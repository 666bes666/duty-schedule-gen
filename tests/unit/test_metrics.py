from __future__ import annotations

from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType
from duty_schedule.scheduler.postprocess.metrics import ScheduleSnapshot, compute_snapshot


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


class TestScheduleSnapshot:
    def test_score_zero_when_perfect(self):
        snap = ScheduleSnapshot(
            evening_balance=0,
            isolated_off_total=0,
            isolated_off_max=0,
            max_streak=0,
            norm_deviation_total=0,
            weekend_balance=0,
        )
        assert snap.score() == 0.0

    def test_score_increases_with_imbalance(self):
        a = ScheduleSnapshot(0, 0, 0, 0, 0, 0)
        b = ScheduleSnapshot(2, 3, 1, 6, 0, 1)
        assert b.score() > a.score()


class TestComputeSnapshot:
    def test_basic_snapshot(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["C"], workday=["D"]),
            _day(2, morning=["B"], evening=["A"], night=["C"], day_off=["D"]),
            _day(3, morning=["A"], evening=["B"], night=["C"], workday=["D"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]
        snap = compute_snapshot(days, employees, set())
        assert isinstance(snap, ScheduleSnapshot)
        assert snap.evening_balance >= 0
        assert snap.max_streak >= 0

    def test_evening_balance(self):
        days = [
            _day(1, morning=["B"], evening=["A"], night=["C"]),
            _day(2, morning=["B"], evening=["A"], night=["C"]),
            _day(3, morning=["A"], evening=["B"], night=["C"]),
        ]
        employees = [
            _emp("A"),
            _emp("B"),
            _emp("C", city=City.KHABAROVSK),
        ]
        snap = compute_snapshot(days, employees, set())
        assert snap.evening_balance == 1

    def test_norm_deviation(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["C"]),
            _day(2, morning=["A"], evening=["B"], night=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        target = {"A": 1, "B": 1, "C": 1}
        snap = compute_snapshot(days, employees, set(), target_working=target)
        assert snap.norm_deviation_total == 3

    def test_empty_schedule(self):
        employees = [_emp("A")]
        snap = compute_snapshot([], employees, set())
        assert snap.score() == 0.0

    def test_carry_over_increases_max_streak(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["C"]),
            _day(2, morning=["A"], evening=["B"], night=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        snap_no_co = compute_snapshot(days, employees, set())
        snap_with_co = compute_snapshot(days, employees, set(), carry_over_cw={"A": 5})
        assert snap_with_co.max_streak > snap_no_co.max_streak

    def test_target_working_produces_nonzero_deviation(self):
        days = [
            _day(1, morning=["A"], evening=["B"], night=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        snap_no_target = compute_snapshot(days, employees, set())
        snap_with_target = compute_snapshot(
            days, employees, set(), target_working={"A": 10, "B": 10, "C": 10}
        )
        assert snap_no_target.norm_deviation_total == 0
        assert snap_with_target.norm_deviation_total > 0
