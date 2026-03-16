from __future__ import annotations

from datetime import date

from duty_schedule.models import City, DaySchedule, Employee, ScheduleType
from duty_schedule.scheduler.postprocess import (
    _balance_duty_shifts,
    _balance_evening_shifts,
    _balance_weekend_work,
)


def _emp(name: str, **kwargs) -> Employee:
    defaults = {
        "city": City.MOSCOW,
        "schedule_type": ScheduleType.FLEXIBLE,
        "on_duty": True,
    }
    defaults.update(kwargs)
    return Employee(name=name, **defaults)


def _day(d: int, morning: list[str], evening: list[str], **kwargs) -> DaySchedule:
    return DaySchedule(
        date=date(2026, 4, d), morning=list(morning), evening=list(evening), **kwargs
    )


class TestBalanceEveningShifts:
    def test_evening_imbalance_resolved(self):
        days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["C"], evening=["A"]),
            _day(5, morning=["B"], evening=["A"]),
            _day(7, morning=["C"], evening=["A"]),
            _day(9, morning=["B"], evening=["A"]),
            _day(11, morning=["C"], evening=["A"]),
            _day(13, morning=["A"], evening=["B"]),
            _day(15, morning=["A"], evening=["C"]),
        ]

        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_evening_shifts(days, employees)

        counts = {e.name: sum(1 for d in result if e.name in d.evening) for e in employees}
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_morning_only_excluded(self):
        days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["B"], evening=["A"]),
            _day(5, morning=["B"], evening=["A"]),
        ]

        employees = [
            _emp("A"),
            _emp("B", morning_only=True),
            _emp("C"),
        ]
        result = _balance_evening_shifts(days, employees)

        assert all("B" not in d.evening for d in result)

    def test_pinned_not_swapped(self):
        days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["B"], evening=["A"]),
            _day(5, morning=["B"], evening=["A"]),
        ]

        employees = [_emp("A"), _emp("B")]
        pinned = {(date(2026, 4, d), "A") for d in (1, 3, 5)}
        result = _balance_evening_shifts(days, employees, pinned_on=pinned)

        counts_a = sum(1 for d in result if "A" in d.evening)
        assert counts_a == 3

    def test_next_day_constraint(self):
        days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(2, morning=["B"], evening=["A"]),
            _day(3, morning=["B"], evening=["A"]),
        ]

        employees = [_emp("A"), _emp("B")]
        result = _balance_evening_shifts(days, employees)

        for d in result:
            for name in d.evening:
                nxt = next(
                    (
                        r
                        for r in result
                        if r.date == d.date + __import__("datetime").timedelta(days=1)
                    ),
                    None,
                )
                if nxt:
                    assert name not in nxt.morning, f"{name} evening {d.date} -> morning {nxt.date}"

    def test_already_balanced_noop(self):
        days = [
            _day(1, morning=["B"], evening=["A"]),
            _day(3, morning=["A"], evening=["B"]),
        ]

        employees = [_emp("A"), _emp("B")]
        original_evenings = {d.date: list(d.evening) for d in days}
        result = _balance_evening_shifts(days, employees)

        for d in result:
            assert d.evening == original_evenings[d.date]

    def test_evening_workday_swap(self):
        days = [
            _day(1, morning=["C"], evening=["A"], workday=["B"]),
            _day(3, morning=["C"], evening=["A"], workday=["B"]),
            _day(5, morning=["C"], evening=["A"], workday=["B"]),
            _day(7, morning=["C"], evening=["B"], workday=["A"]),
        ]

        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_evening_shifts(days, employees)

        counts = {e.name: sum(1 for d in result if e.name in d.evening) for e in employees}
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_evening_workday_swap_blocked_by_next_day(self):
        days = [
            _day(1, morning=["C"], evening=["A"], workday=["B"]),
            _day(2, morning=["C"], evening=["A"], workday=["B"]),
        ]

        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_evening_shifts(days, employees)

        assert "A" in result[0].evening
        assert "A" in result[1].evening

    def test_evening_workday_swap_blocked_by_prev_evening(self):
        days = [
            _day(4, morning=["C"], evening=["A"], workday=["B"]),
            _day(5, morning=["C"], evening=["A"], workday=["B"]),
        ]

        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_evening_shifts(days, employees)

        swapped_day5 = "B" in result[1].evening
        if swapped_day5:
            assert "A" not in result[0].evening


class TestBalanceDutyShifts:
    def test_duty_imbalance_resolved(self):
        days = [
            _day(1, morning=["A"], evening=["B"], workday=["C"]),
            _day(3, morning=["A"], evening=["B"], workday=["C"]),
            _day(5, morning=["A"], evening=["B"], workday=["C"]),
            _day(7, morning=["B"], evening=["C"], workday=["A"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        result = _balance_duty_shifts(days, employees, set())

        duty_counts = {}
        for e in employees:
            duty_counts[e.name] = sum(
                1 for d in result if e.name in d.morning or e.name in d.evening or e.name in d.night
            )
        assert max(duty_counts.values()) - min(duty_counts.values()) <= 1

    def test_already_balanced_noop(self):
        days = [
            _day(1, morning=["A"], evening=["B"], workday=["C"]),
            _day(3, morning=["B"], evening=["C"], workday=["A"]),
            _day(5, morning=["C"], evening=["A"], workday=["B"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        original = {d.date: (list(d.morning), list(d.evening)) for d in days}
        result = _balance_duty_shifts(days, employees, set())

        for d in result:
            assert (d.morning, d.evening) == original[d.date]

    def test_pinned_not_swapped(self):
        days = [
            _day(1, morning=["A"], evening=["B"], workday=["C"]),
            _day(3, morning=["A"], evening=["B"], workday=["C"]),
            _day(5, morning=["A"], evening=["B"], workday=["C"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C")]
        pinned = frozenset({(date(2026, 4, d), "A") for d in (1, 3, 5)})
        result = _balance_duty_shifts(days, employees, set(), pinned_on=pinned)

        for d in result:
            assert "A" in d.morning


class TestBalanceWeekendWork:
    def test_weekend_balance(self):
        sat1 = date(2026, 4, 4)
        sun1 = date(2026, 4, 5)
        sat2 = date(2026, 4, 11)
        sun2 = date(2026, 4, 12)
        days = [
            DaySchedule(date=sat1, morning=["A"], evening=["B"], day_off=["C", "D"]),
            DaySchedule(date=sun1, morning=["A"], evening=["B"], day_off=["C", "D"]),
            DaySchedule(date=sat2, morning=["A"], evening=["B"], day_off=["C", "D"]),
            DaySchedule(date=sun2, morning=["A"], evening=["B"], day_off=["C", "D"]),
        ]
        employees = [_emp("A"), _emp("B"), _emp("C"), _emp("D")]

        result = _balance_weekend_work(days, employees)

        weekend_counts: dict[str, int] = {}
        for e in employees:
            weekend_counts[e.name] = sum(
                1 for d in result if e.name in d.morning or e.name in d.evening
            )
        assert max(weekend_counts.values()) - min(weekend_counts.values()) <= 1

    def test_no_weekends_noop(self):
        days = [
            _day(1, morning=["A"], evening=["B"]),
            _day(3, morning=["A"], evening=["B"]),
        ]
        employees = [_emp("A"), _emp("B")]
        original_mornings = [list(d.morning) for d in days]
        result = _balance_weekend_work(days, employees)
        for i, d in enumerate(result):
            assert d.morning == original_mornings[i]
