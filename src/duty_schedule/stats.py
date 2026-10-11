from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from duty_schedule.models import City, Employee, Schedule

HOURS_NORMAL = 8
HOURS_SHORT = 7


@dataclass
class EmployeeStats:
    name: str
    city: str
    total_working: int
    target: int
    morning: int
    evening: int
    night: int
    workday: int
    day_off: int
    vacation: int
    weekend_work: int
    holiday_work: int
    max_streak_work: int
    max_streak_rest: int
    isolated_off: int
    paired_off: int
    total_hours: int = 0
    cost_hours: float = 0.0
    sick_leave: int = 0
    calendar_hours: int = 0
    absence_reduction_hours: int = 0
    adjusted_hours: int = 0
    selected_hours: int = 0
    target_hours: int = 0
    hours_delta: int = 0


def diff_schedules(
    a: Schedule,
    b: Schedule,
) -> list[dict[str, Any]]:
    assign_a = build_assignments(a)
    assign_b = build_assignments(b)
    all_names = sorted(set(assign_a) | set(assign_b))
    all_dates = sorted({d.date for d in a.days} | {d.date for d in b.days})
    diffs: list[dict[str, Any]] = []
    days_a = {day.date: day for day in a.days}
    days_b = {day.date: day for day in b.days}
    for d in all_dates:
        for name in all_names:
            old = assign_a.get(name, {}).get(d, "day_off")
            new = assign_b.get(name, {}).get(d, "day_off")
            old_hours = days_a[d].workday_hours.get(name) if d in days_a else None
            new_hours = days_b[d].workday_hours.get(name) if d in days_b else None
            if old != new or old_hours != new_hours:
                diffs.append(
                    {
                        "date": d.isoformat(),
                        "employee": name,
                        "old_shift": old,
                        "new_shift": new,
                    }
                )
                if old_hours != new_hours:
                    diffs[-1]["old_hours"] = old_hours
                    diffs[-1]["new_hours"] = new_hours
    return diffs


def build_assignments(schedule: Schedule) -> dict[str, dict[date, str]]:
    result: dict[str, dict[date, str]] = {}
    for day in schedule.days:
        mapping = {
            "morning": day.morning,
            "evening": day.evening,
            "night": day.night,
            "workday": day.workday,
            "day_off": day.day_off,
            "vacation": day.vacation,
            "sick_leave": day.sick_leave,
        }
        for shift_key, names in mapping.items():
            for name in names:
                result.setdefault(name, {})[day.date] = shift_key
    return result


def count_isolated_off(emp_name: str, schedule: Schedule) -> int:
    count = 0
    days = schedule.days
    for i, day in enumerate(days):
        if emp_name not in day.day_off:
            continue
        left_ok = (
            i == 0
            or emp_name in days[i - 1].day_off
            or emp_name in days[i - 1].vacation
            or emp_name in days[i - 1].sick_leave
        )
        right_ok = (
            i == len(days) - 1
            or emp_name in days[i + 1].day_off
            or emp_name in days[i + 1].vacation
            or emp_name in days[i + 1].sick_leave
        )
        if not left_ok and not right_ok:
            count += 1
    return count


def count_paired_off(emp_name: str, schedule: Schedule) -> int:
    count = 0
    days = schedule.days
    i = 0
    while i < len(days):
        if (
            emp_name in days[i].day_off
            or emp_name in days[i].vacation
            or emp_name in days[i].sick_leave
        ):
            j = i
            while j < len(days) and (
                emp_name in days[j].day_off
                or emp_name in days[j].vacation
                or emp_name in days[j].sick_leave
            ):
                j += 1
            if j - i >= 2:
                count += 1
            i = j
        else:
            i += 1
    return count


def max_streak(
    sorted_dates: list[date],
    emp_days: dict[date, str],
    working: bool,
) -> int:
    working_keys = {"morning", "evening", "night", "workday"}
    max_s = cur = 0
    for d in sorted_dates:
        key = emp_days.get(d, "day_off")
        is_working = key in working_keys
        if is_working == working:
            cur += 1
            max_s = max(max_s, cur)
        else:
            cur = 0
    return max_s


def compute_stats(
    schedule: Schedule,
    assignments: dict[str, dict[date, str]],
    production_days: int,
    employees: list[Employee] | None = None,
    short_days: set[date] | None = None,
) -> list[EmployeeStats]:
    holiday_dates = {day.date for day in schedule.days if day.is_holiday}
    sorted_dates = sorted(day.date for day in schedule.days)
    _employees = employees if employees is not None else schedule.config.employees

    from duty_schedule.calendar import calendar_for_config
    from duty_schedule.costs import CostModel, compute_cost_hours
    from duty_schedule.workload import assignment_hours, calculate_monthly_targets

    _short = short_days or set()
    calendar = calendar_for_config(schedule.config, holiday_dates)
    if schedule.config.production_calendar is None:
        calendar = calendar.model_copy(deep=True)
        for calendar_day in calendar.days:
            if calendar_day.date in _short and calendar_day.kind != "off":
                calendar_day.kind = "short"
    targets = calculate_monthly_targets(schedule.config, calendar)
    days_by_date = {day.date: day for day in schedule.days}
    _cost_model = CostModel()
    result = []
    for emp in _employees:
        emp_days = assignments.get(emp.name, {})
        city = "Москва" if emp.city == City.MOSCOW else "Хабаровск"

        morning = sum(1 for v in emp_days.values() if v == "morning")
        evening = sum(1 for v in emp_days.values() if v == "evening")
        night = sum(1 for v in emp_days.values() if v == "night")
        workday = sum(1 for v in emp_days.values() if v == "workday")
        day_off = sum(1 for v in emp_days.values() if v == "day_off")
        vacation = sum(1 for v in emp_days.values() if v == "vacation")
        sick_leave = sum(1 for v in emp_days.values() if v == "sick_leave")
        total_working = morning + evening + night + workday

        working_keys = {"morning", "evening", "night", "workday"}

        weekend_work = sum(
            1
            for d, v in emp_days.items()
            if v in working_keys
            and (
                not calendar.is_working(d)
                if schedule.config.production_calendar is not None
                else d.weekday() >= 5
            )
        )

        holiday_work = sum(
            1
            for d, v in emp_days.items()
            if not calendar.is_working(d) and d.weekday() < 5 and v in working_keys
        )

        max_streak_work = max_streak(sorted_dates, emp_days, working=True)
        max_streak_rest = max_streak(sorted_dates, emp_days, working=False)
        isolated_off = count_isolated_off(emp.name, schedule)
        paired_off = count_paired_off(emp.name, schedule)

        total_hours = sum(
            assignment_hours(days_by_date[d], emp.name, calendar)
            for d, v in emp_days.items()
            if v in working_keys
        )

        cost_hours = compute_cost_hours(
            emp.name, schedule, holiday_dates, short_days=_short, model=_cost_model
        )

        result.append(
            EmployeeStats(
                name=emp.name,
                city=city,
                total_working=total_working,
                target=production_days,
                morning=morning,
                evening=evening,
                night=night,
                workday=workday,
                day_off=day_off,
                vacation=vacation,
                weekend_work=weekend_work,
                holiday_work=holiday_work,
                max_streak_work=max_streak_work,
                max_streak_rest=max_streak_rest,
                isolated_off=isolated_off,
                paired_off=paired_off,
                total_hours=total_hours,
                cost_hours=cost_hours,
                sick_leave=sick_leave,
                calendar_hours=targets[emp.name].calendar_hours,
                absence_reduction_hours=targets[emp.name].absence_reduction_hours,
                adjusted_hours=targets[emp.name].adjusted_hours,
                selected_hours=targets[emp.name].selected_hours,
                target_hours=targets[emp.name].selected_hours,
                hours_delta=total_hours - targets[emp.name].selected_hours,
            )
        )
    return result
