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
from duty_schedule.stats import (
    build_assignments,
    compute_stats,
    count_isolated_off,
    count_paired_off,
    max_streak,
)


def _emp(name: str, city: City = City.MOSCOW) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE)


def _min_employees() -> list[Employee]:
    return [
        _emp("A"),
        _emp("B"),
        _emp("M3"),
        _emp("M4"),
        _emp("C", City.KHABAROVSK),
        _emp("D", City.KHABAROVSK),
    ]


def _schedule(days: list[DaySchedule], employees: list[Employee] | None = None) -> Schedule:
    emps = employees or _min_employees()
    config = Config(month=4, year=2026, seed=1, employees=emps)
    return Schedule(config=config, days=days)


class TestBuildAssignments:
    def test_basic_mapping(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), morning=["A"], evening=["B"], night=["C"]),
            DaySchedule(date=date(2026, 4, 2), morning=["B"], evening=["A"], night=["D"]),
        ]
        result = build_assignments(_schedule(days))

        assert result["A"][date(2026, 4, 1)] == "morning"
        assert result["A"][date(2026, 4, 2)] == "evening"
        assert result["B"][date(2026, 4, 1)] == "evening"
        assert result["C"][date(2026, 4, 1)] == "night"

    def test_day_off_and_vacation(self):
        days = [
            DaySchedule(
                date=date(2026, 4, 1),
                morning=["A"],
                evening=["B"],
                night=["C"],
                day_off=["D"],
            ),
        ]
        result = build_assignments(_schedule(days))

        assert result["D"][date(2026, 4, 1)] == "day_off"

    def test_workday_tracked(self):
        days = [
            DaySchedule(
                date=date(2026, 4, 1),
                morning=["A"],
                evening=["B"],
                night=["C"],
                workday=["D"],
            ),
        ]
        result = build_assignments(_schedule(days))

        assert result["D"][date(2026, 4, 1)] == "workday"


class TestCountIsolatedOff:
    def test_single_isolated(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), morning=["A"], evening=[], night=[]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
        ]
        assert count_isolated_off("A", _schedule(days)) == 1

    def test_no_isolated_when_paired(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
        ]
        assert count_isolated_off("A", _schedule(days)) == 0

    def test_edge_first_day_off(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 2), morning=["A"], evening=[], night=[]),
        ]
        assert count_isolated_off("A", _schedule(days)) == 0

    def test_edge_last_day_off(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), morning=["A"], evening=[], night=[]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
        ]
        assert count_isolated_off("A", _schedule(days)) == 0

    def test_vacation_adjacent_not_isolated(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), vacation=["A"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
        ]
        assert count_isolated_off("A", _schedule(days)) == 0


class TestCountPairedOff:
    def test_two_consecutive_off(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
        ]
        assert count_paired_off("A", _schedule(days)) == 1

    def test_single_off_not_paired(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 2), morning=["A"], evening=[], night=[]),
        ]
        assert count_paired_off("A", _schedule(days)) == 0

    def test_vacation_plus_day_off_counts(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), vacation=["A"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
        ]
        assert count_paired_off("A", _schedule(days)) == 1

    def test_two_separate_pairs(self):
        days = [
            DaySchedule(date=date(2026, 4, 1), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 2), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 3), morning=["A"], evening=[], night=[]),
            DaySchedule(date=date(2026, 4, 4), day_off=["A"]),
            DaySchedule(date=date(2026, 4, 5), day_off=["A"]),
        ]
        assert count_paired_off("A", _schedule(days)) == 2


class TestMaxStreak:
    def test_working_streak(self):
        sorted_dates = [date(2026, 4, d) for d in range(1, 6)]
        emp_days = {
            date(2026, 4, 1): "morning",
            date(2026, 4, 2): "evening",
            date(2026, 4, 3): "workday",
            date(2026, 4, 4): "day_off",
            date(2026, 4, 5): "morning",
        }
        assert max_streak(sorted_dates, emp_days, working=True) == 3

    def test_rest_streak(self):
        sorted_dates = [date(2026, 4, d) for d in range(1, 6)]
        emp_days = {
            date(2026, 4, 1): "morning",
            date(2026, 4, 2): "day_off",
            date(2026, 4, 3): "day_off",
            date(2026, 4, 4): "day_off",
            date(2026, 4, 5): "morning",
        }
        assert max_streak(sorted_dates, emp_days, working=False) == 3

    def test_all_working(self):
        sorted_dates = [date(2026, 4, d) for d in range(1, 4)]
        emp_days = dict.fromkeys(sorted_dates, "morning")
        assert max_streak(sorted_dates, emp_days, working=True) == 3

    def test_missing_date_treated_as_day_off(self):
        sorted_dates = [date(2026, 4, d) for d in range(1, 4)]
        emp_days = {date(2026, 4, 1): "morning"}
        assert max_streak(sorted_dates, emp_days, working=False) == 2


class TestComputeStats:
    def test_basic_stats(self):
        days = [
            DaySchedule(
                date=date(2026, 4, 1),
                morning=["A"],
                evening=["B"],
                night=["C"],
                workday=["D"],
            ),
            DaySchedule(
                date=date(2026, 4, 2),
                morning=["B"],
                evening=["A"],
                night=["D"],
                workday=["C"],
            ),
        ]
        schedule = _schedule(days)
        assignments = build_assignments(schedule)
        stats = compute_stats(schedule, assignments, production_days=22)

        stats_a = next(s for s in stats if s.name == "A")
        assert stats_a.morning == 1
        assert stats_a.evening == 1
        assert stats_a.total_working == 2
        assert stats_a.city == "Москва"

        stats_c = next(s for s in stats if s.name == "C")
        assert stats_c.night == 1
        assert stats_c.workday == 1
        assert stats_c.city == "Хабаровск"

    def test_short_days_reduce_hours(self):
        d1 = date(2026, 4, 1)
        d2 = date(2026, 4, 2)
        days = [
            DaySchedule(date=d1, morning=["A"], evening=["B"], night=["C"], workday=["D"]),
            DaySchedule(date=d2, morning=["A"], evening=["B"], night=["C"], workday=["D"]),
        ]
        schedule = _schedule(days)
        assignments = build_assignments(schedule)

        stats_normal = compute_stats(schedule, assignments, production_days=22)
        stats_short = compute_stats(schedule, assignments, production_days=22, short_days={d1})

        a_normal = next(s for s in stats_normal if s.name == "A")
        a_short = next(s for s in stats_short if s.name == "A")

        assert a_normal.total_hours == 16
        assert a_short.total_hours == 15

    def test_weekend_work_counted(self):
        sat = date(2026, 4, 4)
        days = [
            DaySchedule(date=sat, morning=["A"], evening=["B"], night=["C"], day_off=["D"]),
        ]
        schedule = _schedule(days)
        assignments = build_assignments(schedule)
        stats = compute_stats(schedule, assignments, production_days=22)

        stats_a = next(s for s in stats if s.name == "A")
        assert stats_a.weekend_work == 1
