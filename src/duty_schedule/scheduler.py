"""Движок генерации расписания: жадный алгоритм с откатом."""

from __future__ import annotations

import calendar
import copy
import random
from dataclasses import dataclass
from datetime import date, timedelta

from duty_schedule.logging import get_logger
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
    ShiftType,
)

logger = get_logger()

MAX_CONSECUTIVE_WORKING = 5
MAX_CONSECUTIVE_OFF = 3
MAX_BACKTRACK_DAYS = 3
MAX_BACKTRACK_ATTEMPTS = 10


def _max_cw(emp: Employee) -> int:
    """Максимальное число рабочих дней подряд для сотрудника."""
    if emp.max_consecutive_working is not None:
        return emp.max_consecutive_working
    return MAX_CONSECUTIVE_WORKING


def _shift_limit_reached(emp: Employee, state: EmployeeState, shift: ShiftType) -> bool:
    """Достигнут ли месячный лимит смен данного типа для сотрудника."""
    if shift == ShiftType.MORNING and emp.max_morning_shifts is not None:
        return state.morning_count >= emp.max_morning_shifts
    if shift == ShiftType.EVENING and emp.max_evening_shifts is not None:
        return state.evening_count >= emp.max_evening_shifts
    if shift == ShiftType.NIGHT and emp.max_night_shifts is not None:
        return state.night_count >= emp.max_night_shifts
    return False


class ScheduleError(Exception):
    """Расписание не может быть построено."""


@dataclass
class EmployeeState:
    consecutive_working: int = 0
    consecutive_off: int = 0
    last_shift: ShiftType | None = None
    night_count: int = 0
    morning_count: int = 0
    evening_count: int = 0
    workday_count: int = 0
    total_working: int = 0
    target_working_days: int = 0
    vacation_days: int = 0

    def shift_count(self, shift: ShiftType) -> int:
        return {
            ShiftType.NIGHT: self.night_count,
            ShiftType.MORNING: self.morning_count,
            ShiftType.EVENING: self.evening_count,
            ShiftType.WORKDAY: self.workday_count,
        }.get(shift, 0)

    def record(self, shift: ShiftType) -> None:
        if shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY):
            self.consecutive_working += 1
            self.consecutive_off = 0
            self.total_working += 1
        else:
            self.consecutive_off += 1
            self.consecutive_working = 0
        self.last_shift = shift
        if shift == ShiftType.MORNING:
            self.morning_count += 1
        elif shift == ShiftType.EVENING:
            self.evening_count += 1
        elif shift == ShiftType.NIGHT:
            self.night_count += 1
        elif shift == ShiftType.WORKDAY:
            self.workday_count += 1

    @property
    def effective_target(self) -> int:
        """Целевое число рабочих дней с учётом отпуска."""
        return max(0, self.target_working_days - self.vacation_days)

    def needs_more_work(self, remaining_days: int) -> bool:
        """Сотрудник отстаёт от нормы и нужно дополнительно назначать."""
        if remaining_days <= 0:
            return False
        deficit = self.effective_target - self.total_working
        return deficit > 0


def _is_weekend_or_holiday(day: date, holidays: set[date]) -> bool:
    return day.weekday() >= 5 or day in holidays


def _can_work(
    emp: Employee,
    state: EmployeeState,
    day: date,
    holidays: set[date],
) -> bool:
    """Может ли сотрудник работать в указанный день (любая смена)."""
    if emp.is_blocked(day):
        return False
    if emp.is_day_off_weekly(day):
        return False
    if state.consecutive_working >= _max_cw(emp):
        return False
    is_weekend = _is_weekend_or_holiday(day, holidays)
    return not (emp.schedule_type == ScheduleType.FIVE_TWO and is_weekend)


def _resting_after_night(state: EmployeeState) -> bool:
    return state.last_shift == ShiftType.NIGHT


def _resting_after_evening(state: EmployeeState) -> bool:
    """После вечерней смены (15:00–00:00) можно только снова вечером или выходной.
    Утро (08:00) и рабочий день (09:00) — недопустимы: слишком мало времени отдыха."""
    return state.last_shift == ShiftType.EVENING


def _select_fair(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    shift: ShiftType,
    rng: random.Random,
    count: int = 1,
) -> list[Employee]:
    """
    Выбрать `count` сотрудников из кандидатов по принципу минимального числа смен.
    Сотрудники с preferred_shift == shift получают мягкий приоритет.
    Тайбрейк — случайный (детерминировано через rng).
    """
    sorted_candidates = sorted(
        candidates,
        key=lambda e: (
            states[e.name].shift_count(shift),
            0 if e.preferred_shift == shift else 1,
            rng.random(),
        ),
    )
    return sorted_candidates[:count]


def _select_for_mandatory(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    shift: ShiftType,
    remaining_days: int,
    rng: random.Random,
    count: int = 1,
) -> list[Employee]:
    """
    Выбор для обязательных смен:
    - Предпочтение тем, у кого есть дефицит нормы (deficit > 0)
    - Внутри группы — справедливый выбор: минимальное число смен данного типа
    - Если нет кандидатов с дефицитом → обычный справедливый выбор из всех

    Это позволяет:
    1. Не «перегружать» сотрудников, уже выполнивших норму (они назначаются
       только если больше некому).
    2. Распределять нагрузку равномерно внутри группы с дефицитом, не создавая
       серий из 5+ рабочих дней подряд (риск при urgency-based выборе).
    """
    deficit_pool = [e for e in candidates if states[e.name].needs_more_work(remaining_days)]
    pool = deficit_pool if deficit_pool else candidates
    return _select_fair(pool, states, shift, rng, count)


def _select_by_urgency(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    remaining_days: int,
    rng: random.Random,
) -> list[Employee]:
    """
    Выбрать сотрудников, которым срочнее всего нужны смены для выполнения нормы.
    Сортировка: наибольший дефицит / оставшиеся дни → первый.
    """

    def urgency(emp: Employee) -> float:
        st = states[emp.name]
        deficit = st.effective_target - st.total_working
        if deficit <= 0:
            return -rng.random()
        return deficit / max(remaining_days, 1) + rng.random() * 0.001

    return sorted(candidates, key=urgency, reverse=True)


def _calc_production_days(year: int, month: int, holidays: set[date]) -> int:
    """Количество рабочих дней в месяце по производственному календарю."""
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        if day.weekday() < 5 and day not in holidays:
            count += 1
    return count


def _calc_blocked_working_days(emp: Employee, year: int, month: int) -> int:
    """Число рабочих дней (Пн–Пт), когда сотрудник недоступен (отпуск + unavailable_dates).

    Используется для снижения нормы: если сотрудник недоступен в рабочий день,
    этот день не включается в целевое число рабочих дней (effective_target).
    """
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        if day.weekday() < 5 and emp.is_blocked(day):
            count += 1
    return count


def _build_day(
    day: date,
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    rng: random.Random,
    remaining_days: int,
    pins_today: dict[str, ShiftType] | None = None,
) -> DaySchedule:
    """Построить расписание на один день."""
    is_holiday = _is_weekend_or_holiday(day, holidays)
    _next_day = day + timedelta(days=1)
    ds = DaySchedule(date=day, is_holiday=is_holiday)

    moscow_duty = [e for e in employees if e.city == City.MOSCOW and e.on_duty]
    khabarovsk_duty = [e for e in employees if e.city == City.KHABAROVSK and e.on_duty]
    non_duty = [e for e in employees if not e.on_duty]
    emp_by_name = {e.name: e for e in employees}

    assigned: dict[str, ShiftType] = dict(pins_today or {})

    _night_pinned = any(s == ShiftType.NIGHT for s in assigned.values())
    if not _night_pinned:
        night_eligible = [
            e
            for e in khabarovsk_duty
            if e.name not in assigned
            and not e.is_blocked(day)
            and not e.is_day_off_weekly(day)
            and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
            and states[e.name].consecutive_working < _max_cw(e)
            and not _shift_limit_reached(e, states[e.name], ShiftType.NIGHT)
        ]

        if not night_eligible:
            raise ScheduleError(
                f"Невозможно покрыть ночную смену {day}: нет доступных дежурных в Хабаровске"
            )

        night_assigned = _select_for_mandatory(
            night_eligible, states, ShiftType.NIGHT, remaining_days, rng, 1
        )
        for emp in night_assigned:
            assigned[emp.name] = ShiftType.NIGHT

    moscow_available = [
        e
        for e in moscow_duty
        if e.name not in assigned
        and not e.is_blocked(day)
        and not e.is_day_off_weekly(day)
        and not _resting_after_night(states[e.name])
        and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
        and states[e.name].consecutive_working < _max_cw(e)
    ]

    _morning_pinned = any(s == ShiftType.MORNING for s in assigned.values())
    _evening_pinned = any(s == ShiftType.EVENING for s in assigned.values())

    morning_groups_taken: set[str] = {
        emp_by_name[name].group
        for name, s in assigned.items()
        if s == ShiftType.MORNING and name in emp_by_name and emp_by_name[name].group
    }

    morning_eligible = [
        e
        for e in moscow_available
        if e.can_work_morning()
        and not _resting_after_evening(states[e.name])
        and not _shift_limit_reached(e, states[e.name], ShiftType.MORNING)
        and (not e.group or e.group not in morning_groups_taken)
    ]
    evening_eligible = [
        e
        for e in moscow_available
        if e.can_work_evening() and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
    ]

    if not _morning_pinned:
        if not morning_eligible:
            raise ScheduleError(
                f"Невозможно покрыть утреннюю смену {day}: нет доступных дежурных в Москве"
            )
        morning_pick = _select_for_mandatory(
            morning_eligible, states, ShiftType.MORNING, remaining_days, rng, 1
        )
        for emp in morning_pick:
            assigned[emp.name] = ShiftType.MORNING
            if emp.group:
                morning_groups_taken.add(emp.group)
    else:
        morning_pick = []

    if not _evening_pinned:
        evening_groups_taken: set[str] = {
            emp_by_name[name].group
            for name, s in assigned.items()
            if s == ShiftType.EVENING and name in emp_by_name and emp_by_name[name].group
        }
        evening_pick_pool = [
            e
            for e in moscow_available
            if e.can_work_evening()
            and e not in morning_pick
            and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
            and (not e.group or e.group not in evening_groups_taken)
        ]
        if not evening_pick_pool:
            evening_pick_pool = [
                e
                for e in evening_eligible
                if e not in morning_pick and (not e.group or e.group not in evening_groups_taken)
            ]
        if not evening_pick_pool:
            raise ScheduleError(
                f"Невозможно покрыть вечернюю смену {day}: все доступные дежурные заняты утром"
            )
        after_evening_deficit = [
            e
            for e in evening_pick_pool
            if _resting_after_evening(states[e.name])
            and states[e.name].needs_more_work(remaining_days)
            and states[e.name].consecutive_working < _max_cw(e) - 1
        ]
        if after_evening_deficit:
            evening_pick = _select_fair(after_evening_deficit, states, ShiftType.EVENING, rng, 1)
        else:
            evening_pick = _select_for_mandatory(
                evening_pick_pool, states, ShiftType.EVENING, remaining_days, rng, 1
            )
        for emp in evening_pick:
            assigned[emp.name] = ShiftType.EVENING

    if not is_holiday:
        _next_is_holiday = _is_weekend_or_holiday(_next_day, holidays)
        _WORKING = frozenset({ShiftType.MORNING, ShiftType.EVENING, ShiftType.WORKDAY})

        while True:
            extra = [
                e
                for e in moscow_available
                if e.name not in assigned
                and states[e.name].needs_more_work(remaining_days)
                and states[e.name].consecutive_working < _max_cw(e)
                and not _resting_after_evening(states[e.name])
            ]
            if not extra:
                break
            by_urgency = _select_by_urgency(extra, states, remaining_days, rng)
            if not by_urgency:
                break
            candidate = by_urgency[0]

            if _next_is_holiday:
                cand_cw_after = states[candidate.name].consecutive_working + 1
                avail_tomorrow = 0
                for e in moscow_duty:
                    if e.name == candidate.name:
                        if cand_cw_after < _max_cw(e):
                            avail_tomorrow += 1
                    else:
                        s = assigned.get(e.name)
                        cw_ok = states[e.name].consecutive_working + 1 < _max_cw(e)
                        if s is None or s not in _WORKING or cw_ok:
                            avail_tomorrow += 1
                if avail_tomorrow < 2:
                    break

            assigned[candidate.name] = ShiftType.WORKDAY

    for emp in moscow_duty:
        if emp.name not in assigned:
            assigned[emp.name] = (
                ShiftType.VACATION if emp.is_on_vacation(day) else ShiftType.DAY_OFF
            )

    for emp in khabarovsk_duty:
        if emp.name in assigned:
            continue
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
            continue
        if day in emp.unavailable_dates or emp.is_day_off_weekly(day):
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if states[emp.name].consecutive_working >= _max_cw(emp):
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        emp_cw_after = states[emp.name].consecutive_working + 1
        needs_work = states[emp.name].needs_more_work(remaining_days)
        if emp_cw_after >= _max_cw(emp) and needs_work:
            others_available = 0
            for other in khabarovsk_duty:
                if other.name == emp.name:
                    continue
                if other.is_blocked(_next_day):
                    continue
                other_shift = assigned.get(other.name)
                if other_shift == ShiftType.VACATION:
                    pass
                elif other_shift == ShiftType.DAY_OFF:
                    others_available += 1
                elif other_shift in (ShiftType.NIGHT, ShiftType.WORKDAY):
                    if states[other.name].consecutive_working + 1 < _max_cw(other):
                        others_available += 1
                else:
                    others_available += 1
            if others_available < 1:
                assigned[emp.name] = ShiftType.DAY_OFF
                continue
        if states[emp.name].needs_more_work(remaining_days):
            assigned[emp.name] = ShiftType.WORKDAY
        else:
            assigned[emp.name] = ShiftType.DAY_OFF

    for emp in non_duty:
        if emp.name in assigned:
            continue
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
        elif day in emp.unavailable_dates or emp.is_day_off_weekly(day) or is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
        else:
            assigned[emp.name] = ShiftType.WORKDAY

    for emp in moscow_duty + khabarovsk_duty:
        state = states[emp.name]
        if (
            assigned.get(emp.name) == ShiftType.DAY_OFF
            and state.consecutive_off >= MAX_CONSECUTIVE_OFF
            and _can_work(emp, state, day, holidays)
            and not _resting_after_evening(state)
            and state.needs_more_work(remaining_days)
            and not is_holiday
        ):
            assigned[emp.name] = ShiftType.WORKDAY

    for name, shift in assigned.items():
        getattr(ds, shift.value).append(name)

    for emp in employees:
        states[emp.name].record(assigned.get(emp.name, ShiftType.DAY_OFF))

    return ds


def _is_working_on_day(emp_name: str, day: DaySchedule) -> bool:
    return (
        emp_name in day.morning
        or emp_name in day.evening
        or emp_name in day.night
        or emp_name in day.workday
    )


def _streak_around(emp_name: str, idx: int, days: list[DaySchedule], working: bool) -> int:
    """Длина серии вокруг days[idx], если он становится рабочим (working=True) или выходным."""

    def active(d: DaySchedule) -> bool:
        return (
            _is_working_on_day(emp_name, d)
            if working
            else (emp_name in d.day_off or emp_name in d.vacation)
        )

    left = 0
    for i in range(idx - 1, -1, -1):
        if active(days[i]):
            left += 1
        else:
            break
    right = 0
    for i in range(idx + 1, len(days)):
        if active(days[i]):
            right += 1
        else:
            break
    return left + 1 + right


def _target_adjustment_pass(
    days: list[DaySchedule],
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    pinned_on: set[tuple[date, str]] = frozenset(),
) -> list[DaySchedule]:
    """
    Пост-обработка: скорректировать WORKDAY/DAY_OFF, чтобы каждый сотрудник
    отработал ровно столько дней, сколько предписывает производственный календарь.

    - Избыток: снимаем WORKDAY (с конца месяца), не создавая цепочек выходных > MAX.
    - Недостача: добавляем WORKDAY (с начала месяца), не создавая цепочек рабочих > MAX+1.
    """
    for emp in employees:
        if not emp.on_duty:
            continue

        state = states[emp.name]
        target = state.effective_target
        actual = state.total_working

        if actual > target:
            excess = actual - target
            for i in range(len(days) - 1, -1, -1):
                if excess == 0:
                    break
                day = days[i]
                if (
                    emp.name in day.workday
                    and not _is_weekend_or_holiday(day.date, holidays)
                    and (day.date, emp.name) not in pinned_on
                    and _streak_around(emp.name, i, days, working=False) <= MAX_CONSECUTIVE_OFF
                ):
                    day.workday.remove(emp.name)
                    day.day_off.append(emp.name)
                    state.total_working -= 1
                    excess -= 1
            if excess > 0:
                logger.warning(
                    "Не удалось убрать избыток рабочих дней",
                    employee=emp.name,
                    excess=excess,
                )

        elif actual < target:
            deficit = target - actual
            for i in range(len(days)):
                if deficit == 0:
                    break
                day = days[i]
                if (
                    emp.name not in day.day_off
                    or _is_weekend_or_holiday(day.date, holidays)
                    or emp.is_blocked(day.date)
                ):
                    continue
                if i > 0 and emp.name in days[i - 1].evening:
                    continue
                if _streak_around(emp.name, i, days, working=True) > _max_cw(emp):
                    continue
                day.day_off.remove(emp.name)
                day.workday.append(emp.name)
                state.total_working += 1
                deficit -= 1
            if deficit > 0:
                logger.warning(
                    "Не удалось закрыть недостачу рабочих дней",
                    employee=emp.name,
                    deficit=deficit,
                )

    return days


def _balance_weekend_work(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: set[tuple[date, str]] = frozenset(),
) -> list[DaySchedule]:
    """
    Пост-обработка: выровнять число рабочих суббот/воскресений между дежурными
    гибкого графика одного города. Разница max−min должна быть ≤ 1.

    Принцип: swap между перегруженным (A) и недогруженным (B) в выходной день
    (сб/вс), где A несёт дежурство (утро/вечер/ночь), а B стоит «выходным» (DAY_OFF).
    Балансировка меняет total_working — caller обязан пересчитать состояния.
    """
    day_by_date = {d.date: d for d in days}
    weekend_days = [d for d in days if d.date.weekday() >= 5]
    if not weekend_days:
        return days

    for city in [City.MOSCOW, City.KHABAROVSK]:
        duty_emps = [
            e
            for e in employees
            if e.city == city and e.on_duty and e.schedule_type == ScheduleType.FLEXIBLE
        ]
        if len(duty_emps) < 2:
            continue

        duty_attrs = ["morning", "evening"] if city == City.MOSCOW else ["night"]

        for _ in range(len(weekend_days) * len(duty_emps)):
            counts: dict[str, int] = {
                e.name: sum(
                    1 for d in weekend_days for attr in duty_attrs if e.name in getattr(d, attr)
                )
                for e in duty_emps
            }
            max_name = max(counts, key=counts.__getitem__)
            min_name = min(counts, key=counts.__getitem__)
            if counts[max_name] - counts[min_name] <= 1:
                break

            swapped = False
            for day in weekend_days:
                if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                    continue
                if min_name in day.vacation or max_name in day.vacation:
                    continue

                max_attr = next(
                    (attr for attr in duty_attrs if max_name in getattr(day, attr)),
                    None,
                )
                if max_attr is None:
                    continue

                if min_name not in day.day_off:
                    continue

                min_emp = next(e for e in duty_emps if e.name == min_name)
                if max_attr == "morning" and not min_emp.can_work_morning():
                    continue
                if max_attr == "evening" and not min_emp.can_work_evening():
                    continue

                if max_attr == "morning" and min_emp.max_morning_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.morning)
                    if cur >= min_emp.max_morning_shifts:
                        continue
                if max_attr == "evening" and min_emp.max_evening_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.evening)
                    if cur >= min_emp.max_evening_shifts:
                        continue
                if max_attr == "night" and min_emp.max_night_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.night)
                    if cur >= min_emp.max_night_shifts:
                        continue

                prev = day_by_date.get(day.date - timedelta(days=1))
                if max_attr == "morning" and prev and min_name in prev.evening:
                    continue

                getattr(day, max_attr).remove(max_name)
                day.day_off.append(max_name)
                day.day_off.remove(min_name)
                getattr(day, max_attr).append(min_name)
                swapped = True
                break

            if not swapped:
                break

    return days


def _balance_duty_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: set[tuple[date, str]] = frozenset(),
) -> list[DaySchedule]:
    """
    Пост-обработка: выровнять число дежурных смен между сотрудниками одного города.
    Разница max−min должна быть ≤ 1.

    Принцип: swap между перегруженным (A) и недогруженным (B) в будний день,
    где A несёт дежурство (утро/вечер/ночь), а B стоит «рабочим днём» (WORKDAY).
    Оба по-прежнему отрабатывают один рабочий день — итоговый счёт не меняется.
    """
    for city in [City.MOSCOW, City.KHABAROVSK]:
        duty_emps = [e for e in employees if e.city == city and e.on_duty]
        if len(duty_emps) < 2:
            continue

        duty_attrs = ["morning", "evening"] if city == City.MOSCOW else ["night"]

        day_by_date = {d.date: d for d in days}

        for _ in range(len(days) * len(duty_emps)):
            counts: dict[str, int] = {
                e.name: sum(1 for d in days for attr in duty_attrs if e.name in getattr(d, attr))
                for e in duty_emps
            }
            max_name = max(counts, key=counts.__getitem__)
            min_name = min(counts, key=counts.__getitem__)
            if counts[max_name] - counts[min_name] <= 1:
                break

            swapped = False
            for day in days:
                if _is_weekend_or_holiday(day.date, holidays):
                    continue
                if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                    continue

                max_attr = next(
                    (attr for attr in duty_attrs if max_name in getattr(day, attr)),
                    None,
                )
                if max_attr is None:
                    continue

                if min_name not in day.workday:
                    continue

                min_emp = next(e for e in duty_emps if e.name == min_name)
                if max_attr == "morning" and not min_emp.can_work_morning():
                    continue
                if max_attr == "evening" and not min_emp.can_work_evening():
                    continue

                if max_attr == "morning" and min_emp.max_morning_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.morning)
                    if cur >= min_emp.max_morning_shifts:
                        continue
                if max_attr == "evening" and min_emp.max_evening_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.evening)
                    if cur >= min_emp.max_evening_shifts:
                        continue
                if max_attr == "night" and min_emp.max_night_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.night)
                    if cur >= min_emp.max_night_shifts:
                        continue

                prev = day_by_date.get(day.date - timedelta(days=1))
                if prev and max_name in prev.evening:
                    continue
                if max_attr == "morning" and prev and min_name in prev.evening:
                    continue

                getattr(day, max_attr).remove(max_name)
                day.workday.append(max_name)
                day.workday.remove(min_name)
                getattr(day, max_attr).append(min_name)
                swapped = True
                break

            if not swapped:
                break

    return days


def generate_schedule(
    config: Config,
    holidays: set[date],
) -> Schedule:
    """
    Основная точка входа: генерация расписания на месяц.

    Каждый сотрудник должен отработать число дней, равное числу рабочих дней
    производственного календаря (за вычетом отпускных рабочих дней).

    Args:
        config: Конфигурация (сотрудники, месяц, год, seed).
        holidays: Множество дат-праздников/выходных (суббота/воскресенье + праздники).

    Returns:
        Готовое расписание.

    Raises:
        ScheduleError: Если расписание не может быть построено.
    """
    from duty_schedule.calendar import get_all_days

    rng = random.Random(config.seed)
    all_days = get_all_days(config.year, config.month)
    employees = config.employees

    pins_by_date: dict[date, dict[str, ShiftType]] = {}
    for pin in config.pins:
        pins_by_date.setdefault(pin.date, {})[pin.employee_name] = pin.shift
    pinned_on: set[tuple[date, str]] = {(p.date, p.employee_name) for p in config.pins}

    production_days = _calc_production_days(config.year, config.month, holidays)
    logger.info("Норма рабочих дней", production_days=production_days)

    states: dict[str, EmployeeState] = {}
    for emp in employees:
        vac_days = _calc_blocked_working_days(emp, config.year, config.month)
        target = round(production_days * emp.workload_pct / 100)
        states[emp.name] = EmployeeState(
            target_working_days=target,
            vacation_days=vac_days,
        )

    carry_over_by_name = {c.employee_name: c for c in config.carry_over}
    for emp in employees:
        if emp.name in carry_over_by_name:
            co = carry_over_by_name[emp.name]
            if co.last_shift is not None:
                states[emp.name].last_shift = co.last_shift
            states[emp.name].consecutive_working = co.consecutive_working
            states[emp.name].consecutive_off = co.consecutive_off

    days: list[DaySchedule] = []
    backtrack_stack: list[tuple[date, dict[str, EmployeeState]]] = []

    day_idx = 0
    total_backtracks = 0

    while day_idx < len(all_days):
        day = all_days[day_idx]
        saved_states = copy.deepcopy(states)
        remaining_days = len(all_days) - day_idx

        try:
            ds = _build_day(
                day,
                employees,
                states,
                holidays,
                rng,
                remaining_days,
                pins_today=pins_by_date.get(day),
            )
            days.append(ds)
            backtrack_stack.append((day, saved_states))
            day_idx += 1

        except ScheduleError as exc:
            logger.warning("Ошибка назначения смены, откат", day=str(day), reason=str(exc))
            total_backtracks += 1

            if total_backtracks > MAX_BACKTRACK_ATTEMPTS or len(backtrack_stack) < 1:
                raise ScheduleError(
                    f"Расписание не может быть построено: {exc}\n"
                    f"Откатов всего: {total_backtracks}. Проверьте параметры сотрудников."
                ) from exc

            steps_back = min(MAX_BACKTRACK_DAYS, len(backtrack_stack))
            for _ in range(steps_back):
                if backtrack_stack:
                    _, states = backtrack_stack.pop()
                    days.pop()
                    day_idx -= 1

            rng = random.Random(config.seed + total_backtracks * 1000 + day_idx)

    days = _balance_weekend_work(days, employees, pinned_on=pinned_on)
    for emp in employees:
        states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))

    days = _balance_duty_shifts(days, employees, holidays, pinned_on=pinned_on)
    days = _target_adjustment_pass(days, employees, states, holidays, pinned_on=pinned_on)

    duty_employees = [e for e in employees if e.on_duty]
    ev_counts = {e.name: sum(1 for d in days if e.name in d.evening) for e in duty_employees}
    if ev_counts:
        max_ev, min_ev = max(ev_counts.values()), min(ev_counts.values())
        logger.info("Баланс вечерних смен", max=max_ev, min=min_ev, diff=max_ev - min_ev)

    total_nights = sum(len(d.night) for d in days)
    total_mornings = sum(len(d.morning) for d in days)
    total_evenings = sum(len(d.evening) for d in days)
    uncovered = [d.date for d in days if not d.is_covered()]

    if uncovered:
        raise ScheduleError(f"Не покрыты смены для дней: {[str(d) for d in uncovered]}")

    working_days_report: dict[str, int] = {
        emp.name: states[emp.name].total_working for emp in employees
    }
    logger.info(
        "Расписание сгенерировано",
        days=len(days),
        nights=total_nights,
        mornings=total_mornings,
        evenings=total_evenings,
        production_days=production_days,
        working_days_per_employee=working_days_report,
    )

    final_carry_over = [
        {
            "employee_name": emp.name,
            "last_shift": str(states[emp.name].last_shift) if states[emp.name].last_shift else None,
            "consecutive_working": states[emp.name].consecutive_working,
            "consecutive_off": states[emp.name].consecutive_off,
        }
        for emp in employees
    ]

    return Schedule(
        config=config,
        days=days,
        metadata={
            "total_nights": total_nights,
            "total_mornings": total_mornings,
            "total_evenings": total_evenings,
            "holidays_count": len(holidays),
            "production_working_days": production_days,
            "working_days_per_employee": working_days_report,
            "carry_over": final_carry_over,
        },
    )
