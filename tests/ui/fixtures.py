from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from duty_schedule.models import (
    CalendarDay,
    CarryOverState,
    City,
    Config,
    DaySchedule,
    Employee,
    PinnedAssignment,
    ProductionCalendar,
    ScheduleType,
    ShiftType,
)


def journey_config() -> Config:
    employees = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(4)
    ] + [
        Employee(name=f"K{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(2)
    ]
    dates = [date(2026, 4, number) for number in range(1, 31)]
    working = {day for day in dates if day.weekday() < 5}
    working = set(sorted(working)[:16]) | {date(2026, 4, 4)}
    snapshot = ProductionCalendar(
        year=2026,
        month=4,
        days=[CalendarDay(date=day, kind="working" if day in working else "off") for day in dates],
        source="offline_test_fixture",
        fetched_at=datetime(2026, 3, 25, tzinfo=UTC),
    )
    config = Config(
        month=4,
        year=2026,
        employees=employees,
        production_calendar=snapshot,
        carry_over=[
            CarryOverState(
                employee_name=employee.name,
                employee_id=employee.employee_id,
                last_shift=ShiftType.DAY_OFF,
                consecutive_off=1,
                as_of=date(2026, 3, 31),
                source="manual",
            )
            for employee in employees
        ],
    )
    days = journey_days(config)
    config.pins = [
        PinnedAssignment(date=day.date, employee_name=name, shift=shift)
        for day in days
        for shift in (
            ShiftType.MORNING,
            ShiftType.EVENING,
            ShiftType.NIGHT,
            ShiftType.WORKDAY,
            ShiftType.DAY_OFF,
        )
        for name in getattr(day, shift.value)
    ]
    return config


def journey_days(config: Config) -> list[DaySchedule]:
    workdays = {
        "M0": {2, 6},
        "M1": {4, 8},
        "M2": {3, 7},
        "M3": {9, 13},
        "K0": {2, 4},
        "K1": {1, 3},
    }
    days = []
    for index in range(30):
        day = date(2026, 4, 1) + timedelta(days=index)
        morning = [["M0"], ["M2"], ["M1"], ["M3"]][index % 4]
        evening = [["M1"], ["M3"], ["M0"], ["M2"]][index % 4]
        night = [f"K{index % 2}"]
        workday = [name for name, selected in workdays.items() if day.day in selected]
        assigned = set(morning + evening + night + workday)
        days.append(
            DaySchedule(
                date=day,
                is_holiday=not config.production_calendar.is_working(day),
                morning=morning,
                evening=evening,
                night=night,
                workday=workday,
                day_off=[
                    employee.name for employee in config.employees if employee.name not in assigned
                ],
            )
        )
    return days
