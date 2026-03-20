"""Интеграционные тесты новых параметров сотрудника (фичи 1–7)."""

from __future__ import annotations

import pytest

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler import generate_schedule


def _emp(name: str, city: City = City.MOSCOW, **kwargs) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE, **kwargs)


def _base_team() -> list[Employee]:
    return [_emp(f"Москва {i}") for i in range(1, 5)] + [
        _emp(f"Хабаровск {i}", City.KHABAROVSK) for i in range(1, 3)
    ]


class TestPreferredShift:
    """preferred_shift задаёт мягкий приоритет при выборе смены."""

    def test_preferred_evening_gets_more_evenings(self):
        emps_pref = [
            _emp("Москва 1", preferred_shift=ShiftType.EVENING),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=0, employees=emps_pref)
        schedule = generate_schedule(config, set())
        evening_counts: dict[str, int] = {}
        for day in schedule.days:
            for name in day.evening:
                evening_counts[name] = evening_counts.get(name, 0) + 1
        moscow_names = ["Москва 2", "Москва 3", "Москва 4"]
        avg_others = sum(evening_counts.get(n, 0) for n in moscow_names) / len(moscow_names)
        pref_count = evening_counts.get("Москва 1", 0)
        assert pref_count > avg_others, (
            f"Preferred evening employee got {pref_count} evenings, avg others {avg_others:.1f}"
        )

    def test_preferred_morning_model_valid(self):
        """Модель Employee принимает preferred_shift=MORNING."""
        emp = _emp("Тест", preferred_shift=ShiftType.MORNING)
        assert emp.preferred_shift == ShiftType.MORNING

    def test_preferred_shift_vacation_raises(self):
        """preferred_shift=VACATION вызывает ValidationError."""
        with pytest.raises(Exception, match="preferred_shift"):
            _emp("Тест", preferred_shift=ShiftType.VACATION)

    def test_preferred_shift_day_off_raises(self):
        """preferred_shift=DAY_OFF вызывает ValidationError."""
        with pytest.raises(Exception, match="preferred_shift"):
            _emp("Тест", preferred_shift=ShiftType.DAY_OFF)


class TestDaysOffWeekly:
    """Сотрудник не работает в указанные дни недели."""

    def test_employee_not_assigned_on_weekly_day_off(self):
        """Сотрудник с days_off_weekly=[0] (Пн) никогда не работает по понедельникам."""
        emps = [
            _emp("Москва 1", days_off_weekly=[0]),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            if day.date.weekday() == 0:
                all_shifts = day.morning + day.evening + day.night + day.workday
                assert "Москва 1" not in all_shifts, f"Москва 1 назначена в Пн {day.date}"

    def test_schedule_covered_with_weekly_day_off(self):
        """Расписание полностью покрыто при наличии постоянных выходных."""
        emps = [
            _emp("Москва 1", days_off_weekly=[5, 6]),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"

    def test_invalid_weekday_raises(self):
        """days_off_weekly с числом вне 0–6 вызывает ValidationError."""
        with pytest.raises(Exception, match="days_off_weekly"):
            _emp("Тест", days_off_weekly=[7])


class TestMaxConsecutiveWorking:
    """Индивидуальный лимит рабочих дней подряд соблюдается."""

    def test_max_consecutive_working_3_not_exceeded(self):
        """Сотрудник с max_consecutive_working=3 не работает более 3 дней подряд."""
        emps = [
            _emp("Москва 1", max_consecutive_working=3),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        streak = 0
        for day in schedule.days:
            working = (
                "Москва 1" in day.morning
                or "Москва 1" in day.evening
                or "Москва 1" in day.night
                or "Москва 1" in day.workday
            )
            if working:
                streak += 1
                assert streak <= 3, (
                    f"Москва 1 работает {streak} дней подряд (лимит 3) на {day.date}"
                )
            else:
                streak = 0

    def test_max_consecutive_working_below_1_raises(self):
        """max_consecutive_working=0 вызывает ValidationError."""
        with pytest.raises(Exception, match="max_consecutive_working"):
            _emp("Тест", max_consecutive_working=0)

    def test_schedule_covered_with_low_max_consecutive(self):
        """Все смены покрыты при низком лимите серии."""
        emps = [
            _emp("Москва 1", max_consecutive_working=3),
            _emp("Москва 2", max_consecutive_working=3),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"
