from __future__ import annotations

from datetime import date

from duty_schedule.costs import CostModel, compute_cost_hours
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)


def _make_schedule(days_data: list[dict]) -> Schedule:
    emps = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True)
        for i in range(1, 5)
    ] + [
        Employee(
            name=f"K{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE, on_duty=True
        )
        for i in range(1, 3)
    ]
    days = []
    for dd in days_data:
        days.append(DaySchedule(**dd))
    config = Config(month=3, year=2026, employees=emps)
    return Schedule(config=config, days=days)


def test_basic_cost_no_multipliers() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 2),
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": ["M3"],
                "day_off": ["M4", "K2"],
            }
        ]
    )
    cost = compute_cost_hours("M1", schedule, holidays=set())
    assert cost == 8.0


def test_night_multiplier() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 2),
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": ["M3"],
                "day_off": ["M4", "K2"],
            }
        ]
    )
    cost = compute_cost_hours("K1", schedule, holidays=set())
    assert cost == 9.6


def test_weekend_multiplier() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 7),
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": [],
                "day_off": ["M3", "M4", "K2"],
            }
        ]
    )
    cost = compute_cost_hours("M1", schedule, holidays=set())
    assert cost == 12.0


def test_holiday_multiplier() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 2),
                "is_holiday": True,
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": [],
                "day_off": ["M3", "M4", "K2"],
            }
        ]
    )
    holidays = {date(2026, 3, 2)}
    cost = compute_cost_hours("M1", schedule, holidays=holidays)
    assert cost == 16.0


def test_night_on_holiday() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 2),
                "is_holiday": True,
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": [],
                "day_off": ["M3", "M4", "K2"],
            }
        ]
    )
    holidays = {date(2026, 3, 2)}
    cost = compute_cost_hours("K1", schedule, holidays=holidays)
    assert cost == 19.2


def test_custom_model() -> None:
    schedule = _make_schedule(
        [
            {
                "date": date(2026, 3, 2),
                "morning": ["M1"],
                "evening": ["M2"],
                "night": ["K1"],
                "workday": ["M3"],
                "day_off": ["M4", "K2"],
            }
        ]
    )
    model = CostModel(night_multiplier=1.5, holiday_multiplier=3.0, weekend_multiplier=2.0)
    cost = compute_cost_hours("K1", schedule, holidays=set(), model=model)
    assert cost == 12.0
