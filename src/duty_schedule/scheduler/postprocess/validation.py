from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from duty_schedule.models import (
    DaySchedule,
    Employee,
    PinnedAssignment,
    ScheduleType,
)
from duty_schedule.scheduler.constraints import (
    _is_working_on_day,
    _max_cw,
)
from duty_schedule.scheduler.core import ScheduleError


@dataclass(frozen=True)
class ConstraintViolation:
    employee: str
    date: date | None
    constraint: str
    detail: str
    severity: Literal["hard", "soft"]


def validate_schedule(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pins: list[PinnedAssignment] | None = None,
    carry_over_cw: dict[str, int] | None = None,
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    emp_by_name = {e.name: e for e in employees}

    violations.extend(_check_evening_rest(days))
    violations.extend(_check_coverage(days))
    violations.extend(_check_duplicates(days))
    violations.extend(_check_max_consecutive(days, employees, carry_over_cw))
    violations.extend(_check_schedule_type(days, employees, holidays))
    violations.extend(_check_shift_restrictions(days, employees))
    violations.extend(_check_blocked_dates(days, employees))
    if pins:
        violations.extend(_check_pinned(days, pins, emp_by_name))

    return violations


def validate_schedule_or_raise(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pins: list[PinnedAssignment] | None = None,
    carry_over_cw: dict[str, int] | None = None,
) -> list[ConstraintViolation]:
    violations = validate_schedule(days, employees, holidays, pins, carry_over_cw)
    hard = [v for v in violations if v.severity == "hard"]
    if hard:
        details = "; ".join(f"{v.employee} @ {v.date}: {v.detail}" for v in hard[:5])
        raise ScheduleError(f"Hard constraint violations ({len(hard)}): {details}")
    return violations


def _check_evening_rest(days: list[DaySchedule]) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for i in range(len(days) - 1):
        for emp_name in days[i].evening:
            if emp_name in days[i + 1].morning or emp_name in days[i + 1].workday:
                result.append(
                    ConstraintViolation(
                        employee=emp_name,
                        date=days[i].date,
                        constraint="evening_rest",
                        detail=(f"evening {days[i].date} → morning/workday {days[i + 1].date}"),
                        severity="hard",
                    )
                )
    return result


def _check_coverage(days: list[DaySchedule]) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for d in days:
        if not d.is_covered():
            result.append(
                ConstraintViolation(
                    employee="",
                    date=d.date,
                    constraint="coverage",
                    detail="not all shifts covered",
                    severity="hard",
                )
            )
    return result


def _check_duplicates(days: list[DaySchedule]) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for d in days:
        assigned = d.all_assigned()
        seen: set[str] = set()
        for name in assigned:
            if name in seen:
                result.append(
                    ConstraintViolation(
                        employee=name,
                        date=d.date,
                        constraint="duplicate",
                        detail="assigned to multiple working shifts",
                        severity="hard",
                    )
                )
            seen.add(name)
    return result


def _check_max_consecutive(
    days: list[DaySchedule],
    employees: list[Employee],
    carry_over_cw: dict[str, int] | None,
) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for emp in employees:
        limit = _max_cw(emp)
        streak = carry_over_cw.get(emp.name, 0) if carry_over_cw else 0
        for d in days:
            if _is_working_on_day(emp.name, d):
                streak += 1
                if streak > limit:
                    result.append(
                        ConstraintViolation(
                            employee=emp.name,
                            date=d.date,
                            constraint="max_consecutive_working",
                            detail=f"streak {streak} > limit {limit}",
                            severity="soft",
                        )
                    )
            else:
                streak = 0
    return result


def _check_schedule_type(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for emp in employees:
        if emp.schedule_type != ScheduleType.FIVE_TWO:
            continue
        for d in days:
            is_weekend = d.date.weekday() >= 5 or d.date in holidays
            if is_weekend and _is_working_on_day(emp.name, d):
                result.append(
                    ConstraintViolation(
                        employee=emp.name,
                        date=d.date,
                        constraint="five_two_weekend",
                        detail="5/2 employee working on weekend/holiday",
                        severity="hard",
                    )
                )
    return result


def _check_shift_restrictions(
    days: list[DaySchedule],
    employees: list[Employee],
) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for emp in employees:
        for d in days:
            if emp.morning_only and emp.name in d.evening:
                result.append(
                    ConstraintViolation(
                        employee=emp.name,
                        date=d.date,
                        constraint="morning_only",
                        detail="morning_only employee in evening shift",
                        severity="hard",
                    )
                )
            if emp.evening_only and emp.name in d.morning:
                result.append(
                    ConstraintViolation(
                        employee=emp.name,
                        date=d.date,
                        constraint="evening_only",
                        detail="evening_only employee in morning shift",
                        severity="hard",
                    )
                )
    return result


def _check_blocked_dates(
    days: list[DaySchedule],
    employees: list[Employee],
) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    for emp in employees:
        for d in days:
            if emp.is_blocked(d.date) and _is_working_on_day(emp.name, d):
                result.append(
                    ConstraintViolation(
                        employee=emp.name,
                        date=d.date,
                        constraint="blocked_date",
                        detail="working on blocked/vacation date",
                        severity="soft",
                    )
                )
    return result


def _check_pinned(
    days: list[DaySchedule],
    pins: list[PinnedAssignment],
    emp_by_name: dict[str, Employee],
) -> list[ConstraintViolation]:
    result: list[ConstraintViolation] = []
    day_by_date = {d.date: d for d in days}
    for pin in pins:
        d = day_by_date.get(pin.date)
        if d is None:
            continue
        shift_attr = pin.shift.value
        assigned_list: list[str] = getattr(d, shift_attr, [])
        if pin.employee_name not in assigned_list:
            result.append(
                ConstraintViolation(
                    employee=pin.employee_name,
                    date=pin.date,
                    constraint="pinned_assignment",
                    detail=f"not in {shift_attr} as pinned",
                    severity="hard",
                )
            )
    return result
