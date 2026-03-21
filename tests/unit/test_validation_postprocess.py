from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    PinnedAssignment,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.core import ScheduleError
from duty_schedule.scheduler.postprocess.validation import (
    validate_schedule,
    validate_schedule_or_raise,
)


def _emp(name: str, **kwargs: object) -> Employee:
    defaults: dict[str, object] = {
        "city": City.MOSCOW,
        "schedule_type": ScheduleType.FLEXIBLE,
        "on_duty": True,
    }
    defaults.update(kwargs)
    return Employee(name=name, **defaults)


def _day(d: int, **kwargs: object) -> DaySchedule:
    return DaySchedule(date=date(2026, 4, d), **kwargs)


class TestEveningRest:
    def test_evening_then_morning_is_hard_violation(self):
        days = [
            _day(1, morning=["B"], evening=["A"], night=["C"]),
            _day(2, morning=["A"], evening=["B"], night=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        vs = validate_schedule(days, employees, set())
        hard = [v for v in vs if v.constraint == "evening_rest"]
        assert len(hard) == 1
        assert hard[0].employee == "A"

    def test_evening_then_day_off_is_ok(self):
        days = [
            _day(1, morning=["B"], evening=["A"], night=["C"]),
            _day(2, morning=["B"], evening=["C"], night=["D"], day_off=["A"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]
        vs = validate_schedule(days, employees, set())
        assert not [v for v in vs if v.constraint == "evening_rest"]


class TestCoverage:
    def test_uncovered_day(self):
        days = [_day(1, morning=["A"], evening=["B"])]
        employees = [_emp("A"), _emp("B")]
        vs = validate_schedule(days, employees, set())
        assert any(v.constraint == "coverage" for v in vs)

    def test_covered_day(self):
        days = [_day(1, morning=["A"], evening=["B"], night=["C"])]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        vs = validate_schedule(days, employees, set())
        assert not [v for v in vs if v.constraint == "coverage"]


class TestDuplicates:
    def test_duplicate_in_shifts(self):
        days = [_day(1, morning=["A"], evening=["A"], night=["B"])]
        employees = [_emp("A"), _emp("B")]
        vs = validate_schedule(days, employees, set())
        assert any(v.constraint == "duplicate" for v in vs)


class TestMaxConsecutive:
    def test_streak_exceeds_limit(self):
        days = [_day(i, morning=["A"], evening=["B"], night=["C"]) for i in range(1, 9)]
        employees = [_emp("A", max_consecutive_working=5), _emp("B"), _emp("C")]
        vs = validate_schedule(days, employees, set())
        streak_vs = [
            v for v in vs if v.constraint == "max_consecutive_working" and v.employee == "A"
        ]
        assert len(streak_vs) > 0


class TestScheduleType:
    def test_five_two_on_weekend(self):
        sat = date(2026, 4, 4)
        days = [DaySchedule(date=sat, morning=["B"], evening=["C"], night=["D"], workday=["A"])]
        employees = [
            _emp("A", schedule_type=ScheduleType.FIVE_TWO),
            _emp("B"),
            _emp("C"),
            _emp("D"),
        ]
        vs = validate_schedule(days, employees, set())
        assert any(v.constraint == "five_two_weekend" for v in vs)


class TestShiftRestrictions:
    def test_morning_only_in_evening(self):
        days = [_day(1, morning=["B"], evening=["A"], night=["C"])]
        employees = [_emp("A", morning_only=True), _emp("B"), _emp("C")]
        vs = validate_schedule(days, employees, set())
        assert any(v.constraint == "morning_only" for v in vs)

    def test_evening_only_in_morning(self):
        days = [_day(1, morning=["A"], evening=["B"], night=["C"])]
        employees = [_emp("A", evening_only=True), _emp("B"), _emp("C")]
        vs = validate_schedule(days, employees, set())
        assert any(v.constraint == "evening_only" for v in vs)


class TestBlockedDates:
    def test_working_on_blocked_date(self):
        days = [_day(1, morning=["B"], evening=["C"], night=["D"], workday=["A"])]
        employees = [
            _emp("A", unavailable_dates=[date(2026, 4, 1)]),
            _emp("B"),
            _emp("C"),
            _emp("D"),
        ]
        vs = validate_schedule(days, employees, set())
        blocked = [v for v in vs if v.constraint == "blocked_date"]
        assert len(blocked) == 1
        assert blocked[0].severity == "soft"


class TestPinnedAssignment:
    def test_missing_pin(self):
        days = [_day(1, morning=["B"], evening=["C"], night=["D"], day_off=["A"])]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]
        pins = [PinnedAssignment(date=date(2026, 4, 1), employee_name="A", shift=ShiftType.MORNING)]
        vs = validate_schedule(days, employees, set(), pins=pins)
        assert any(v.constraint == "pinned_assignment" for v in vs)

    def test_present_pin(self):
        days = [_day(1, morning=["A"], evening=["C"], night=["D"])]
        employees = [_emp("A"), _emp("C"), _emp("D")]
        pins = [PinnedAssignment(date=date(2026, 4, 1), employee_name="A", shift=ShiftType.MORNING)]
        vs = validate_schedule(days, employees, set(), pins=pins)
        assert not [v for v in vs if v.constraint == "pinned_assignment"]


class TestValidateOrRaise:
    def test_hard_raises(self):
        days = [
            _day(1, morning=["A"], evening=["A"], night=["B"]),
        ]
        employees = [_emp("A"), _emp("B")]
        with pytest.raises(ScheduleError, match="Hard constraint"):
            validate_schedule_or_raise(days, employees, set())

    def test_soft_only_returns(self):
        days = [_day(i, morning=["A"], evening=["B"], night=["C"]) for i in range(1, 9)]
        employees = [_emp("A", max_consecutive_working=5), _emp("B"), _emp("C")]
        result = validate_schedule_or_raise(days, employees, set())
        assert len(result) > 0
