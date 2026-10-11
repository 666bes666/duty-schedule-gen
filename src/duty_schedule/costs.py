from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from duty_schedule.models import Schedule
from duty_schedule.stats import HOURS_NORMAL, HOURS_SHORT, build_assignments
from duty_schedule.workload import assignment_hours


@dataclass
class CostModel:
    night_multiplier: float = 1.2
    holiday_multiplier: float = 2.0
    weekend_multiplier: float = 1.5


def compute_cost_hours(
    emp_name: str,
    schedule: Schedule,
    holidays: set[date],
    short_days: set[date] | None = None,
    model: CostModel | None = None,
) -> float:
    m = model or CostModel()
    _short = short_days or set()
    working_keys = {"morning", "evening", "night", "workday"}
    assignments = build_assignments(schedule)
    emp_days = assignments.get(emp_name, {})
    calendar = schedule.config.production_calendar
    days_by_date = {day.date: day for day in schedule.days}

    total = 0.0
    for d, shift_key in emp_days.items():
        if shift_key not in working_keys:
            continue
        base_hours = (
            assignment_hours(days_by_date[d], emp_name, calendar)
            if calendar is not None
            else days_by_date[d].workday_hours.get(
                emp_name, HOURS_SHORT if d in _short else HOURS_NORMAL
            )
        )
        multiplier = 1.0
        if shift_key == "night":
            multiplier *= m.night_multiplier
        is_holiday = d in holidays
        is_weekend = d.weekday() >= 5
        if calendar is not None:
            is_weekend = not calendar.is_working(d) and d.weekday() >= 5
            is_holiday = not calendar.is_working(d) and d.weekday() < 5
        if is_holiday:
            multiplier *= m.holiday_multiplier
        elif is_weekend:
            multiplier *= m.weekend_multiplier
        total += base_hours * multiplier

    return round(total, 1)
