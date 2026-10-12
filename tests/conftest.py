"""Общие фикстуры для тестов."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from duty_schedule.models import (
    CalendarDay,
    CarryOverState,
    City,
    Config,
    Employee,
    ProductionCalendar,
    ScheduleType,
)


def complete_config(config: Config) -> Config:
    from duty_schedule.calendar import get_all_days

    result = config.model_copy(deep=True)
    result.production_calendar = ProductionCalendar(
        year=result.year,
        month=result.month,
        days=[
            CalendarDay(date=day, kind="off" if day.weekday() >= 5 else "working")
            for day in get_all_days(result.year, result.month)
        ],
        source="verified test fixture",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    previous = date(result.year, result.month, 1) - timedelta(days=1)
    result.carry_over = [
        CarryOverState(
            employee_name=e.name,
            employee_id=e.employee_id,
            source="new_employee",
            no_previous_shifts=True,
            as_of=previous,
        )
        for e in result.employees
    ]
    return result


@pytest.fixture
def planning_config() -> Config:
    employees = [_emp(f"M{i}") for i in range(6)] + [
        _emp(f"K{i}", City.KHABAROVSK) for i in range(2)
    ]
    return complete_config(Config(year=2026, month=4, employees=employees))


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
    on_duty: bool = True,
    morning_only: bool = False,
    evening_only: bool = False,
    vacations: list | None = None,
) -> Employee:
    return Employee(
        name=name,
        city=city,
        schedule_type=schedule_type,
        on_duty=on_duty,
        morning_only=morning_only,
        evening_only=evening_only,
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
        _emp("Иванов Иван", City.MOSCOW),
        _emp("Петров Пётр", City.MOSCOW),
        _emp("Сидоров Сидор", City.MOSCOW),
        _emp("Козлов Коля", City.MOSCOW, morning_only=True),
        _emp("Морозов Михаил", City.MOSCOW, evening_only=True),
        _emp("Новиков Николай", City.MOSCOW, schedule_type=ScheduleType.FIVE_TWO, on_duty=False),
        _emp("Волков Владимир", City.MOSCOW, schedule_type=ScheduleType.FIVE_TWO, on_duty=False),
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
        date(2025, 3, 8),
        date(2025, 3, 10),
    }


@pytest.fixture
def no_holidays() -> set[date]:
    return set()
