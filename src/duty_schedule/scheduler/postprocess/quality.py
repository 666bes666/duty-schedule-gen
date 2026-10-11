from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import date
from fractions import Fraction

from duty_schedule.calendar import calendar_for_config
from duty_schedule.logging import get_logger
from duty_schedule.models import Config, ProductionCalendar, Schedule, ShiftType
from duty_schedule.scheduler.rules import (
    WORKING_SHIFTS,
    assignment_for,
    can_assign_work,
    carry_for_employee,
)

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


def quality_key(schedule: Schedule) -> tuple[int, int, Fraction, Fraction, int]:
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

    from duty_schedule.quality_history import balance_counts, balance_pools, weighted_imbalance

    pools = balance_pools(schedule.config)
    values = {
        name: weighted_imbalance(balance_counts(schedule, pool), pool["weights"])
        for name, pool in pools.items()
    }
    preference = sum(
        employee.preferred_shift is not None
        and assignment_for(day, employee.name) in WORKING_SHIFTS
        and assignment_for(day, employee.name) != employee.preferred_shift
        for day in schedule.days
        for employee in schedule.config.employees
    )
    return (
        isolated,
        longest * 100000 + streak_penalty,
        values["evening"] + values["night"],
        values["off_moscow"] + values["off_khabarovsk"],
        preference,
    )


def optimize_candidate(
    schedule: Schedule, budget: int = 120, baseline: Schedule | None = None
) -> Schedule:
    from duty_schedule.scheduler.validation import validate_schedule_result

    best = schedule.model_copy(deep=True)
    best_key = (len(changed_cells(baseline, best)) if baseline else 0, *quality_key(best))
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
        candidate_key = (
            len(changed_cells(baseline, candidate)) if baseline else 0,
            *quality_key(candidate),
        )
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
        quality=[float(value) for value in best_key],
        budget=budget,
    )
    best.metadata["optimization"] = optimization_provenance(schedule, best, "lexicographic_swaps")
    return best


def optimization_provenance(before: Schedule, after: Schedule, algorithm: str) -> dict:
    from duty_schedule.workload import assignment_hours

    def snapshot(schedule: Schedule) -> dict:
        calendar = calendar_for_config(schedule.config)
        return {
            "revision_id": schedule.revision_id or None,
            "days": {
                str(day.date): {
                    employee.employee_id: [
                        assignment_for(day, employee.name),
                        assignment_hours(day, employee.name, calendar),
                    ]
                    for employee in schedule.config.employees
                }
                for day in schedule.days
            },
        }

    first, last = snapshot(before), snapshot(after)
    last["revision_id"] = None
    changes = [
        {
            "date": day,
            "employee_id": identity,
            "before": values,
            "after": last["days"].get(day, {}).get(identity),
        }
        for day, employees in first["days"].items()
        for identity, values in employees.items()
        if values != last["days"].get(day, {}).get(identity)
    ]
    return {
        "status": "changes" if changes else "no_changes",
        "algorithm": algorithm,
        "before": first,
        "after": last,
        "changed_cells": len(changes),
        "changes": changes,
        "quality_labels": [
            "isolated_rest",
            "working_streaks",
            "evening_night_balance",
            "off_duty_balance",
            "preference_penalty",
        ],
        "quality_before": [float(value) for value in quality_key(before)],
        "quality_after": [float(value) for value in quality_key(after)],
        "optimality": "bounded_search",
    }


def schedule_cells(schedule: Schedule) -> dict:
    from duty_schedule.workload import assignment_hours

    calendar = calendar_for_config(schedule.config)
    return {
        (day.date, employee.employee_id): (
            assignment_for(day, employee.name),
            assignment_hours(day, employee.name, calendar),
        )
        for day in schedule.days
        for employee in schedule.config.employees
    }


def changed_cells(before: Schedule, after: Schedule) -> list[dict]:
    first, last = schedule_cells(before), schedule_cells(after)
    return [
        {
            "date": str(day),
            "employee_id": identity,
            "before": first.get((day, identity)),
            "after": last.get((day, identity)),
        }
        for day, identity in sorted(first.keys() | last.keys())
        if first.get((day, identity)) != last.get((day, identity))
    ]


def repair_metadata(before: Schedule, after: Schedule, optimality: str) -> dict:
    changes = changed_cells(before, after)
    return {
        "baseline_id": before.revision_id or None,
        "changed_cells": len(changes),
        "changes": changes,
        "search_status": after.search_status,
        "optimality": optimality,
    }
