from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
)

try:
    from ortools.sat.python import cp_model  # noqa: F401

    _HAS_ORTOOLS = True
except ImportError:
    _HAS_ORTOOLS = False

pytestmark = pytest.mark.skipif(not _HAS_ORTOOLS, reason="ortools not installed")


def _make_config() -> Config:
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
    return Config(month=3, year=2026, employees=emps, seed=42, solver="cpsat")


def test_solver_produces_schedule() -> None:
    from duty_schedule.scheduler.solver import solve_schedule

    config = _make_config()
    holidays = {date(2026, 3, 8)}
    schedule = solve_schedule(config, holidays)
    assert len(schedule.days) == 31
    assert schedule.metadata.get("solver") == "cpsat"


def test_solver_covers_shifts() -> None:
    from duty_schedule.scheduler.solver import solve_schedule

    config = _make_config()
    holidays: set[date] = set()
    schedule = solve_schedule(config, holidays)
    for day in schedule.days:
        assert len(day.morning) >= 1, f"No morning on {day.date}"
        assert len(day.evening) >= 1, f"No evening on {day.date}"
        assert len(day.night) >= 1, f"No night on {day.date}"


def test_solver_respects_city() -> None:
    from duty_schedule.scheduler.solver import solve_schedule

    config = _make_config()
    holidays: set[date] = set()
    schedule = solve_schedule(config, holidays)
    for day in schedule.days:
        for name in day.night:
            assert name.startswith("K"), f"Moscow employee {name} on night shift"
        for name in day.morning + day.evening:
            assert name.startswith("M"), f"Khabarovsk employee {name} on morning/evening"
