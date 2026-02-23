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
    # Норма рабочих дней и вакационные дни
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
    if emp.is_on_vacation(day):
        return False
    if state.consecutive_working >= MAX_CONSECUTIVE_WORKING:
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
    Тайбрейк — случайный (детерминировано через rng).
    """
    sorted_candidates = sorted(
        candidates,
        key=lambda e: (states[e.name].shift_count(shift), rng.random()),
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
            return -rng.random()  # норма выполнена — низкий приоритет
        # urgency = дефицит / оставшиеся дни: чем выше, тем срочнее
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


def _calc_vacation_days(emp: Employee, year: int, month: int) -> int:
    """Число рабочих дней отпуска сотрудника в данном месяце."""
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        if day.weekday() < 5 and emp.is_on_vacation(day):
            count += 1
    return count


def _build_day(
    day: date,
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    rng: random.Random,
    remaining_days: int,
) -> DaySchedule:
    """Построить расписание на один день."""
    is_holiday = _is_weekend_or_holiday(day, holidays)
    _next_day = day + timedelta(days=1)
    ds = DaySchedule(date=day, is_holiday=is_holiday)

    moscow_duty = [e for e in employees if e.city == City.MOSCOW and e.on_duty]
    khabarovsk_duty = [e for e in employees if e.city == City.KHABAROVSK and e.on_duty]
    non_duty = [e for e in employees if not e.on_duty]

    assigned: dict[str, ShiftType] = {}

    # ── Фаза 1: Ночная смена (Хабаровск, обязательно каждый день) ──────────
    # Ночная смена 00-08 МСК = 07-15 по местному времени Хабаровска.
    # После неё 16 часов отдыха до следующей ночи и >18 часов до рабочего дня 09-18.
    # Поэтому принудительный отдых на следующий день НЕ применяется.
    night_eligible = [
        e
        for e in khabarovsk_duty
        if not e.is_on_vacation(day)
        and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
        and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING
    ]

    if not night_eligible:
        raise ScheduleError(
            f"Невозможно покрыть ночную смену {day}: нет доступных дежурных в Хабаровске"
        )

    # Назначаем ровно 1 хабаровчанина на ночь: сначала те, у кого дефицит нормы,
    # затем по наименьшему числу ночных смен (справедливость).
    night_assigned = _select_for_mandatory(
        night_eligible, states, ShiftType.NIGHT, remaining_days, rng, 1
    )

    for emp in night_assigned:
        assigned[emp.name] = ShiftType.NIGHT

    # ── Фаза 2: Утренняя и вечерняя смены (Москва, обязательно) ───────────
    moscow_available = [
        e
        for e in moscow_duty
        if not e.is_on_vacation(day)
        and not _resting_after_night(states[e.name])
        and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
        and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING
    ]

    morning_eligible = [
        e
        for e in moscow_available
        if e.can_work_morning() and not _resting_after_evening(states[e.name])
    ]
    evening_eligible = [e for e in moscow_available if e.can_work_evening()]

    if not morning_eligible:
        raise ScheduleError(
            f"Невозможно покрыть утреннюю смену {day}: нет доступных дежурных в Москве"
        )
    if not evening_eligible:
        raise ScheduleError(
            f"Невозможно покрыть вечернюю смену {day}: нет доступных дежурных в Москве"
        )

    # Выбираем по 1 на утро и вечер — минимально необходимые.
    # Приоритет — сотрудники с дефицитом нормы, внутри группы — справедливость.
    morning_pick = _select_for_mandatory(
        morning_eligible, states, ShiftType.MORNING, remaining_days, rng, 1
    )
    evening_pick_pool = [
        e for e in moscow_available if e.can_work_evening() and e not in morning_pick
    ]
    if not evening_pick_pool:
        evening_pick_pool = [e for e in evening_eligible if e not in morning_pick]
    if not evening_pick_pool:
        raise ScheduleError(
            f"Невозможно покрыть вечернюю смену {day}: все доступные дежурные заняты утром"
        )
    # Сотрудники после вечерней смены не могут взять утро или рабочий день —
    # вечер для них единственный способ заработать рабочий день.
    # Даём им приоритет, но только если они ещё не исчерпывают MAX (cw < MAX-1),
    # чтобы не создавать длинные цепочки вечерних смен у одного сотрудника.
    after_evening_deficit = [
        e
        for e in evening_pick_pool
        if _resting_after_evening(states[e.name])
        and states[e.name].needs_more_work(remaining_days)
        and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING - 1
    ]
    if after_evening_deficit:
        evening_pick = _select_fair(after_evening_deficit, states, ShiftType.EVENING, rng, 1)
    else:
        evening_pick = _select_for_mandatory(
            evening_pick_pool, states, ShiftType.EVENING, remaining_days, rng, 1
        )

    for emp in morning_pick:
        assigned[emp.name] = ShiftType.MORNING
    for emp in evening_pick:
        assigned[emp.name] = ShiftType.EVENING

    # ── Фаза 2b: Не-дежурный рабочий день (Москва) ──────────────────────────
    # Всем московским дежурным с дефицитом нормы назначаем рабочий день 09-18.
    # Нет жёсткого «один всегда отдыхает» — это приводило к систематической
    # недовыработке. Единственное ограничение: если ЗАВТРА выходной/праздник,
    # обеспечиваем ≥ 2 дежурных с consecutive_working < MAX для обязательных
    # утренней/вечерней смен (иначе никого не останется на субботу/воскресенье).
    if not is_holiday:
        _next_is_holiday = _is_weekend_or_holiday(_next_day, holidays)
        _WORKING = frozenset({ShiftType.MORNING, ShiftType.EVENING, ShiftType.WORKDAY})

        while True:
            extra = [
                e
                for e in moscow_available
                if e.name not in assigned
                and states[e.name].needs_more_work(remaining_days)
                and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING
                and not _resting_after_evening(states[e.name])
            ]
            if not extra:
                break
            by_urgency = _select_by_urgency(extra, states, remaining_days, rng)
            if not by_urgency:
                break
            candidate = by_urgency[0]

            # Проверка «кануна выходного»: после этого назначения должны
            # остаться ≥ 2 дежурных с cw < MAX для завтрашних обязательных смен.
            if _next_is_holiday:
                cand_cw_after = states[candidate.name].consecutive_working + 1
                avail_tomorrow = 0
                for e in moscow_duty:
                    if e.name == candidate.name:
                        if cand_cw_after < MAX_CONSECUTIVE_WORKING:
                            avail_tomorrow += 1
                    else:
                        s = assigned.get(e.name)
                        cw_ok = states[e.name].consecutive_working + 1 < MAX_CONSECUTIVE_WORKING
                        if s is None or s not in _WORKING or cw_ok:  # day_off/vacation → cw=0
                            avail_tomorrow += 1
                if avail_tomorrow < 2:
                    break

            assigned[candidate.name] = ShiftType.WORKDAY

    # Неназначенные московские дежурные → выходной или отпуск
    for emp in moscow_duty:
        if emp.name not in assigned:
            assigned[emp.name] = (
                ShiftType.VACATION if emp.is_on_vacation(day) else ShiftType.DAY_OFF
            )

    # ── Фаза 2c: Хабаровские дежурные — рабочий день по местному времени ───
    # Хабаровские сотрудники работают ТОЛЬКО ночные смены (MSK) или свой
    # местный рабочий день (09-18 Хабаровск = ShiftType.WORKDAY).
    # Они НЕ работают в московское утро или вечер.
    # Рабочий день (09-18) возможен только в будни — в выходные и праздники
    # допустимы только дежурные смены (ночь и т.п.).
    for emp in khabarovsk_duty:
        if emp.name in assigned:
            continue  # уже на ночной смене
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
            continue
        # Принудительный отдых после ночи НЕ применяется: ночь 00-08 МСК =
        # 07-15 КХСТ, после неё достаточно времени до следующего дня 09-18 КХСТ.
        if is_holiday:
            # В выходные и праздники рабочего дня (9-18) нет — только дежурства
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if states[emp.name].consecutive_working >= MAX_CONSECUTIVE_WORKING:
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        # Назначаем рабочий день по местному времени (для выработки нормы),
        # но сначала проверяем: не исчерпаем ли мы всех хабаровчан одновременно.
        # Если после WORKDAY у этого сотрудника cw достигнет MAX — нужно убедиться,
        # что хотя бы один другой хабаровчанин будет доступен завтра для ночи.
        emp_cw_after = states[emp.name].consecutive_working + 1
        needs_work = states[emp.name].needs_more_work(remaining_days)
        if emp_cw_after >= MAX_CONSECUTIVE_WORKING and needs_work:
            others_available = 0
            for other in khabarovsk_duty:
                if other.name == emp.name:
                    continue
                if other.is_on_vacation(_next_day):
                    continue
                other_shift = assigned.get(other.name)
                if other_shift == ShiftType.VACATION:
                    pass
                elif other_shift == ShiftType.DAY_OFF:
                    others_available += 1  # сегодня отдыхает → cw=0 завтра
                elif other_shift in (ShiftType.NIGHT, ShiftType.WORKDAY):
                    if states[other.name].consecutive_working + 1 < MAX_CONSECUTIVE_WORKING:
                        others_available += 1
                else:
                    others_available += 1  # не назначен или иной
            if others_available < 1:
                assigned[emp.name] = ShiftType.DAY_OFF
                continue
        if states[emp.name].needs_more_work(remaining_days):
            assigned[emp.name] = ShiftType.WORKDAY
        else:
            assigned[emp.name] = ShiftType.DAY_OFF

    # ── Фаза 3: Рабочий день (не-дежурные) ─────────────────────────────────
    # Не-дежурные сотрудники не нужны в выходные/праздники вне зависимости
    # от типа расписания (flexible или 5/2).
    for emp in non_duty:
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
        elif is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
        else:
            assigned[emp.name] = ShiftType.WORKDAY

    # ── Фаза 4: Ограничение максимум 3 выходных подряд ─────────────────────
    # Если дежурный отдыхает 3+ дня подряд и ещё не выработал норму,
    # назначаем рабочий день (только в будни). Дежурные смены уже заняты
    # выбранными сотрудниками — добавлять вторых нельзя.
    for emp in moscow_duty + khabarovsk_duty:
        state = states[emp.name]
        if (
            assigned.get(emp.name) == ShiftType.DAY_OFF
            and state.consecutive_off >= MAX_CONSECUTIVE_OFF
            and _can_work(emp, state, day, holidays)
            and not _resting_after_evening(state)
            and state.needs_more_work(remaining_days)
            and not is_holiday  # WORKDAY только в будни
        ):
            assigned[emp.name] = ShiftType.WORKDAY

    # ── Собираем DaySchedule ────────────────────────────────────────────────
    for name, shift in assigned.items():
        if shift == ShiftType.MORNING:
            ds.morning.append(name)
        elif shift == ShiftType.EVENING:
            ds.evening.append(name)
        elif shift == ShiftType.NIGHT:
            ds.night.append(name)
        elif shift == ShiftType.WORKDAY:
            ds.workday.append(name)
        elif shift == ShiftType.VACATION:
            ds.vacation.append(name)
        else:
            ds.day_off.append(name)

    # ── Обновляем состояния ─────────────────────────────────────────────────
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


def _consecutive_off_if_removed(emp_name: str, idx: int, days: list[DaySchedule]) -> int:
    """Количество подряд выходных, если day[idx] станет выходным."""
    left = 0
    for i in range(idx - 1, -1, -1):
        d = days[i]
        if emp_name in d.day_off or emp_name in d.vacation:
            left += 1
        else:
            break
    right = 0
    for i in range(idx + 1, len(days)):
        d = days[i]
        if emp_name in d.day_off or emp_name in d.vacation:
            right += 1
        else:
            break
    return left + 1 + right


def _consecutive_working_if_added(emp_name: str, idx: int, days: list[DaySchedule]) -> int:
    """Количество подряд рабочих дней, если day[idx] станет рабочим."""
    left = 0
    for i in range(idx - 1, -1, -1):
        if _is_working_on_day(emp_name, days[i]):
            left += 1
        else:
            break
    right = 0
    for i in range(idx + 1, len(days)):
        if _is_working_on_day(emp_name, days[i]):
            right += 1
        else:
            break
    return left + 1 + right


def _target_adjustment_pass(
    days: list[DaySchedule],
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
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
                    and _consecutive_off_if_removed(emp.name, i, days) <= MAX_CONSECUTIVE_OFF
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
                    or emp.is_on_vacation(day.date)
                ):
                    continue
                # Нельзя ставить рабочий день после вечерней смены
                if i > 0 and emp.name in days[i - 1].evening:
                    continue
                # Не превышаем MAX + 1 рабочих дня подряд (6 — допустимо в крайнем случае)
                if _consecutive_working_if_added(emp.name, i, days) > MAX_CONSECUTIVE_WORKING + 1:
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


def _balance_duty_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
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

        # Индекс дат для быстрого поиска предыдущего дня
        day_by_date = {d.date: d for d in days}

        for _ in range(len(days) * len(duty_emps)):  # safety limit
            counts: dict[str, int] = {
                e.name: sum(
                    1 for d in days for attr in duty_attrs if e.name in getattr(d, attr)
                )
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

                # max_name должен нести дежурство в этот день
                max_attr = next(
                    (attr for attr in duty_attrs if max_name in getattr(day, attr)),
                    None,
                )
                if max_attr is None:
                    continue

                # min_name должен быть на рабочем дне (WORKDAY) в этот день
                if min_name not in day.workday:
                    continue

                # Проверяем, что min_name может работать этот тип смены
                min_emp = next(e for e in duty_emps if e.name == min_name)
                if max_attr == "morning" and not min_emp.can_work_morning():
                    continue
                if max_attr == "evening" and not min_emp.can_work_evening():
                    continue

                # Для утренней смены: нельзя ставить min_name, если вчера у него вечер
                if max_attr == "morning":
                    prev = day_by_date.get(day.date - timedelta(days=1))
                    if prev and min_name in prev.evening:
                        continue

                # Выполняем замену
                getattr(day, max_attr).remove(max_name)
                day.workday.append(max_name)
                day.workday.remove(min_name)
                getattr(day, max_attr).append(min_name)
                swapped = True
                break

            if not swapped:
                break

    return days


def _fairness_pass(
    days: list[DaySchedule],
    employees: list[Employee],
) -> list[DaySchedule]:
    """
    Пост-обработка: логирование балансировки смен.
    """
    counts: dict[str, dict[ShiftType, int]] = {
        e.name: dict.fromkeys(ShiftType, 0) for e in employees
    }
    for day in days:
        for name in day.morning:
            counts[name][ShiftType.MORNING] += 1
        for name in day.evening:
            counts[name][ShiftType.EVENING] += 1
        for name in day.night:
            counts[name][ShiftType.NIGHT] += 1

    duty_employees = [e for e in employees if e.on_duty]
    evening_counts = {e.name: counts[e.name][ShiftType.EVENING] for e in duty_employees}

    if evening_counts:
        max_ev = max(evening_counts.values())
        min_ev = min(evening_counts.values())
        logger.info("Баланс вечерних смен", max=max_ev, min=min_ev, diff=max_ev - min_ev)

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

    # Норма рабочих дней по производственному календарю
    production_days = _calc_production_days(config.year, config.month, holidays)
    logger.info("Норма рабочих дней", production_days=production_days)

    # Инициализация состояний с нормами
    states: dict[str, EmployeeState] = {}
    for emp in employees:
        vac_days = _calc_vacation_days(emp, config.year, config.month)
        states[emp.name] = EmployeeState(
            target_working_days=production_days,
            vacation_days=vac_days,
        )

    days: list[DaySchedule] = []
    backtrack_stack: list[tuple[date, dict[str, EmployeeState]]] = []

    day_idx = 0
    total_backtracks = 0  # суммарный счётчик откатов (не сбрасывается)

    while day_idx < len(all_days):
        day = all_days[day_idx]
        saved_states = copy.deepcopy(states)
        remaining_days = len(all_days) - day_idx

        try:
            ds = _build_day(day, employees, states, holidays, rng, remaining_days)
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

    days = _fairness_pass(days, employees)
    days = _balance_duty_shifts(days, employees, holidays)
    days = _target_adjustment_pass(days, employees, states, holidays)

    # Метаданные
    total_nights = sum(len(d.night) for d in days)
    total_mornings = sum(len(d.morning) for d in days)
    total_evenings = sum(len(d.evening) for d in days)
    uncovered = [d.date for d in days if not d.is_covered()]

    if uncovered:
        raise ScheduleError(f"Не покрыты смены для дней: {[str(d) for d in uncovered]}")

    # Отчёт по выработке
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
        },
    )
