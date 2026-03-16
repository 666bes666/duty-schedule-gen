"""Тесты моделей данных и правил валидации."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from duty_schedule.models import (
    CarryOverState,
    City,
    Config,
    DaySchedule,
    Employee,
    PinnedAssignment,
    ScheduleType,
    ShiftType,
    VacationPeriod,
    collect_config_issues,
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

    def test_unavailable_dates_blocks_day(self):
        emp = Employee(
            name="Недоступен",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            unavailable_dates=[date(2025, 3, 5), date(2025, 3, 10)],
        )
        assert emp.is_blocked(date(2025, 3, 5)) is True
        assert emp.is_blocked(date(2025, 3, 10)) is True
        assert emp.is_blocked(date(2025, 3, 6)) is False
        assert emp.is_on_vacation(date(2025, 3, 5)) is False

    def test_is_blocked_includes_vacation(self):
        emp = Employee(
            name="В отпуске и недоступен",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 3))],
            unavailable_dates=[date(2025, 3, 15)],
        )
        assert emp.is_blocked(date(2025, 3, 2)) is True
        assert emp.is_blocked(date(2025, 3, 15)) is True
        assert emp.is_blocked(date(2025, 3, 10)) is False


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

    def test_non_duty_not_counted_as_duty(self):
        emps = self._make_employees(4, 2)
        emps.append(
            Employee(
                name="Не дежурный",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FIVE_TWO,
                on_duty=False,
            )
        )
        cfg = Config(month=3, year=2025, employees=emps)
        assert len(cfg.employees) == 7


class TestDaySchedule:
    def test_all_assigned_excludes_day_off(self):
        ds = DaySchedule(
            date=date(2025, 3, 1),
            morning=["A"],
            evening=["B"],
            night=["C"],
            workday=["D"],
            day_off=["E"],
        )
        assigned = ds.all_assigned()
        assert "A" in assigned
        assert "D" in assigned
        assert "E" not in assigned

    def test_is_covered_true(self):
        ds = DaySchedule(
            date=date(2025, 3, 1),
            morning=["A"],
            evening=["B"],
            night=["C"],
        )
        assert ds.is_covered() is True

    def test_is_covered_false_missing_night(self):
        ds = DaySchedule(
            date=date(2025, 3, 1),
            morning=["A"],
            evening=["B"],
        )
        assert ds.is_covered() is False

    def test_is_covered_false_empty(self):
        ds = DaySchedule(date=date(2025, 3, 1))
        assert ds.is_covered() is False


class TestCollectConfigIssues:
    def _make_employees(self, moscow: int = 4, khabarovsk: int = 2) -> list[Employee]:
        emps = [
            Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(moscow)
        ] + [
            Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(khabarovsk)
        ]
        return emps

    def test_valid_config_no_issues(self):
        cfg = Config(month=3, year=2025, employees=self._make_employees())
        errors, warnings = collect_config_issues(cfg)
        assert errors == []
        assert warnings == []

    def test_duplicate_names(self):
        emps = self._make_employees()
        emps.append(Employee(name="М0", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE))
        cfg = Config(month=3, year=2025, employees=emps)
        errors, _ = collect_config_issues(cfg)
        assert any("М0" in e for e in errors)

    def test_pin_unknown_employee(self):
        cfg = Config(
            month=3,
            year=2025,
            employees=self._make_employees(),
            pins=[
                PinnedAssignment(
                    date=date(2025, 3, 1),
                    employee_name="НеСуществует",
                    shift=ShiftType.MORNING,
                ),
            ],
        )
        errors, _ = collect_config_issues(cfg)
        assert any("НеСуществует" in e for e in errors)

    def test_pin_moscow_to_night_error(self):
        cfg = Config(
            month=3,
            year=2025,
            employees=self._make_employees(),
            pins=[
                PinnedAssignment(date=date(2025, 3, 1), employee_name="М0", shift=ShiftType.NIGHT),
            ],
        )
        errors, _ = collect_config_issues(cfg)
        assert any("ночную" in e for e in errors)

    def test_pin_khabarovsk_to_morning_error(self):
        cfg = Config(
            month=3,
            year=2025,
            employees=self._make_employees(),
            pins=[
                PinnedAssignment(
                    date=date(2025, 3, 1),
                    employee_name="Х0",
                    shift=ShiftType.MORNING,
                ),
            ],
        )
        errors, _ = collect_config_issues(cfg)
        assert any("утреннюю" in e for e in errors)

    def test_carry_over_unknown_employee_warning(self):
        cfg = Config(
            month=3,
            year=2025,
            employees=self._make_employees(),
            carry_over=[CarryOverState(employee_name="Неизвестный", consecutive_working=3)],
        )
        _, warnings = collect_config_issues(cfg)
        assert any("Неизвестный" in w for w in warnings)

    def test_duplicate_pin_same_day_same_employee(self):
        cfg = Config(
            month=3,
            year=2025,
            employees=self._make_employees(),
            pins=[
                PinnedAssignment(
                    date=date(2025, 3, 1),
                    employee_name="М0",
                    shift=ShiftType.MORNING,
                ),
                PinnedAssignment(
                    date=date(2025, 3, 1),
                    employee_name="М0",
                    shift=ShiftType.EVENING,
                ),
            ],
        )
        errors, _ = collect_config_issues(cfg)
        assert any("несколько смен" in e for e in errors)
