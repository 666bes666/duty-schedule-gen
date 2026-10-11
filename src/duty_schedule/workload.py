from __future__ import annotations

from duty_schedule.models import Config, DaySchedule, MonthlyTarget, ProductionCalendar


def calculate_monthly_targets(
    config: Config, calendar: ProductionCalendar
) -> dict[str, MonthlyTarget]:
    if (calendar.year, calendar.month) != (config.year, config.month):
        raise ValueError("Период календаря не совпадает с периодом планирования")
    calendar_hours = sum(calendar.hours(day.date) for day in calendar.days)
    targets: dict[str, MonthlyTarget] = {}
    for employee in config.employees:
        reduction = sum(
            calendar.hours(day.date)
            for day in calendar.days
            if employee.is_on_vacation(day.date) or employee.is_on_sick_leave(day.date)
        )
        choices = [
            choice
            for choice in config.norm_choices
            if (choice.year, choice.month) == (config.year, config.month)
            and (
                choice.employee_id == employee.employee_id
                if choice.employee_id
                else choice.employee_name == employee.name
            )
        ]
        if len(choices) > 1:
            raise ValueError(f"Несколько выбранных норм для {employee.name}")
        mode = choices[0].mode if choices else "adjusted"
        adjusted = max(0, calendar_hours - reduction)
        targets[employee.name] = MonthlyTarget(
            calendar_hours=calendar_hours,
            absence_reduction_hours=reduction,
            adjusted_hours=adjusted,
            selected_hours=calendar_hours if mode == "full" else adjusted,
            mode=mode,
        )
    return targets


def assignment_hours(day: DaySchedule, name: str, calendar: ProductionCalendar) -> int:
    if name in day.workday:
        return day.workday_hours.get(name, calendar.hours(day.date) or 8)
    if name in day.morning or name in day.evening or name in day.night:
        return calendar.hours(day.date) or 8
    return 0
