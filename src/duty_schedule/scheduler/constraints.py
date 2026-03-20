from __future__ import annotations

import calendar
from datetime import date

from duty_schedule.constants import (
    MAX_CONSECUTIVE_OFF_DEFAULT,
    MAX_CONSECUTIVE_WORKING_DEFAULT,
)
from duty_schedule.models import (
    DaySchedule,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.core import EmployeeState

MAX_CONSECUTIVE_WORKING = MAX_CONSECUTIVE_WORKING_DEFAULT
MAX_CONSECUTIVE_WORKING_FLEX = MAX_CONSECUTIVE_WORKING_DEFAULT
MAX_CONSECUTIVE_OFF = MAX_CONSECUTIVE_OFF_DEFAULT


def _max_cw(emp: Employee) -> int:
    if emp.max_consecutive_working is not None:
        return emp.max_consecutive_working
    return MAX_CONSECUTIVE_WORKING


def _max_cw_postprocess(emp: Employee) -> int:
    if emp.max_consecutive_working is not None:
        return emp.max_consecutive_working
    if (
        emp.schedule_type == ScheduleType.FLEXIBLE
        and emp.on_duty
        and not (emp.morning_only or emp.evening_only or emp.always_on_duty)
    ):
        return MAX_CONSECUTIVE_WORKING_FLEX
    return MAX_CONSECUTIVE_WORKING


def _max_co(emp: Employee) -> int:
    return MAX_CONSECUTIVE_OFF


def _max_co_postprocess(emp: Employee) -> int:
    if (
        emp.schedule_type == ScheduleType.FLEXIBLE
        and emp.on_duty
        and not (emp.morning_only or emp.evening_only or emp.always_on_duty)
    ):
        return MAX_CONSECUTIVE_OFF + 1
    return MAX_CONSECUTIVE_OFF


def _duty_only(emp: Employee) -> bool:
    return emp.on_duty and (emp.morning_only or emp.evening_only or emp.always_on_duty)


def _shift_limit_reached(emp: Employee, state: EmployeeState, shift: ShiftType) -> bool:
    return False


def _consecutive_shift_count_at(
    emp_name: str, idx: int, days: list[DaySchedule], shift_attr: str
) -> int:
    count = 1
    for i in range(idx - 1, -1, -1):
        if emp_name in getattr(days[i], shift_attr):
            count += 1
        else:
            break
    for i in range(idx + 1, len(days)):
        if emp_name in getattr(days[i], shift_attr):
            count += 1
        else:
            break
    return count


def _is_weekend_or_holiday(day: date, holidays: set[date]) -> bool:
    return day.weekday() >= 5 or day in holidays


def _had_evening_before(
    emp_name: str,
    idx: int,
    days: list[DaySchedule],
    carry_over_last_shift: dict[str, ShiftType] | None = None,
) -> bool:
    if idx > 0:
        return emp_name in days[idx - 1].evening
    if carry_over_last_shift:
        return carry_over_last_shift.get(emp_name) == ShiftType.EVENING
    return False


def _can_work(
    emp: Employee,
    state: EmployeeState,
    day: date,
    holidays: set[date],
) -> bool:
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
    return state.last_shift == ShiftType.EVENING


def _calc_production_days(year: int, month: int, holidays: set[date]) -> int:
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        if day.weekday() < 5 and day not in holidays:
            count += 1
    return count


def _calc_blocked_working_days(emp: Employee, year: int, month: int) -> int:
    _, days_in_month = calendar.monthrange(year, month)
    count = 0
    for d in range(1, days_in_month + 1):
        day = date(year, month, d)
        if day.weekday() < 5 and emp.is_on_vacation(day):
            count += 1
    return count


def _is_working_on_day(emp_name: str, day: DaySchedule) -> bool:
    return (
        emp_name in day.morning
        or emp_name in day.evening
        or emp_name in day.night
        or emp_name in day.workday
    )
