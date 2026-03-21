from __future__ import annotations

from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType, ShiftType
from duty_schedule.scheduler.postprocess.carry_over_calc import compute_carry_over


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


class TestComputeCarryOver:
    def test_consecutive_working_from_end(self):
        days = [
            _day(1, day_off=["A"]),
            _day(2, morning=["A"]),
            _day(3, evening=["A"]),
            _day(4, workday=["A"]),
        ]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["employee_name"] == "A"
        assert result[0]["consecutive_working"] == 3
        assert result[0]["consecutive_off"] == 0
        assert result[0]["last_shift"] == str(ShiftType.WORKDAY)

    def test_consecutive_off_from_end(self):
        days = [
            _day(1, morning=["A"]),
            _day(2, day_off=["A"]),
            _day(3, day_off=["A"]),
        ]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_off"] == 2
        assert result[0]["consecutive_working"] == 0
        assert result[0]["last_shift"] == str(ShiftType.DAY_OFF)

    def test_consecutive_same_shift(self):
        days = [
            _day(1, day_off=["A"]),
            _day(2, evening=["A"]),
            _day(3, evening=["A"]),
            _day(4, evening=["A"]),
        ]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_same_shift"] == 3
        assert result[0]["consecutive_working"] == 3
        assert result[0]["last_shift"] == str(ShiftType.EVENING)

    def test_mixed_shifts_break_same_shift(self):
        days = [
            _day(1, morning=["A"]),
            _day(2, evening=["A"]),
            _day(3, morning=["A"]),
            _day(4, morning=["A"]),
        ]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_same_shift"] == 2
        assert result[0]["consecutive_working"] == 4
        assert result[0]["last_shift"] == str(ShiftType.MORNING)

    def test_multiple_employees(self):
        days = [
            _day(1, morning=["A"], day_off=["B"]),
            _day(2, morning=["A"], evening=["B"]),
            _day(3, day_off=["A"], evening=["B"]),
        ]
        employees = [_emp("A"), _emp("B")]
        result = compute_carry_over(days, employees)
        a = next(r for r in result if r["employee_name"] == "A")
        b = next(r for r in result if r["employee_name"] == "B")
        assert a["consecutive_off"] == 1
        assert a["consecutive_working"] == 0
        assert b["consecutive_working"] == 2
        assert b["consecutive_same_shift"] == 2

    def test_vacation_counts_as_off(self):
        days = [
            _day(1, morning=["A"]),
            _day(2, vacation=["A"]),
            _day(3, vacation=["A"]),
        ]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_off"] == 2
        assert result[0]["last_shift"] == str(ShiftType.VACATION)

    def test_night_shift(self):
        days = [
            _day(1, day_off=["A"]),
            _day(2, night=["A"]),
            _day(3, night=["A"]),
        ]
        employees = [_emp("A", city=City.KHABAROVSK)]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_working"] == 2
        assert result[0]["consecutive_same_shift"] == 2
        assert result[0]["last_shift"] == str(ShiftType.NIGHT)

    def test_empty_days(self):
        employees = [_emp("A")]
        result = compute_carry_over([], employees)
        assert result[0]["consecutive_working"] == 0
        assert result[0]["consecutive_off"] == 0
        assert result[0]["last_shift"] is None
        assert result[0]["consecutive_same_shift"] == 0

    def test_single_day_working(self):
        days = [_day(1, morning=["A"])]
        employees = [_emp("A")]
        result = compute_carry_over(days, employees)
        assert result[0]["consecutive_working"] == 1
        assert result[0]["consecutive_same_shift"] == 1
        assert result[0]["last_shift"] == str(ShiftType.MORNING)
