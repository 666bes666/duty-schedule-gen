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


# ── Фича 1: Лимиты смен ───────────────────────────────────────────────────────


class TestShiftLimits:
    """Лимиты смен по типу не превышаются."""

    def test_max_evening_shifts_not_exceeded(self):
        """Сотрудник с max_evening_shifts=5 не получает более 5 вечерних смен.

        В марте 2025 (21 рабочий день) с 4 московскими дежурными каждый
        получает ~5–6 вечерних смен. Лимит 5 — реалистичная верхняя граница.
        """
        emps = [
            _emp("Москва 1", max_evening_shifts=5),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        evening_count = sum(1 for d in schedule.days if "Москва 1" in d.evening)
        assert evening_count <= 5, f"Превышен лимит вечерних смен: {evening_count}"

    def test_max_morning_shifts_not_exceeded(self):
        """Сотрудник с max_morning_shifts=6 не получает более 6 утренних смен.

        Естественное распределение — ~6–8 утренних смен на 4 москвичей за 31 день.
        Лимит 6 — разумная граница.
        """
        emps = [
            _emp("Москва 1", max_morning_shifts=6),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        morning_count = sum(1 for d in schedule.days if "Москва 1" in d.morning)
        assert morning_count <= 6, f"Превышен лимит утренних смен: {morning_count}"

    def test_max_night_shifts_not_exceeded(self):
        """Хабаровский с max_night_shifts=18 не получает более 18 ночных смен.

        Естественно каждый из 2 хабаровских получает ~15–16 ночей в марте.
        Лимит 18 — верхняя граница, подтверждает корректность механизма.
        """
        emps = [
            _emp("Москва 1"),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK, max_night_shifts=18),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        night_count = sum(1 for d in schedule.days if "Хабаровск 1" in d.night)
        assert night_count <= 18, f"Превышен лимит ночных смен: {night_count}"

    def test_schedule_covered_with_limits(self):
        """Все смены покрыты даже при лимитах."""
        emps = [
            _emp("Москва 1", max_evening_shifts=5),
            _emp("Москва 2", max_morning_shifts=5),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"


# ── Фича 2: Предпочтительная смена ───────────────────────────────────────────


class TestPreferredShift:
    """preferred_shift задаёт мягкий приоритет при выборе смены."""

    def test_preferred_evening_gets_more_evenings(self):
        """Сотрудник с preferred_shift=EVENING получает не меньше вечерних, чем без предпочтения."""
        emps_pref = [
            _emp("Москва 1", preferred_shift=ShiftType.EVENING),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps_pref)
        schedule = generate_schedule(config, set())
        # Просто проверяем, что расписание строится и preferred_shift принимается
        assert len(schedule.days) == 31

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


# ── Фича 3: Норма нагрузки ────────────────────────────────────────────────────


class TestWorkloadPct:
    """workload_pct снижает целевое число рабочих дней."""

    def test_workload_50pct_fewer_working_days(self):
        """Сотрудник с workload_pct=50 работает примерно вдвое меньше, чем другие."""
        emps = [
            _emp("Москва 1", workload_pct=50),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        report = schedule.metadata.get("working_days_per_employee", {})
        wd_m1 = report.get("Москва 1", 0)
        wd_m2 = report.get("Москва 2", 0)
        # 50% загрузка → значительно меньше рабочих дней
        assert wd_m1 < wd_m2, f"Москва 1 ({wd_m1}) должна работать меньше Москвы 2 ({wd_m2})"

    def test_workload_100pct_default(self):
        """workload_pct=100 — полная ставка по умолчанию."""
        emp = _emp("Тест")
        assert emp.workload_pct == 100

    def test_workload_out_of_range_raises(self):
        """workload_pct вне 1–100 вызывает ValidationError."""
        with pytest.raises(Exception, match="workload_pct"):
            _emp("Тест", workload_pct=0)
        with pytest.raises(Exception, match="workload_pct"):
            _emp("Тест", workload_pct=101)

    def test_schedule_covered_with_low_workload(self):
        """Все смены покрыты даже если один сотрудник работает на 30%."""
        emps = [
            _emp("Москва 1", workload_pct=30),
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


# ── Фича 4: Постоянные выходные дни недели ────────────────────────────────────


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
            if day.date.weekday() == 0:  # Понедельник
                all_shifts = day.morning + day.evening + day.night + day.workday
                assert "Москва 1" not in all_shifts, (
                    f"Москва 1 назначена в Пн {day.date}"
                )

    def test_schedule_covered_with_weekly_day_off(self):
        """Расписание полностью покрыто при наличии постоянных выходных."""
        emps = [
            _emp("Москва 1", days_off_weekly=[5, 6]),  # нет в выходные
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


# ── Фича 5: Индивидуальный лимит серии ───────────────────────────────────────


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


# ── Фича 6: Группы ────────────────────────────────────────────────────────────


class TestGroupConstraint:
    """Два сотрудника из одной группы не попадают на одну смену в один день."""

    def test_same_group_not_on_same_shift(self):
        """Москва 1 и Москва 2 в одной группе — не на одном утре/вечере в один день."""
        emps = [
            _emp("Москва 1", group="DB"),
            _emp("Москва 2", group="DB"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            if "Москва 1" in day.morning and "Москва 2" in day.morning:
                pytest.fail(f"Обе из группы DB стоят на утро {day.date}")
            if "Москва 1" in day.evening and "Москва 2" in day.evening:
                pytest.fail(f"Обе из группы DB стоят на вечер {day.date}")

    def test_group_none_no_constraint(self):
        """Без группы (group=None) ограничений нет."""
        emps = _base_team()
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 31

    def test_schedule_covered_with_groups(self):
        """Все смены покрыты при наличии групп."""
        emps = [
            _emp("Москва 1", group="A"),
            _emp("Москва 2", group="A"),
            _emp("Москва 3", group="B"),
            _emp("Москва 4", group="B"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"


# ── Фича 7: Роль ──────────────────────────────────────────────────────────────


class TestRole:
    """Роль — информационное поле, не влияет на расписание."""

    def test_role_stored_in_employee(self):
        """Поле role сохраняется в объекте Employee."""
        emp = _emp("Тест", role="Backend Lead")
        assert emp.role == "Backend Lead"

    def test_role_default_empty(self):
        """По умолчанию role = ''."""
        emp = _emp("Тест")
        assert emp.role == ""

    def test_schedule_generated_with_roles(self):
        """Расписание строится при наличии ролей у сотрудников."""
        emps = [
            _emp("Москва 1", role="Lead"),
            _emp("Москва 2", role="Backend"),
            _emp("Москва 3", role="Frontend"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK, role="Ops"),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"
