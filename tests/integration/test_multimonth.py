from __future__ import annotations

from datetime import date
from unittest.mock import patch

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler.multimonth import generate_multimonth
from tests.conftest import complete_config
from tests.contract.conftest import production_calendar


def _make_config(month: int = 3, year: int = 2026) -> Config:
    emps = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True)
        for i in range(1, 5)
    ] + [
        Employee(
            name=f"K{i}",
            city=City.KHABAROVSK,
            schedule_type=ScheduleType.FLEXIBLE,
            on_duty=True,
        )
        for i in range(1, 3)
    ]
    return complete_config(Config(month=month, year=year, employees=emps, seed=42))


def _mock_holidays(year: int, month: int) -> tuple[set[date], set[date]]:
    import calendar

    _, ndays = calendar.monthrange(year, month)
    holidays = {
        date(year, month, d) for d in range(1, ndays + 1) if date(year, month, d).weekday() >= 5
    }
    return holidays, set()


def test_multimonth_two_months() -> None:
    config = _make_config()
    with patch(
        "duty_schedule.scheduler.multimonth.fetch_production_calendar",
        side_effect=production_calendar,
    ):
        schedules = generate_multimonth(config, 3, 2026, 4, 2026)
    assert len(schedules) == 2
    assert schedules[0].config.month == 3
    assert schedules[1].config.month == 4
    assert all(schedule.status == "ready" for schedule in schedules)


def test_multimonth_single_month() -> None:
    config = _make_config()
    with patch(
        "duty_schedule.scheduler.multimonth.fetch_production_calendar",
        side_effect=production_calendar,
    ):
        schedules = generate_multimonth(config, 3, 2026, 3, 2026)
    assert len(schedules) == 1
    assert schedules[0].status == "ready"


def test_multimonth_cross_year() -> None:
    config = _make_config(month=12)
    with patch(
        "duty_schedule.scheduler.multimonth.fetch_production_calendar",
        side_effect=production_calendar,
    ):
        schedules = generate_multimonth(config, 12, 2026, 1, 2027)
    assert len(schedules) == 2
    assert schedules[0].config.month == 12
    assert schedules[0].config.year == 2026
    assert schedules[1].config.month == 1
    assert schedules[1].config.year == 2027
    assert all(schedule.status == "ready" for schedule in schedules)
