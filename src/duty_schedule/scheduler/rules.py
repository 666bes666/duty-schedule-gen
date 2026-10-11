from __future__ import annotations

from datetime import date
from typing import Literal

from duty_schedule.models import (
    CarryOverState,
    City,
    Config,
    DaySchedule,
    Employee,
    ProductionCalendar,
    RuleApproval,
    ScheduleType,
    ShiftType,
)

WORKING_SHIFTS = (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY)
ALL_SHIFTS = (*WORKING_SHIFTS, ShiftType.DAY_OFF, ShiftType.VACATION, ShiftType.SICK_LEAVE)


def matches_employee(name: str, employee_id: str | None, employee: Employee) -> bool:
    return employee_id == employee.employee_id if employee_id else name == employee.name


def carry_for_employee(config: Config, employee: Employee) -> CarryOverState | None:
    return next(
        (
            carry
            for carry in config.carry_over
            if matches_employee(carry.employee_name, carry.employee_id, employee)
        ),
        None,
    )


def approval_for(
    config: Config,
    employee: Employee,
    day: date,
    rule: Literal["working_streak", "weekly_day_off", "individual_workday"],
    value: int | None = None,
) -> RuleApproval | None:
    for approval in config.approvals:
        if (
            approval.date != day
            or approval.rule != rule
            or not matches_employee(approval.employee_name, approval.employee_id, employee)
        ):
            continue
        if rule == "working_streak" and (
            value is None or approval.value is None or not value <= approval.value <= 7
        ):
            continue
        if rule == "individual_workday" and approval.value != value:
            continue
        return approval
    return None


def normal_streak_limit(employee: Employee) -> int:
    return min(employee.max_consecutive_working or 6, 6)


def assignment_for(day: DaySchedule, name: str) -> ShiftType | None:
    return next((shift for shift in ALL_SHIFTS if name in getattr(day, shift.value)), None)


def can_assign_work(
    config: Config,
    calendar: ProductionCalendar,
    employee: Employee,
    day: date,
    shift: ShiftType,
    previous_shift: ShiftType | None,
    previous_streak: int,
    allow_pending: bool = False,
) -> bool:
    if employee.is_blocked(day) or previous_streak >= 7:
        return False
    if employee.schedule_type == ScheduleType.FIVE_TWO and not calendar.is_working(day):
        return False
    if shift == ShiftType.WORKDAY and not calendar.is_working(day):
        return False
    if previous_shift == ShiftType.EVENING and shift in (ShiftType.MORNING, ShiftType.WORKDAY):
        return False
    if shift in (ShiftType.MORNING, ShiftType.EVENING):
        if employee.city != City.MOSCOW or not employee.on_duty:
            return False
        if shift == ShiftType.MORNING and employee.evening_only:
            return False
        if shift == ShiftType.EVENING and employee.morning_only:
            return False
    if shift == ShiftType.NIGHT and (employee.city != City.KHABAROVSK or not employee.on_duty):
        return False
    if (
        shift == ShiftType.WORKDAY
        and employee.on_duty
        and (employee.morning_only or employee.evening_only or employee.always_on_duty)
    ):
        return False
    if (
        employee.is_day_off_weekly(day)
        and not allow_pending
        and approval_for(config, employee, day, "weekly_day_off") is None
    ):
        return False
    return not (
        previous_streak + 1 > normal_streak_limit(employee)
        and not allow_pending
        and approval_for(config, employee, day, "working_streak", previous_streak + 1) is None
    )
