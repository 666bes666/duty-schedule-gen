from __future__ import annotations

from duty_schedule.models import CarryOverState, DaySchedule, Employee, ShiftType
from duty_schedule.scheduler.rules import WORKING_SHIFTS, assignment_for, matches_employee


def _get_shift_type(emp_name: str, day: DaySchedule) -> ShiftType | None:
    return assignment_for(day, emp_name)


def compute_carry_over(
    days: list[DaySchedule],
    employees: list[Employee],
    initial_history: list[CarryOverState] | None = None,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for employee in employees:
        initial = next(
            (
                carry
                for carry in (initial_history or [])
                if matches_employee(carry.employee_name, carry.employee_id, employee)
            ),
            None,
        )
        working = initial.consecutive_working if initial else 0
        off = initial.consecutive_off if initial else 0
        same = initial.consecutive_same_shift if initial else 0
        last = initial.last_shift if initial else None
        for day in sorted(days, key=lambda item: item.date):
            shift = assignment_for(day, employee.name)
            if shift in WORKING_SHIFTS:
                working += 1
                off = 0
                same = same + 1 if shift == last else 1
            else:
                working = 0
                same = 0
                off += 1
            last = shift
        results.append(
            {
                "employee_name": employee.name,
                "employee_id": employee.employee_id,
                "last_shift": str(last) if last else None,
                "consecutive_working": working,
                "consecutive_off": off,
                "consecutive_same_shift": same,
                "as_of": max(day.date for day in days).isoformat() if days else None,
                "source": "schedule",
                "no_previous_shifts": False,
            }
        )
    return results
