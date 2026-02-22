"""Тесты движка планирования."""

from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    VacationPeriod,
)
from duty_schedule.scheduler import generate_schedule


def _base_employees() -> list[Employee]:
    return [
        Employee(name=f"Москва {i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 5)
    ] + [
        Employee(name=f"Хабаровск {i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(1, 3)
    ]


class TestGenerateSchedule:
    def test_full_month_coverage(self):
        """Все дни месяца должны иметь покрытие трёх смен."""
        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 31
        for day in schedule.days:
            assert day.morning, f"Нет утренней смены {day.date}"
            assert day.evening, f"Нет вечерней смены {day.date}"
            assert day.night, f"Нет ночной смены {day.date}"

    def test_deterministic_with_same_seed(self):
        """Одинаковый seed → одинаковое расписание."""
        config = Config(month=3, year=2025, seed=99, employees=_base_employees())
        s1 = generate_schedule(config, set())
        s2 = generate_schedule(config, set())
        for d1, d2 in zip(s1.days, s2.days, strict=False):
            assert d1.morning == d2.morning
            assert d1.evening == d2.evening
            assert d1.night == d2.night

    def test_different_seeds_may_differ(self):
        """Разные seeds могут давать разные результаты."""
        emps = _base_employees()
        c1 = Config(month=3, year=2025, seed=1, employees=emps)
        c2 = Config(month=3, year=2025, seed=2, employees=emps)
        s1 = generate_schedule(c1, set())
        s2 = generate_schedule(c2, set())
        # Хотя бы один день должен отличаться
        differs = any(
            d1.morning != d2.morning or d1.evening != d2.evening
            for d1, d2 in zip(s1.days, s2.days, strict=False)
        )
        assert differs, "Разные seeds дали одинаковое расписание"

    def test_night_shift_only_khabarovsk(self):
        """Ночная смена назначается только хабаровским сотрудникам."""
        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        khb_names = {f"Хабаровск {i}" for i in range(1, 3)}
        for day in schedule.days:
            for name in day.night:
                assert name in khb_names, f"Ночная смена у {name} на {day.date}"

    def test_vacation_employee_not_assigned(self):
        """Сотрудник в отпуске не назначается ни на одну смену."""
        emps = _base_employees()
        # Даём Москва 1 отпуск на первую неделю
        emps[0] = Employee(
            name="Москва 1",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 7))],
        )
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        for day in schedule.days:
            if date(2025, 3, 1) <= day.date <= date(2025, 3, 7):
                all_duty = day.morning + day.evening
                assert "Москва 1" not in all_duty, f"Отпускник назначен {day.date}"

    def test_five_two_not_on_weekends(self):
        """5/2 сотрудник не работает в выходные."""
        emps = [
            Employee(name="Москва 5/2", city=City.MOSCOW, schedule_type=ScheduleType.FIVE_TWO),
            Employee(name="Москва 2", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Москва 3", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Москва 4", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Хабаровск 1", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Хабаровск 2", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps)
        schedule = generate_schedule(config, set())
        weekends = {d.date for d in schedule.days if d.date.weekday() >= 5}
        for day in schedule.days:
            if day.date in weekends:
                assert "Москва 5/2" not in day.morning + day.evening

    def test_metadata_contains_counts(self):
        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        assert "total_nights" in schedule.metadata
        assert "total_mornings" in schedule.metadata
        assert "total_evenings" in schedule.metadata

    def test_after_night_rest_is_mandatory(self):
        """После ночной смены следующий день — выходной (не ночь/утро/вечер/рабочий)."""
        from datetime import timedelta

        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        days = {d.date: d for d in schedule.days}
        for day in schedule.days:
            next_day_date = day.date + timedelta(days=1)
            if next_day_date not in days:
                continue
            next_day = days[next_day_date]
            # После ночи — только day_off или vacation (не любая рабочая смена)
            for name in day.night:
                all_working = (
                    next_day.morning + next_day.evening + next_day.night + next_day.workday
                )
                assert name not in all_working, f"{name} работает после ночной смены {day.date}"

    def test_khabarovsk_only_night_or_workday(self):
        """Хабаровские дежурные никогда не появляются в московских сменах (утро/вечер)."""
        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        khb_names = {f"Хабаровск {i}" for i in range(1, 3)}
        for day in schedule.days:
            for name in day.morning + day.evening:
                assert name not in khb_names, f"Хабаровский {name} в MSK смене на {day.date}"

    def test_real_team_generates_schedule(self):
        """Реальный состав команды: 5 Москва + 3 Хабаровск + 2 нет дежурств."""
        from duty_schedule.models import City, Employee, ScheduleType

        employees = [
            Employee(name="Амир", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Милана", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Ваня", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Тимофей", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Петя", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE),
            Employee(
                name="Слава",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FIVE_TWO,
                on_duty=False,
            ),
            Employee(
                name="Дима",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FIVE_TWO,
                on_duty=False,
                team_lead=True,
            ),
            Employee(name="Вика", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Андрей", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE),
            Employee(name="Глеб", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE),
            Employee(
                name="Паша",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
                on_duty=False,
                team_lead=True,
            ),
        ]
        config = Config(month=3, year=2025, seed=42, employees=employees)
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 31
        for day in schedule.days:
            assert day.morning, f"Нет утро {day.date}"
            assert day.evening, f"Нет вечер {day.date}"
            assert day.night, f"Нет ночь {day.date}"
        # Проверяем что хабаровские не в московских сменах
        khb = {"Вика", "Андрей", "Глеб"}
        for day in schedule.days:
            for name in day.morning + day.evening:
                assert name not in khb, f"Хабаровский {name} в MSK смене {day.date}"

    def test_february_28_days(self):
        """Февраль 2025 — 28 дней."""
        config = Config(month=2, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, set())
        assert len(schedule.days) == 28

    def test_holiday_coverage(self):
        """В праздники тоже должны быть все три смены."""
        holidays = {
            date(2025, 3, 8),
            date(2025, 3, 9),
            date(2025, 3, 10),
        }
        config = Config(month=3, year=2025, seed=42, employees=_base_employees())
        schedule = generate_schedule(config, holidays)
        for day in schedule.days:
            if day.date in holidays:
                assert day.morning, f"Нет утра в праздник {day.date}"
                assert day.evening, f"Нет вечера в праздник {day.date}"
                assert day.night, f"Нет ночи в праздник {day.date}"
