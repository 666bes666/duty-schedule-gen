from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from duty_schedule.models import Schedule
from duty_schedule.stats import HOURS_NORMAL, HOURS_SHORT, build_assignments


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

    total = 0.0
    for d, shift_key in emp_days.items():
        if shift_key not in working_keys:
            continue
        base_hours = HOURS_SHORT if d in _short else HOURS_NORMAL
        multiplier = 1.0
        if shift_key == "night":
            multiplier *= m.night_multiplier
        is_holiday = d in holidays
        is_weekend = d.weekday() >= 5
        if is_holiday:
            multiplier *= m.holiday_multiplier
        elif is_weekend:
            multiplier *= m.weekend_multiplier
        total += base_hours * multiplier

    return round(total, 1)
