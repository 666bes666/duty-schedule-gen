"""Интеграционные тесты граничных случаев."""

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


def _emp(name: str, city: City = City.MOSCOW, **kwargs) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE, **kwargs)


def _base_team() -> list[Employee]:
    return [_emp(f"Москва {i}") for i in range(1, 5)] + [
        _emp(f"Хабаровск {i}", City.KHABAROVSK) for i in range(1, 3)
    ]


class TestMinimalKhabarovsk:
    """Ровно 2 дежурных в Хабаровске."""

    def test_exactly_two_khabarovsk(self):
        config = Config(month=3, year=2025, seed=42, employees=_base_team())
        schedule = generate_schedule(config, set())
        # Ночные смены должны быть у обоих хабаровчан
        khb_names = {"Хабаровск 1", "Хабаровск 2"}
        night_workers = set()
        for day in schedule.days:
            night_workers.update(day.night)
        assert night_workers == khb_names

    def test_one_khabarovsk_on_vacation_still_covered(self):
        """Один хабаровчанин в отпуске первую неделю — двое других покрывают ночи.

        С командой из 3 хабаровских сотрудников двое могут чередоваться:
        К2-ночь → К3-ночь → К2-ночь → ... — и покрыть 7 ночей без проблем.
        """
        emps = [_emp(f"Москва {i}") for i in range(1, 5)] + [
            Employee(
                name="Хабаровск 1",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 7))],
            ),
            _emp("Хабаровск 2", City.KHABAROVSK),
            _emp("Хабаровск 3", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            if date(2025, 3, 1) <= day.date <= date(2025, 3, 7):
                assert day.night, f"Нет ночной смены {day.date}"
                assert "Хабаровск 1" not in day.night


class TestMinimalMoscow:
    """Ровно 4 дежурных в Москве."""

    def test_exactly_four_moscow(self):
        config = Config(month=3, year=2025, seed=42, employees=_base_team())
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 31

    def test_moscow_employee_long_vacation(self):
        """Один московский в длинном отпуске — остальные справляются."""
        emps = [
            Employee(
                name="Москва 1",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=[VacationPeriod(start=date(2025, 3, 10), end=date(2025, 3, 20))],
            ),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.morning, f"Нет утра {day.date}"
            assert day.evening, f"Нет вечера {day.date}"


class TestHolidayHeavyMonth:
    """Месяц с большим количеством праздников."""

    def test_many_holidays(self):
        """10 праздников подряд — расписание всё равно строится."""
        holidays = {date(2025, 3, d) for d in range(1, 11)}
        config = Config(month=3, year=2025, seed=42, employees=_base_team())
        schedule = generate_schedule(config, holidays)
        for day in schedule.days:
            if day.date in holidays:
                assert day.is_covered(), f"Праздник {day.date} не покрыт"

    def test_full_month_holidays(self):
        """Весь месяц — праздники, гибкие сотрудники работают."""
        from duty_schedule.calendar import get_all_days

        all_days = get_all_days(2025, 3)
        holidays = set(all_days)
        config = Config(month=3, year=2025, seed=42, employees=_base_team())
        schedule = generate_schedule(config, holidays)
        assert len(schedule.days) == 31


class TestMorningEveningOnlyEmployees:
    """Сотрудники с ограничением по типу смены."""

    def test_morning_only_not_on_evening(self):
        emps = [
            _emp("Москва 1", morning_only=True),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert "Москва 1" not in day.evening, f"morning_only назначен вечером {day.date}"

    def test_evening_only_not_on_morning(self):
        emps = [
            _emp("Москва 1", evening_only=True),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert "Москва 1" not in day.morning, f"evening_only назначен утром {day.date}"


class TestVacationOverlap:
    """Пересекающиеся отпуска нескольких сотрудников."""

    def test_two_moscow_on_vacation_same_week(self):
        """Двое московских в отпуске одновременно — всё равно покрытие.

        С 5 московскими сотрудниками (реальный состав) уход двоих оставляет трёх,
        которые без проблем покрывают утро и вечер весь период отпуска.
        """
        vacation = [VacationPeriod(start=date(2025, 3, 3), end=date(2025, 3, 7))]
        emps = [
            Employee(
                name="Москва 1",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=vacation,
            ),
            Employee(
                name="Москва 2",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=vacation,
            ),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Москва 5"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Нет покрытия {day.date}"


class TestUnavailableDates:
    """Разовые блокировки дней."""

    def test_unavailable_employee_not_assigned_on_blocked_day(self):
        """Сотрудник с unavailable_dates не должен быть в сменах в эти дни."""
        team = _base_team()
        # Блокируем первого московского дежурного на 5-е число
        team[0] = _emp("Москва 1", unavailable_dates=[date(2025, 3, 5)])
        config = Config(month=3, year=2025, seed=42, employees=team)
        schedule = generate_schedule(config, set())
        day_5 = next(d for d in schedule.days if d.date == date(2025, 3, 5))
        all_assigned = day_5.morning + day_5.evening + day_5.night + day_5.workday
        assert "Москва 1" not in all_assigned

    def test_unavailable_shows_as_day_off_not_vacation(self):
        """Разовая блокировка показывается как выходной, а не отпуск."""
        team = _base_team()
        team[0] = _emp("Москва 1", unavailable_dates=[date(2025, 3, 10)])
        config = Config(month=3, year=2025, seed=42, employees=team)
        schedule = generate_schedule(config, set())
        day_10 = next(d for d in schedule.days if d.date == date(2025, 3, 10))
        assert "Москва 1" not in day_10.vacation

    def test_schedule_still_covered_with_unavailable(self):
        """Все смены покрыты даже при наличии блокировок."""
        team = _base_team()
        team[0] = _emp("Москва 1", unavailable_dates=[date(2025, 3, 1), date(2025, 3, 5)])
        config = Config(month=3, year=2025, seed=42, employees=team)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"


class TestDifferentMonths:
    """Разные месяцы и года."""

    @pytest.mark.parametrize(
        "month,year,expected_days",
        [
            (1, 2025, 31),
            (2, 2025, 28),
            (2, 2024, 29),
            (4, 2025, 30),
            (12, 2025, 31),
        ],
    )
    def test_month_length(self, month, year, expected_days):
        config = Config(month=month, year=year, seed=42, employees=_base_team())
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == expected_days
