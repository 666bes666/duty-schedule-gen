from datetime import UTC, date, datetime

from duty_schedule.models import (
    CalendarDay,
    Config,
    DaySchedule,
    NormChoice,
    ProductionCalendar,
    VacationPeriod,
)
from duty_schedule.workload import assignment_hours, calculate_monthly_targets


def month_calendar():
    return ProductionCalendar(
        year=2026,
        month=4,
        days=[
            CalendarDay(
                date=date(2026, 4, d),
                kind="short" if d == 30 else "off" if d == 1 else "working",
            )
            for d in range(1, 31)
        ],
        source="fixture",
        fetched_at=datetime.now(UTC),
    )


def test_norm_deducts_union_of_working_absences_only(minimal_employees):
    employee = minimal_employees[0]
    employee.vacations = [VacationPeriod(start=date(2026, 4, 1), end=date(2026, 4, 3))]
    employee.sick_leaves = [VacationPeriod(start=date(2026, 4, 3), end=date(2026, 4, 4))]
    employee.unavailable_dates = [date(2026, 4, 5)]
    config = Config(year=2026, month=4, employees=minimal_employees)
    target = calculate_monthly_targets(config, month_calendar())[employee.name]
    assert target.calendar_hours == 231
    assert target.absence_reduction_hours == 24
    assert target.adjusted_hours == target.selected_hours == 207


def test_full_norm_choice_is_period_specific(minimal_employees):
    employee = minimal_employees[0]
    employee.sick_leaves = [VacationPeriod(start=date(2026, 4, 30), end=date(2026, 4, 30))]
    config = Config(
        year=2026,
        month=4,
        employees=minimal_employees,
        norm_choices=[NormChoice(employee_name=employee.name, year=2026, month=4, mode="full")],
    )
    target = calculate_monthly_targets(config, month_calendar())[employee.name]
    assert target.adjusted_hours == 224
    assert target.selected_hours == 231
    config.norm_choices[0].month = 3
    assert calculate_monthly_targets(config, month_calendar())[employee.name].selected_hours == 224


def test_assignment_hours_share_short_and_individual_workday_model():
    calendar = month_calendar()
    day = DaySchedule(date=date(2026, 4, 30), night=["N"], workday=["R"], workday_hours={"R": 3})
    assert assignment_hours(day, "N", calendar) == 7
    assert assignment_hours(day, "R", calendar) == 3
    assert assignment_hours(day, "missing", calendar) == 0
    off_duty = DaySchedule(date=date(2026, 4, 1), morning=["M"])
    assert assignment_hours(off_duty, "M", calendar) == 8
