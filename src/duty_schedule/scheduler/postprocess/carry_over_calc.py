from __future__ import annotations

from duty_schedule.models import DaySchedule, Employee, ShiftType
from duty_schedule.scheduler.constraints import _is_working_on_day


def _get_shift_type(emp_name: str, day: DaySchedule) -> ShiftType | None:
    if emp_name in day.morning:
        return ShiftType.MORNING
    if emp_name in day.evening:
        return ShiftType.EVENING
    if emp_name in day.night:
        return ShiftType.NIGHT
    if emp_name in day.workday:
        return ShiftType.WORKDAY
    if emp_name in day.vacation:
        return ShiftType.VACATION
    if emp_name in day.day_off:
        return ShiftType.DAY_OFF
    return None


def compute_carry_over(
    days: list[DaySchedule],
    employees: list[Employee],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []

    for emp in employees:
        last_shift: ShiftType | None = None
        consecutive_working = 0
        consecutive_off = 0
        consecutive_same_shift = 0
        same_shift_done = False

        for day in reversed(days):
            shift = _get_shift_type(emp.name, day)
            working = _is_working_on_day(emp.name, day)

            if last_shift is None:
                last_shift = shift
                if working:
                    consecutive_working = 1
                    consecutive_same_shift = 1
                else:
                    consecutive_off = 1
                continue

            if working and consecutive_working > 0:
                consecutive_working += 1
                if not same_shift_done and shift == last_shift:
                    consecutive_same_shift += 1
                else:
                    same_shift_done = True
            elif not working and consecutive_off > 0:
                consecutive_off += 1
            else:
                break

        result.append(
            {
                "employee_name": emp.name,
                "last_shift": str(last_shift) if last_shift else None,
                "consecutive_working": consecutive_working,
                "consecutive_off": consecutive_off,
                "consecutive_same_shift": consecutive_same_shift,
            }
        )

    return result
