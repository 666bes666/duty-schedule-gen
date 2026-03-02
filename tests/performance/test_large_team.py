from __future__ import annotations

import time

import pytest

from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.scheduler import generate_schedule


@pytest.mark.benchmark
class TestLargeTeam:
    def test_20_employees_completes(self):
        employees = [
            Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(14)
        ] + [
            Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(6)
        ]
        config = Config(month=3, year=2025, seed=42, employees=employees)

        start = time.monotonic()
        schedule = generate_schedule(config, set())
        elapsed = time.monotonic() - start

        assert len(schedule.days) == 31
        assert elapsed < 30

    def test_25_employees_completes(self):
        employees = [
            Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(17)
        ] + [
            Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(8)
        ]
        config = Config(month=6, year=2025, seed=42, employees=employees)

        start = time.monotonic()
        schedule = generate_schedule(config, set())
        elapsed = time.monotonic() - start

        assert len(schedule.days) == 30
        assert elapsed < 60
