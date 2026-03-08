from __future__ import annotations

from duty_schedule.models import (
    CarryOverState,
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


def _is_working(name: str, day) -> bool:
    return name in day.morning or name in day.evening or name in day.night or name in day.workday


class TestCarryOverConsecutiveWorking:
    def test_carry_over_consecutive_5_gets_early_day_off(self):
        emps = _base_team()
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                consecutive_working=5,
                last_shift=ShiftType.MORNING,
            )
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        streak = 5
        max_allowed = 6
        for day in schedule.days:
            if _is_working("Москва 1", day):
                streak += 1
            else:
                streak = 0
            assert streak <= max_allowed, (
                f"Москва 1 работает {streak} дней подряд (включая carry_over) на {day.date}"
            )

    def test_carry_over_consecutive_working_forces_rest_day_1(self):
        emps = _base_team()
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                consecutive_working=6,
                last_shift=ShiftType.WORKDAY,
            )
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        day1 = schedule.days[0]
        assert not _is_working("Москва 1", day1), (
            "Москва 1 должен отдыхать в день 1 после carry_over consecutive_working=6"
        )


class TestCarryOverLastShift:
    def test_carry_over_last_shift_evening_no_morning_day_1(self):
        emps = _base_team()
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                last_shift=ShiftType.EVENING,
                consecutive_working=2,
            )
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        day1 = schedule.days[0]
        assert "Москва 1" not in day1.morning, (
            "После вечерней смены (carry_over) сотрудник не должен стоять на утро в день 1"
        )
        assert "Москва 1" not in day1.workday, (
            "После вечерней смены (carry_over) сотрудник не должен стоять на рабочий день в день 1"
        )

    def test_carry_over_last_shift_night_blocks_moscow_morning_day_1(self):
        emps = _base_team()
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                last_shift=ShiftType.NIGHT,
                consecutive_working=1,
            )
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        day1 = schedule.days[0]
        assert "Москва 1" not in day1.morning, (
            "После ночной смены (carry_over) московский сотрудник не должен стоять на утро в день 1"
        )


class TestCarryOverConsecutiveSameShift:
    def test_carry_over_consecutive_same_shift_limits_morning(self):
        emps = [
            _emp("Москва 1", max_consecutive_morning=3),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                last_shift=ShiftType.MORNING,
                consecutive_working=2,
                consecutive_same_shift=2,
            )
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        morning_streak = 2
        for day in schedule.days:
            if "Москва 1" in day.morning:
                morning_streak += 1
            else:
                morning_streak = 0
            assert morning_streak <= 3, (
                f"Москва 1 стоит на утро {morning_streak} дней подряд "
                f"(включая carry_over, лимит 3) на {day.date}"
            )

    def test_schedule_covered_with_carry_over(self):
        emps = _base_team()
        carry = [
            CarryOverState(
                employee_name="Москва 1",
                consecutive_working=5,
                last_shift=ShiftType.EVENING,
            ),
            CarryOverState(
                employee_name="Хабаровск 1",
                last_shift=ShiftType.NIGHT,
                consecutive_working=3,
            ),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, carry_over=carry)
        schedule = generate_schedule(config, set())

        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"
