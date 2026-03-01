"""Генеративные тесты: случайные конфиги и базовые инварианты."""

from __future__ import annotations

import random

from duty_schedule.models import City, Config, Employee, ScheduleType
from duty_schedule.scheduler import generate_schedule


def _random_team(rng: random.Random) -> list[Employee]:
    """Сгенерировать случайную команду с соблюдением минимальных требований."""
    moscow_count = rng.randint(4, 7)
    khab_count = rng.randint(2, 4)

    employees: list[Employee] = []
    for i in range(moscow_count):
        employees.append(
            Employee(
                name=f"Москва {i + 1}",
                city=City.MOSCOW,
                schedule_type=ScheduleType.FLEXIBLE,
            )
        )
    for i in range(khab_count):
        employees.append(
            Employee(
                name=f"Хабаровск {i + 1}",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
            )
        )
    return employees


def _is_working_day(shift_names: list[str]) -> bool:
    """Есть ли у сотрудника хотя бы одна рабочая смена в день."""
    return bool(shift_names)


def _count_isolated_off_for_emp(name: str, days: list) -> int:
    count = 0
    for i, day in enumerate(days):
        if name not in day.day_off:
            continue
        left_ok = i == 0 or name in days[i - 1].day_off or name in days[i - 1].vacation
        right_ok = i == len(days) - 1 or name in days[i + 1].day_off or name in days[i + 1].vacation
        if not left_ok and not right_ok:
            count += 1
    return count


def test_random_configs_respect_basic_invariants():
    """Случайные команды всегда дают корректное покрытие и базовые ограничения.

    Проверяем:
    - Все дни покрыты утренней/вечерней/ночной сменой.
    - Ночные смены только у хабаровчан.
    - Хабаровчане никогда не попадают в утро/вечер (MSK).
    - Сотрудник не назначается на две смены одновременно в один день.
    """
    rng = random.Random(12345)

    for _ in range(10):
        employees = _random_team(rng)
        cfg = Config(month=3, year=2025, seed=rng.randint(0, 10_000), employees=employees)
        schedule = generate_schedule(cfg, set())

        assert len(schedule.days) == 31

        moscow_names = {e.name for e in employees if e.city == City.MOSCOW}
        khab_names = {e.name for e in employees if e.city == City.KHABAROVSK}

        for day in schedule.days:
            assert day.morning, f"Нет утренней смены {day.date}"
            assert day.evening, f"Нет вечерней смены {day.date}"
            assert day.night, f"Нет ночной смены {day.date}"

            for name in day.night:
                assert name in khab_names, f"Ночная смена у {name} на {day.date}"

            for name in day.morning + day.evening:
                assert name in moscow_names, f"Хабаровский {name} в MSK смене на {day.date}"

            all_working = day.morning + day.evening + day.night + day.workday
            assert len(all_working) == len(set(all_working)), (
                f"Дублирование назначений на {day.date}: {all_working}"
            )

        for emp in employees:
            if emp.on_duty and emp.schedule_type == ScheduleType.FLEXIBLE:
                iso = _count_isolated_off_for_emp(emp.name, schedule.days)
                assert iso <= 2, (
                    f"{emp.name}: {iso} изолированных выходных (допустимо ≤2)"
                )
