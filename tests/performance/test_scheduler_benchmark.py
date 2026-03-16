from __future__ import annotations

import pytest

pytest.importorskip("pytest_benchmark")

from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.scheduler import generate_schedule


def _make_config(moscow: int = 5, khabarovsk: int = 3) -> Config:
    employees = [
        Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(moscow)
    ] + [
        Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(khabarovsk)
    ]
    return Config(month=3, year=2025, seed=42, employees=employees)


@pytest.mark.benchmark
class TestSchedulerBenchmark:
    def test_generate_minimal_team(self, benchmark):
        config = _make_config(4, 2)
        benchmark(generate_schedule, config, set())

    def test_generate_standard_team(self, benchmark):
        config = _make_config(5, 3)
        benchmark(generate_schedule, config, set())

    def test_generate_large_team(self, benchmark):
        config = _make_config(10, 5)
        benchmark(generate_schedule, config, set())
