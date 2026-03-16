from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)
from duty_schedule.stats import diff_schedules


def _make_employees() -> list[Employee]:
    return [
        Employee(
            name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True
        )
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


def _make_schedule(morning: list[str], evening: list[str]) -> Schedule:
    emps = _make_employees()
    days = [
        DaySchedule(
            date=date(2026, 3, 2),
            morning=morning,
            evening=evening,
            night=["K1"],
            workday=["M3"],
            day_off=["M4", "K2"],
        ),
    ]
    config = Config(month=3, year=2026, employees=emps)
    return Schedule(config=config, days=days)


def test_identical_schedules() -> None:
    a = _make_schedule(morning=["M1"], evening=["M2"])
    b = _make_schedule(morning=["M1"], evening=["M2"])
    assert diff_schedules(a, b) == []


def test_single_change() -> None:
    a = _make_schedule(morning=["M1"], evening=["M2"])
    b = _make_schedule(morning=["M2"], evening=["M1"])
    diffs = diff_schedules(a, b)
    assert len(diffs) == 2
    names = {d["employee"] for d in diffs}
    assert names == {"M1", "M2"}


def test_diff_contains_correct_shifts() -> None:
    a = _make_schedule(morning=["M1"], evening=["M2"])
    b = _make_schedule(morning=["M2"], evening=["M1"])
    diffs = diff_schedules(a, b)
    m1_diff = next(d for d in diffs if d["employee"] == "M1")
    assert m1_diff["old_shift"] == "morning"
    assert m1_diff["new_shift"] == "evening"
    assert m1_diff["date"] == "2026-03-02"
