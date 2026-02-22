"""Общие фикстуры для тестов."""

from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
)


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
    on_duty: bool = True,
    morning_only: bool = False,
    evening_only: bool = False,
    team_lead: bool = False,
    vacations: list | None = None,
) -> Employee:
    return Employee(
        name=name,
        city=city,
        schedule_type=schedule_type,
        on_duty=on_duty,
        morning_only=morning_only,
        evening_only=evening_only,
        team_lead=team_lead,
        vacations=vacations or [],
    )


@pytest.fixture
def moscow_employees() -> list[Employee]:
    """4 дежурных сотрудника в Москве."""
    return [
        _emp("Иванов Иван", City.MOSCOW),
        _emp("Петров Пётр", City.MOSCOW),
        _emp("Сидоров Сидор", City.MOSCOW),
        _emp("Козлов Коля", City.MOSCOW),
    ]


@pytest.fixture
def khabarovsk_employees() -> list[Employee]:
    """2 дежурных сотрудника в Хабаровске."""
    return [
        _emp("Дальнев Дмитрий", City.KHABAROVSK),
        _emp("Востоков Виктор", City.KHABAROVSK),
    ]


@pytest.fixture
def minimal_employees(moscow_employees, khabarovsk_employees) -> list[Employee]:
    """Минимальная команда: 4 Москва + 2 Хабаровск."""
    return moscow_employees + khabarovsk_employees


@pytest.fixture
def full_employees() -> list[Employee]:
    """Полная команда с разными атрибутами."""
    return [
        # Москва — дежурные
        _emp("Иванов Иван", City.MOSCOW),
        _emp("Петров Пётр", City.MOSCOW),
        _emp("Сидоров Сидор", City.MOSCOW),
        _emp("Козлов Коля", City.MOSCOW, morning_only=True),
        _emp("Морозов Михаил", City.MOSCOW, evening_only=True),
        # Москва — тимлид (не дежурный)
        _emp("Новиков Николай", City.MOSCOW, team_lead=True, on_duty=False),
        # Москва — 5/2 (не дежурный)
        _emp("Волков Владимир", City.MOSCOW, schedule_type=ScheduleType.FIVE_TWO, on_duty=False),
        # Хабаровск — дежурные
        _emp("Дальнев Дмитрий", City.KHABAROVSK),
        _emp("Востоков Виктор", City.KHABAROVSK),
    ]


@pytest.fixture
def minimal_config(minimal_employees) -> Config:
    return Config(
        month=3,
        year=2025,
        seed=42,
        employees=minimal_employees,
    )


@pytest.fixture
def full_config(full_employees) -> Config:
    return Config(
        month=3,
        year=2025,
        seed=42,
        employees=full_employees,
    )


@pytest.fixture
def sample_holidays() -> set[date]:
    """Праздники для марта 2025."""
    return {
        date(2025, 3, 8),  # 8 Марта
        date(2025, 3, 10),  # выходной
    }


@pytest.fixture
def no_holidays() -> set[date]:
    return set()
