"""Тесты моделей данных и правил валидации."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    VacationPeriod,
)


class TestVacationPeriod:
    def test_valid(self):
        vp = VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 10))
        assert vp.start < vp.end

    def test_same_day_valid(self):
        vp = VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 1))
        assert vp.start == vp.end

    def test_end_before_start_raises(self):
        with pytest.raises(ValidationError, match="не раньше"):
            VacationPeriod(start=date(2025, 3, 10), end=date(2025, 3, 1))


class TestEmployee:
    def test_valid_on_duty(self):
        emp = Employee(name="Тест", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        assert emp.on_duty is True
        assert emp.morning_only is False

    def test_team_lead_implies_not_on_duty(self):
        with pytest.raises(ValidationError, match="тимлид"):
            Employee(
                name="Тимлид",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                team_lead=True,
                on_duty=True,
            )

    def test_morning_and_evening_only_raises(self):
        with pytest.raises(ValidationError, match="нельзя одновременно"):
            Employee(
                name="Странный",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                morning_only=True,
                evening_only=True,
            )

    def test_morning_only_can_work_morning(self):
        emp = Employee(
            name="Утренний",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            morning_only=True,
        )
        assert emp.can_work_morning() is True
        assert emp.can_work_evening() is False

    def test_evening_only(self):
        emp = Employee(
            name="Вечерний",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            evening_only=True,
        )
        assert emp.can_work_morning() is False
        assert emp.can_work_evening() is True

    def test_is_on_vacation(self):
        emp = Employee(
            name="В отпуске",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 10))],
        )
        assert emp.is_on_vacation(date(2025, 3, 5)) is True
        assert emp.is_on_vacation(date(2025, 3, 1)) is True
        assert emp.is_on_vacation(date(2025, 3, 10)) is True
        assert emp.is_on_vacation(date(2025, 3, 11)) is False
        assert emp.is_on_vacation(date(2025, 2, 28)) is False

    def test_52_does_not_work_weekends(self):
        emp = Employee(
            name="5/2",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FIVE_TWO,
        )
        assert emp.works_on_weekend() is False

    def test_flexible_works_weekends(self):
        emp = Employee(
            name="Гибкий",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
        )
        assert emp.works_on_weekend() is True


class TestConfig:
    def _make_employees(self, moscow: int, khabarovsk: int):
        emps = []
        for i in range(moscow):
            emps.append(
                Employee(
                    name=f"Москва {i}",
                    city=City.MOSCOW,
                    schedule_type=ScheduleType.FLEXIBLE,
                )
            )
        for i in range(khabarovsk):
            emps.append(
                Employee(
                    name=f"Хабаровск {i}",
                    city=City.KHABAROVSK,
                    schedule_type=ScheduleType.FLEXIBLE,
                )
            )
        return emps

    def test_valid_config(self):
        cfg = Config(month=3, year=2025, employees=self._make_employees(4, 2))
        assert cfg.month == 3

    def test_too_few_moscow(self):
        with pytest.raises(ValidationError, match="Москве"):
            Config(month=3, year=2025, employees=self._make_employees(3, 2))

    def test_too_few_khabarovsk(self):
        with pytest.raises(ValidationError, match="Хабаровске"):
            Config(month=3, year=2025, employees=self._make_employees(4, 1))

    def test_invalid_month(self):
        with pytest.raises(ValidationError, match="Месяц"):
            Config(month=13, year=2025, employees=self._make_employees(4, 2))

    def test_invalid_year(self):
        with pytest.raises(ValidationError, match="Год"):
            Config(month=3, year=2023, employees=self._make_employees(4, 2))

    def test_team_lead_not_counted_as_duty(self):
        # Тимлид не считается дежурным → нужны 4 отдельных дежурных
        emps = self._make_employees(4, 2)
        emps.append(
            Employee(
                name="Тимлид",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                team_lead=True,
                on_duty=False,
            )
        )
        cfg = Config(month=3, year=2025, employees=emps)
        assert len(cfg.employees) == 7
