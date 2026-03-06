from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    VacationPeriod,
)
from duty_schedule.scheduler import generate_schedule


def _make_config(**kwargs) -> Config:
    employees = kwargs.pop("employees", None)
    if employees is None:
        employees = [
            Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(5)
        ] + [
            Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(3)
        ]
    defaults = {"month": 3, "year": 2025, "seed": 42, "employees": employees}
    defaults.update(kwargs)
    return Config(**defaults)


@pytest.mark.system
class TestBusinessRules:
    def test_all_days_covered(self):
        config = _make_config()
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Day {day.date} is not covered"

    def test_moscow_employees_not_on_night(self):
        config = _make_config()
        schedule = generate_schedule(config, set())
        moscow_names = {e.name for e in config.employees if e.city == City.MOSCOW}
        for day in schedule.days:
            for name in day.night:
                assert name not in moscow_names, f"{name} (Moscow) assigned to night on {day.date}"

    def test_khabarovsk_employees_not_on_morning_evening(self):
        config = _make_config()
        schedule = generate_schedule(config, set())
        khb_names = {e.name for e in config.employees if e.city == City.KHABAROVSK}
        for day in schedule.days:
            for name in day.morning + day.evening:
                assert name not in khb_names, (
                    f"{name} (Khabarovsk) assigned to morning/evening on {day.date}"
                )

    def test_vacation_respected(self):
        employees = (
            [
                Employee(
                    name="Отпускник",
                    city=City.MOSCOW,
                    schedule_type=ScheduleType.FLEXIBLE,
                    vacations=[VacationPeriod(start=date(2025, 3, 10), end=date(2025, 3, 15))],
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
        config = _make_config(employees=employees)
        schedule = generate_schedule(config, set())

        for day in schedule.days:
            if date(2025, 3, 10) <= day.date <= date(2025, 3, 15):
                all_working = day.morning + day.evening + day.night + day.workday
                assert "Отпускник" not in all_working, (
                    f"Отпускник assigned on vacation day {day.date}"
                )

    def test_schedule_covers_entire_month(self):
        config = _make_config()
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 31
        assert schedule.days[0].date == date(2025, 3, 1)
        assert schedule.days[-1].date == date(2025, 3, 31)
