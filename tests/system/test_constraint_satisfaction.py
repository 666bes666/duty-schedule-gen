from __future__ import annotations

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler import generate_schedule


@pytest.mark.system
class TestConstraintSatisfaction:
    def _make_config(self, employees=None) -> Config:
        if employees is None:
            employees = [
                Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(5)
            ] + [
                Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(3)
            ]
        return Config(month=3, year=2025, seed=42, employees=employees)

    def test_morning_only_no_evening(self):
        employees = (
            [
                Employee(
                    name="Утренний",
                    city=City.MOSCOW,
                    schedule_type=ScheduleType.FLEXIBLE,
                    morning_only=True,
                ),
            ]
            + [
                Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(4)
            ]
            + [
                Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(2)
            ]
        )
        config = self._make_config(employees)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert "Утренний" not in day.evening

    def test_evening_only_no_morning(self):
        employees = (
            [
                Employee(
                    name="Вечерний",
                    city=City.MOSCOW,
                    schedule_type=ScheduleType.FLEXIBLE,
                    evening_only=True,
                ),
            ]
            + [
                Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(4)
            ]
            + [
                Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(2)
            ]
        )
        config = self._make_config(employees)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert "Вечерний" not in day.morning

    def test_52_employees_no_weekend_duty(self):
        employees = (
            [
                Employee(
                    name="Пятидневка",
                    city=City.MOSCOW,
                    schedule_type=ScheduleType.FIVE_TWO,
                    on_duty=False,
                ),
            ]
            + [
                Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(4)
            ]
            + [
                Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
                for i in range(2)
            ]
        )
        config = self._make_config(employees)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            if day.date.weekday() >= 5:
                all_working = day.morning + day.evening + day.night + day.workday
                assert "Пятидневка" not in all_working, (
                    f"5/2 employee working on weekend {day.date}"
                )
