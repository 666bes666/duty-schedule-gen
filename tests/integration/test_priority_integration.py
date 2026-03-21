from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    OptimizationPriority,
    ScheduleType,
)
from duty_schedule.scheduler import generate_schedule
from duty_schedule.scheduler.postprocess.helpers import _count_isolated_off


def _make_config(priority: OptimizationPriority | None = None) -> Config:
    employees = [
        Employee(name=f"Москва {i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 5)
    ] + [
        Employee(name=f"Хабаровск {i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 3)
    ]
    return Config(
        month=4,
        year=2026,
        seed=42,
        employees=employees,
        optimization_priority=priority,
    )


HOLIDAYS: set[date] = set()


class TestPriorityIsolatedWeekends:
    def test_isolated_weekends_not_worse_than_baseline(self):
        baseline = generate_schedule(_make_config(None), HOLIDAYS)
        priority = generate_schedule(_make_config(OptimizationPriority.ISOLATED_WEEKENDS), HOLIDAYS)

        baseline_total = sum(
            _count_isolated_off(emp.name, baseline.days) for emp in baseline.config.employees
        )
        priority_total = sum(
            _count_isolated_off(emp.name, priority.days) for emp in priority.config.employees
        )
        assert priority_total <= baseline_total + 2


class TestPriorityEveningShifts:
    def test_evening_diff_not_worse_than_baseline(self):
        baseline = generate_schedule(_make_config(None), HOLIDAYS)
        priority = generate_schedule(_make_config(OptimizationPriority.EVENING_SHIFTS), HOLIDAYS)

        def _ev_diff(schedule) -> int:
            emps = [e for e in schedule.config.employees if e.city == City.MOSCOW and e.on_duty]
            counts = {e.name: sum(1 for d in schedule.days if e.name in d.evening) for e in emps}
            return max(counts.values()) - min(counts.values()) if counts else 0

        assert _ev_diff(priority) <= _ev_diff(baseline) + 1


class TestPriorityConsecutiveDays:
    def test_max_streak_not_worse_than_baseline(self):
        baseline = generate_schedule(_make_config(None), HOLIDAYS)
        priority = generate_schedule(_make_config(OptimizationPriority.CONSECUTIVE_DAYS), HOLIDAYS)

        def _max_streak_total(schedule) -> int:
            total = 0
            for emp in schedule.config.employees:
                best = cur = 0
                for d in schedule.days:
                    working = (
                        emp.name in d.morning
                        or emp.name in d.evening
                        or emp.name in d.night
                        or emp.name in d.workday
                    )
                    if working:
                        cur += 1
                        best = max(best, cur)
                    else:
                        cur = 0
                total += best
            return total

        assert _max_streak_total(priority) <= _max_streak_total(baseline) + len(
            baseline.config.employees
        )


class TestHardConstraintsPreserved:
    @pytest.mark.parametrize(
        "prio",
        [
            OptimizationPriority.ISOLATED_WEEKENDS,
            OptimizationPriority.EVENING_SHIFTS,
            OptimizationPriority.CONSECUTIVE_DAYS,
            OptimizationPriority.WEEKEND_DAYS,
        ],
    )
    def test_all_shifts_covered(self, prio):
        schedule = generate_schedule(_make_config(prio), HOLIDAYS)
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date} (priority={prio})"

    @pytest.mark.parametrize(
        "prio",
        [
            OptimizationPriority.ISOLATED_WEEKENDS,
            OptimizationPriority.EVENING_SHIFTS,
            OptimizationPriority.CONSECUTIVE_DAYS,
            OptimizationPriority.WEEKEND_DAYS,
        ],
    )
    def test_no_evening_to_morning_violation(self, prio):
        schedule = generate_schedule(_make_config(prio), HOLIDAYS)
        days = schedule.days
        for i in range(len(days) - 1):
            for name in days[i].evening:
                next_day = days[i + 1]
                assert name not in next_day.morning and name not in next_day.workday, (
                    f"Нарушение вечер→утро: {name} "
                    f"{days[i].date} → {next_day.date} (priority={prio})"
                )

    @pytest.mark.parametrize(
        "prio",
        [
            OptimizationPriority.ISOLATED_WEEKENDS,
            OptimizationPriority.EVENING_SHIFTS,
            OptimizationPriority.CONSECUTIVE_DAYS,
            OptimizationPriority.WEEKEND_DAYS,
        ],
    )
    def test_norm_100_percent(self, prio):
        from duty_schedule.scheduler.constraints import _calc_production_days

        config = _make_config(prio)
        schedule = generate_schedule(config, HOLIDAYS)
        prod_days = _calc_production_days(config.year, config.month, HOLIDAYS)
        for emp in config.employees:
            actual = sum(
                1
                for d in schedule.days
                if emp.name in d.morning
                or emp.name in d.evening
                or emp.name in d.night
                or emp.name in d.workday
            )
            assert actual == prod_days, (
                f"{emp.name}: факт={actual}, норма={prod_days} (priority={prio})"
            )
