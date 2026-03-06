from __future__ import annotations

import pytest

from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.scheduler import generate_schedule


def _make_config(seed: int = 42) -> Config:
    employees = [
        Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(5)
    ] + [
        Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(3)
    ]
    return Config(month=3, year=2025, seed=seed, employees=employees)


@pytest.mark.system
class TestDeterminism:
    def test_same_seed_same_result(self):
        config = _make_config(seed=42)
        s1 = generate_schedule(config, set())
        s2 = generate_schedule(config, set())

        for d1, d2 in zip(s1.days, s2.days, strict=True):
            assert d1.morning == d2.morning
            assert d1.evening == d2.evening
            assert d1.night == d2.night
            assert d1.workday == d2.workday

    def test_different_seed_different_result(self):
        s1 = generate_schedule(_make_config(seed=1), set())
        s2 = generate_schedule(_make_config(seed=999), set())

        differs = False
        for d1, d2 in zip(s1.days, s2.days, strict=True):
            if d1.morning != d2.morning or d1.evening != d2.evening:
                differs = True
                break
        assert differs, "Different seeds produced identical schedules"

    def test_multiple_runs_deterministic(self):
        config = _make_config(seed=123)
        results = [generate_schedule(config, set()) for _ in range(5)]

        for run in results[1:]:
            for d_first, d_run in zip(results[0].days, run.days, strict=True):
                assert d_first.morning == d_run.morning
                assert d_first.evening == d_run.evening
                assert d_first.night == d_run.night
