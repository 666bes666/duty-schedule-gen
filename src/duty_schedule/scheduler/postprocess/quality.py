from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date

from duty_schedule.calendar import calendar_for_config
from duty_schedule.logging import get_logger
from duty_schedule.models import City, Config, ProductionCalendar, Schedule, ShiftType
from duty_schedule.scheduler.rules import (
    WORKING_SHIFTS,
    assignment_for,
    can_assign_work,
    carry_for_employee,
)
from duty_schedule.workload import calculate_monthly_targets

logger = get_logger(__name__)


def eligible_duty_names(
    config: Config,
    calendar: ProductionCalendar,
    dates: Sequence[date],
    shifts: tuple[ShiftType, ...],
    *,
    allow_pending: bool = False,
) -> set[str]:
    first_date = date(config.year, config.month, 1)
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    eligible: set[str] = set()
    for employee in config.employees:
        carry = carry_for_employee(config, employee)
        if any(
            ((pin := pins.get((day, employee.name))) is None or pin.shift == shift)
            and can_assign_work(
                config,
                calendar,
                employee,
                day,
                shift,
                carry.last_shift if carry and day == first_date else None,
                carry.consecutive_working if carry and day == first_date else 0,
                allow_pending,
            )
            for day in dates
            for shift in shifts
        ):
            eligible.add(employee.name)
    return eligible


def quality_key(schedule: Schedule) -> tuple[int, int, int, int]:
    calendar = calendar_for_config(schedule.config)
    targets = calculate_monthly_targets(schedule.config, calendar)
    isolated = 0
    streak_penalty = 0
    longest = 0
    for employee in schedule.config.employees:
        carry = carry_for_employee(schedule.config, employee)
        streak = carry.consecutive_working if carry else 0
        rest = carry.consecutive_off if carry and not carry.no_previous_shifts else 2
        for day in schedule.days:
            working = assignment_for(day, employee.name) in WORKING_SHIFTS
            if working:
                isolated += int(rest == 1)
                rest = 0
                streak += 1
                longest = max(longest, streak)
                streak_penalty += streak * streak
            else:
                streak = 0
                rest += 1

    def imbalance(names: list[str], counts: dict[str, int]) -> int:
        total_norm = sum(targets[name].selected_hours for name in names)
        total_count = sum(counts[name] for name in names)
        return sum(
            abs(counts[name] * total_norm - total_count * targets[name].selected_hours)
            for name in names
        )

    dates = [record.date for record in calendar.days]
    evening_pool = eligible_duty_names(schedule.config, calendar, dates, (ShiftType.EVENING,))
    night_pool = eligible_duty_names(schedule.config, calendar, dates, (ShiftType.NIGHT,))
    evening_names = [
        employee.name
        for employee in schedule.config.employees
        if employee.name in evening_pool and targets[employee.name].selected_hours > 0
    ]
    night_names = [
        employee.name
        for employee in schedule.config.employees
        if employee.name in night_pool and targets[employee.name].selected_hours > 0
    ]
    fairness = imbalance(
        evening_names,
        {name: sum(name in day.evening for day in schedule.days) for name in evening_names},
    ) + imbalance(
        night_names, {name: sum(name in day.night for day in schedule.days) for name in night_names}
    )
    weekend_fairness = 0
    off_duty_pool = eligible_duty_names(
        schedule.config,
        calendar,
        sorted(calendar.off_dates()),
        (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT),
    )
    for city in City:
        names = [
            employee.name
            for employee in schedule.config.employees
            if employee.name in off_duty_pool
            and employee.city == city
            and targets[employee.name].selected_hours > 0
        ]
        counts = {
            name: sum(
                name in day.morning + day.evening + day.night
                for day in schedule.days
                if not calendar.is_working(day.date)
            )
            for name in names
        }
        weekend_fairness += imbalance(names, counts)
    return isolated, longest * 100000 + streak_penalty, fairness, weekend_fairness


def optimize_candidate(schedule: Schedule, budget: int = 120) -> Schedule:
    from duty_schedule.scheduler.validation import validate_schedule_result

    best = schedule.model_copy(deep=True)
    best_key = quality_key(best)
    calendar = calendar_for_config(best.config)
    pins = {(pin.date, pin.employee_name) for pin in best.config.pins}
    rng = random.Random(best.config.seed)
    pairs = [
        (a, b)
        for index, a in enumerate(best.config.employees)
        for b in best.config.employees[index + 1 :]
        if a.city == b.city
    ]
    allowed_context = {
        "calendar_unverified",
        "history_missing",
        "history_stale",
        "history_unverified",
        "history_invalid",
        "history_duplicate",
    }
    baseline_codes = {(d.code, d.employee_name, d.date, d.value) for d in best.diagnostics}
    accepted = 0
    for _ in range(budget):
        if not pairs or len(best.days) < 2:
            break
        a, b = rng.choice(pairs)
        i, j = sorted(rng.sample(range(len(best.days)), 2))
        first, second = best.days[i], best.days[j]
        if (calendar.hours(first.date) or 8) != (calendar.hours(second.date) or 8):
            continue
        if any((day.date, employee.name) in pins for day in (first, second) for employee in (a, b)):
            continue
        a_first, b_first = assignment_for(first, a.name), assignment_for(first, b.name)
        a_second, b_second = assignment_for(second, a.name), assignment_for(second, b.name)
        if (
            a_first == b_first
            or a_first != b_second
            or b_first != a_second
            or a_first not in (*WORKING_SHIFTS, ShiftType.DAY_OFF)
            or b_first not in (*WORKING_SHIFTS, ShiftType.DAY_OFF)
            or any(
                day.workday_hours.get(employee.name) is not None
                for day in (first, second)
                for employee in (a, b)
            )
        ):
            continue
        candidate = best.model_copy(deep=True)
        for index in (i, j):
            day = candidate.days[index]
            sa, sb = assignment_for(day, a.name), assignment_for(day, b.name)
            if sa is None or sb is None:
                continue
            getattr(day, sa.value).remove(a.name)
            getattr(day, sb.value).remove(b.name)
            getattr(day, sb.value).append(a.name)
            getattr(day, sa.value).append(b.name)
        candidate_key = quality_key(candidate)
        if candidate_key >= best_key:
            continue
        candidate = validate_schedule_result(candidate)
        codes = {(d.code, d.employee_name, d.date, d.value) for d in candidate.diagnostics}
        if (
            any(d.code not in allowed_context for d in candidate.diagnostics)
            or not codes <= baseline_codes
        ):
            continue
        best, best_key = candidate, candidate_key
        accepted += 1
    logger.debug(
        "postprocess_stage_done",
        stage="lexicographic_swaps",
        changes=accepted,
        quality=list(best_key),
        budget=budget,
    )
    return best
