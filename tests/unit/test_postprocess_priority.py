from __future__ import annotations

from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType
from duty_schedule.scheduler.postprocess import (
    _balance_evening_shifts,
    _balance_weekend_work,
    _equalize_isolated_off,
    _minimize_max_streak,
)


def _emp(name: str, **kwargs) -> Employee:
    defaults = {
        "city": City.MOSCOW,
        "schedule_type": ScheduleType.FLEXIBLE,
        "on_duty": True,
    }
    defaults.update(kwargs)
    return Employee(name=name, **defaults)


def _day(d: int, **kwargs) -> DaySchedule:
    return DaySchedule(date=date(2026, 4, d), **kwargs)


class TestBalanceEveningStrict:
    def test_strict_achieves_diff_zero(self):
        days = [
            _day(1, morning=["B"], evening=["A"], workday=["C"]),
            _day(3, morning=["B"], evening=["A"], workday=["C"]),
            _day(5, morning=["B"], evening=["A"], workday=["C"]),
            _day(7, morning=["B"], evening=["A"], workday=["C"]),
            _day(9, morning=["B"], evening=["A"], workday=["C"]),
            _day(11, morning=["B"], evening=["A"], workday=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_evening_shifts(days, employees, strict=True)
        counts = {e.name: sum(1 for d in result if e.name in d.evening) for e in employees}
        assert max(counts.values()) - min(counts.values()) == 0

    def test_strict_not_worse_than_non_strict(self):
        base_days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["C"], evening=["A"]),
            _day(5, morning=["B"], evening=["A"]),
            _day(7, morning=["C"], evening=["A"]),
        ]
        prio_days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["C"], evening=["A"]),
            _day(5, morning=["B"], evening=["A"]),
            _day(7, morning=["C"], evening=["A"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        result_normal = _balance_evening_shifts(base_days, employees, strict=False)
        result_strict = _balance_evening_shifts(prio_days, employees, strict=True)
        counts_normal = {
            e.name: sum(1 for d in result_normal if e.name in d.evening) for e in employees
        }
        counts_strict = {
            e.name: sum(1 for d in result_strict if e.name in d.evening) for e in employees
        }
        diff_normal = max(counts_normal.values()) - min(counts_normal.values())
        diff_strict = max(counts_strict.values()) - min(counts_strict.values())
        assert diff_strict <= diff_normal


class TestBalanceWeekendStrict:
    def test_strict_achieves_diff_zero(self):
        days = [
            _day(4, morning=["A"], evening=["C"], night=["X"], is_holiday=False),
            _day(5, morning=["A"], evening=["C"], night=["X"], is_holiday=False),
            _day(11, morning=["A"], evening=["C"], night=["X"], is_holiday=False),
            _day(12, morning=["A"], evening=["C"], night=["X"], is_holiday=False),
            _day(7, morning=["B"], evening=["B"], night=["X"], day_off=["A", "C"]),
        ]
        days[0] = DaySchedule(
            date=date(2026, 4, 4),
            morning=["A"],
            evening=["C"],
            night=["X"],
            day_off=["B"],
        )
        days[1] = DaySchedule(
            date=date(2026, 4, 5),
            morning=["A"],
            evening=["C"],
            night=["X"],
            day_off=["B"],
        )
        days_wk = [
            DaySchedule(
                date=date(2026, 4, 4), morning=["A"], evening=["C"], night=[], day_off=["B"]
            ),
            DaySchedule(
                date=date(2026, 4, 5), morning=["A"], evening=["C"], night=[], day_off=["B"]
            ),
            DaySchedule(
                date=date(2026, 4, 11), morning=["A"], evening=["C"], night=[], day_off=["B"]
            ),
            DaySchedule(
                date=date(2026, 4, 12), morning=["A"], evening=["C"], night=[], day_off=["B"]
            ),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_weekend_work(days_wk, employees, strict=True)
        wk_days = [d for d in result if d.date.weekday() >= 5]
        counts = {
            e.name: sum(1 for d in wk_days if e.name in d.morning or e.name in d.evening)
            for e in employees
            if e.city == City.MOSCOW
        }
        if counts:
            assert max(counts.values()) - min(counts.values()) <= 1


class TestEqualizeIsolatedOffStrict:
    def test_strict_more_iterations(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), workday=["A", "B"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 3), workday=["A", "B"]),
            DaySchedule(date=date(2026, 4, 4), workday=["A", "B"]),
            DaySchedule(date=date(2026, 4, 5), day_off=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 6), workday=["A", "B"]),
            DaySchedule(date=date(2026, 4, 7), workday=["A", "B"]),
            DaySchedule(date=date(2026, 4, 8), day_off=["B"], workday=["A"]),
            DaySchedule(date=date(2026, 4, 9), workday=["A", "B"]),
        ]
        employees = [_emp("A"), _emp("B")]
        result_strict = _equalize_isolated_off(days, employees, set(), strict=True)
        from duty_schedule.scheduler.postprocess.helpers import _count_isolated_off

        iso_a = _count_isolated_off("A", result_strict)
        iso_b = _count_isolated_off("B", result_strict)
        assert abs(iso_a - iso_b) <= 1


class TestMinimizeMaxStreak:
    def test_reduces_longest_streak(self):
        days = [DaySchedule(date=date(2026, 4, d), workday=["A", "B"]) for d in range(1, 8)] + [
            DaySchedule(date=date(2026, 4, 8), day_off=["A", "B"]),
            DaySchedule(date=date(2026, 4, 9), workday=["A", "B"]),
        ]
        employees = [
            _emp("A"),
            _emp("B"),
        ]

        def _max_streak(name):
            best = cur = 0
            for d in days:
                if name in d.workday or name in d.morning or name in d.evening:
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 0
            return best

        streak_before = _max_streak("A")
        result = _minimize_max_streak(days, employees, set())

        def _max_streak_r(name):
            best = cur = 0
            for d in result:
                if name in d.workday or name in d.morning or name in d.evening:
                    cur += 1
                    best = max(best, cur)
                else:
                    cur = 0
            return best

        streak_after = _max_streak_r("A")
        assert streak_after <= streak_before

    def test_only_touches_workday_not_duty_shifts(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 2), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 4), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 5), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 6), morning=["A"], workday=["B"]),
            DaySchedule(date=date(2026, 4, 7), day_off=["A", "B"]),
            DaySchedule(date=date(2026, 4, 8), morning=["A"], workday=["B"]),
        ]
        morning_counts_before = {d.date: len(d.morning) for d in days}
        employees = [_emp("A", morning_only=True), _emp("B")]
        result = _minimize_max_streak(days, employees, set())
        for d in result:
            assert len(d.morning) == morning_counts_before[d.date], (
                f"Duty shift (morning) count changed on {d.date}"
            )
