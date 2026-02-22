"""Движок генерации расписания: жадный алгоритм с откатом."""

from __future__ import annotations

import calendar
import copy
import random
from dataclasses import dataclass
from datetime import date

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


def _resting_after_evening_for_morning(state: EmployeeState) -> bool:
    """После вечерней смены нельзя работать в утреннюю."""
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
    ds = DaySchedule(date=day, is_holiday=is_holiday)

    moscow_duty = [e for e in employees if e.city == City.MOSCOW and e.on_duty]
    khabarovsk_duty = [e for e in employees if e.city == City.KHABAROVSK and e.on_duty]
    non_duty = [e for e in employees if not e.on_duty]

    assigned: dict[str, ShiftType] = {}

    # ── Фаза 1: Ночная смена (Хабаровск, обязательно каждый день) ──────────
    night_eligible = [
        e
        for e in khabarovsk_duty
        if not e.is_on_vacation(day)
        and not _resting_after_night(states[e.name])
        and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
        and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING
    ]

    if not night_eligible:
        raise ScheduleError(
            f"Невозможно покрыть ночную смену {day}: нет доступных дежурных в Хабаровске"
        )

    # Назначаем ровно 1 хабаровчанина на ночь (справедливо чередуя по числу ночей)
    night_assigned = _select_fair(night_eligible, states, ShiftType.NIGHT, rng, 1)

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
        if e.can_work_morning() and not _resting_after_evening_for_morning(states[e.name])
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

    # Выбираем по 1 на утро и вечер — минимально необходимые
    morning_pick = _select_fair(morning_eligible, states, ShiftType.MORNING, rng, 1)
    evening_pick_pool = [
        e for e in moscow_available if e.can_work_evening() and e not in morning_pick
    ]
    if not evening_pick_pool:
        evening_pick_pool = [e for e in evening_eligible if e not in morning_pick]
    if not evening_pick_pool:
        raise ScheduleError(
            f"Невозможно покрыть вечернюю смену {day}: все доступные дежурные заняты утром"
        )
    evening_pick = _select_fair(evening_pick_pool, states, ShiftType.EVENING, rng, 1)

    for emp in morning_pick:
        assigned[emp.name] = ShiftType.MORNING
    for emp in evening_pick:
        assigned[emp.name] = ShiftType.EVENING

    # ── Фаза 2b: Дополнительные смены для выработки нормы (Москва) ─────────
    # Добавляем экстра-назначения пока хотя бы один сотрудник остаётся на отдыхе
    # (invariant: len(available) - assigned >= 1).
    assigned_moscow_count = sum(1 for e in moscow_duty if e.name in assigned)
    while len(moscow_available) - assigned_moscow_count > 1:
        extra_moscow = [
            e
            for e in moscow_available
            if e.name not in assigned
            and states[e.name].needs_more_work(remaining_days)
            and states[e.name].consecutive_working < MAX_CONSECUTIVE_WORKING
        ]
        extra_by_urgency = _select_by_urgency(extra_moscow, states, remaining_days, rng)
        if not extra_by_urgency:
            break
        emp = extra_by_urgency[0]
        if emp.can_work_morning() and not _resting_after_evening_for_morning(states[emp.name]):
            assigned[emp.name] = ShiftType.MORNING
            assigned_moscow_count += 1
        elif emp.can_work_evening():
            assigned[emp.name] = ShiftType.EVENING
            assigned_moscow_count += 1
        else:
            break

    # ── Фаза 2c: Хабаровские дежурные — рабочий день по местному времени ───
    # Хабаровские сотрудники работают ТОЛЬКО ночные смены (MSK) или свой
    # местный рабочий день (09-18 Хабаровск = ShiftType.WORKDAY).
    # Они НЕ работают в московское утро или вечер.
    for emp in khabarovsk_duty:
        if emp.name in assigned:
            continue  # уже на ночной смене
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
            continue
        if _resting_after_night(states[emp.name]):
            # Обязательный отдых после ночной смены
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if emp.schedule_type == ScheduleType.FIVE_TWO and is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if states[emp.name].consecutive_working >= MAX_CONSECUTIVE_WORKING:
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        # Назначаем рабочий день по местному времени (для выработки нормы)
        if states[emp.name].needs_more_work(remaining_days):
            assigned[emp.name] = ShiftType.WORKDAY
        else:
            assigned[emp.name] = ShiftType.DAY_OFF

    # Оставшиеся московские дежурные → выходной/отпуск
    for emp in moscow_duty:
        if emp.name not in assigned:
            assigned[emp.name] = (
                ShiftType.VACATION if emp.is_on_vacation(day) else ShiftType.DAY_OFF
            )

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
    for emp in moscow_duty + khabarovsk_duty:
        state = states[emp.name]
        if (
            assigned.get(emp.name) == ShiftType.DAY_OFF
            and state.consecutive_off >= MAX_CONSECUTIVE_OFF
            and _can_work(emp, state, day, holidays)
            and not _resting_after_night(state)
        ):
            if emp.city == City.KHABAROVSK:
                # Хабаровские не работают в московские смены — только рабочий день
                assigned[emp.name] = ShiftType.WORKDAY
            elif emp.can_work_morning() and not _resting_after_evening_for_morning(state):
                assigned[emp.name] = ShiftType.MORNING
            elif emp.can_work_evening():
                assigned[emp.name] = ShiftType.EVENING

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
