from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType
from duty_schedule.scheduler.constraints import (
    _is_working_on_day,
)
from duty_schedule.scheduler.postprocess.helpers import _count_isolated_off


@dataclass(frozen=True)
class ScheduleSnapshot:
    evening_balance: int
    isolated_off_total: int
    isolated_off_max: int
    max_streak: int
    norm_deviation_total: int
    weekend_balance: int

    def score(self) -> float:
        return (
            self.evening_balance * 3.0
            + self.isolated_off_total * 2.0
            + self.isolated_off_max * 1.5
            + self.max_streak * 1.0
            + self.norm_deviation_total * 2.5
            + self.weekend_balance * 1.5
        )


def compute_snapshot(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    target_working: dict[str, int] | None = None,
    carry_over_cw: dict[str, int] | None = None,
) -> ScheduleSnapshot:
    moscow_duty = [
        e
        for e in employees
        if e.city == City.MOSCOW
        and e.on_duty
        and e.schedule_type == ScheduleType.FLEXIBLE
        and not e.morning_only
        and not e.evening_only
        and not e.always_on_duty
    ]

    ev_counts = {e.name: sum(1 for d in days if e.name in d.evening) for e in moscow_duty}
    evening_balance = max(ev_counts.values()) - min(ev_counts.values()) if ev_counts else 0

    flex_emps = [e for e in employees if e.schedule_type == ScheduleType.FLEXIBLE]
    iso_counts = {e.name: _count_isolated_off(e.name, days) for e in flex_emps}
    isolated_off_total = sum(iso_counts.values())
    isolated_off_max = max(iso_counts.values()) if iso_counts else 0

    max_streak = 0
    for emp in employees:
        streak = carry_over_cw.get(emp.name, 0) if carry_over_cw else 0
        for d in days:
            if _is_working_on_day(emp.name, d):
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

    norm_deviation_total = 0
    if target_working:
        for emp in employees:
            actual = sum(1 for d in days if _is_working_on_day(emp.name, d))
            target = target_working.get(emp.name, actual)
            norm_deviation_total += abs(actual - target)

    weekend_days = [d for d in days if d.date.weekday() >= 5]
    duty_emps = [e for e in employees if e.on_duty]
    if duty_emps and weekend_days:
        wk_counts = {
            e.name: sum(1 for d in weekend_days if _is_working_on_day(e.name, d)) for e in duty_emps
        }
        weekend_balance = max(wk_counts.values()) - min(wk_counts.values())
    else:
        weekend_balance = 0

    return ScheduleSnapshot(
        evening_balance=evening_balance,
        isolated_off_total=isolated_off_total,
        isolated_off_max=isolated_off_max,
        max_streak=max_streak,
        norm_deviation_total=norm_deviation_total,
        weekend_balance=weekend_balance,
    )
