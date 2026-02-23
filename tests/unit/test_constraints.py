"""Тесты ограничений расписания."""

from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import City, Employee, ScheduleType, ShiftType, VacationPeriod
from duty_schedule.scheduler import (
    EmployeeState,
    ScheduleError,
    _build_day,
    _can_work,
    _is_weekend_or_holiday,
    _resting_after_evening,
    _resting_after_night,
)


def _emp(name: str, city: City = City.MOSCOW, on_duty: bool = True) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE, on_duty=on_duty)


class TestIsWeekendOrHoliday:
    def test_saturday(self):
        assert _is_weekend_or_holiday(date(2025, 3, 1), set()) is True  # суббота

    def test_sunday(self):
        assert _is_weekend_or_holiday(date(2025, 3, 2), set()) is True  # воскресенье

    def test_weekday(self):
        assert _is_weekend_or_holiday(date(2025, 3, 3), set()) is False  # понедельник

    def test_holiday_weekday(self):
        holiday = date(2025, 3, 8)
        assert _is_weekend_or_holiday(holiday, {holiday}) is True


class TestRestingConstraints:
    def test_resting_after_night(self):
        state = EmployeeState(last_shift=ShiftType.NIGHT)
        assert _resting_after_night(state) is True

    def test_not_resting_after_morning(self):
        state = EmployeeState(last_shift=ShiftType.MORNING)
        assert _resting_after_night(state) is False

    def test_cannot_work_morning_after_evening(self):
        state = EmployeeState(last_shift=ShiftType.EVENING)
        assert _resting_after_evening(state) is True

    def test_can_work_morning_after_morning(self):
        state = EmployeeState(last_shift=ShiftType.MORNING)
        assert _resting_after_evening(state) is False


class TestCanWork:
    def test_on_vacation_cannot_work(self):
        emp = Employee(
            name="В отпуске",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 31))],
        )
        state = EmployeeState()
        assert _can_work(emp, state, date(2025, 3, 15), set()) is False

    def test_max_consecutive_cannot_work(self):
        emp = _emp("Максимум")
        state = EmployeeState(consecutive_working=5)
        assert _can_work(emp, state, date(2025, 3, 10), set()) is False

    def test_52_weekend_cannot_work(self):
        emp = Employee(
            name="5/2",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FIVE_TWO,
        )
        state = EmployeeState()
        saturday = date(2025, 3, 1)  # суббота
        assert _can_work(emp, state, saturday, set()) is False

    def test_flexible_weekend_can_work(self):
        emp = _emp("Гибкий")
        state = EmployeeState()
        saturday = date(2025, 3, 1)
        assert _can_work(emp, state, saturday, set()) is True


class TestEmployeeState:
    def test_record_night_increments(self):
        state = EmployeeState()
        state.record(ShiftType.NIGHT)
        assert state.night_count == 1
        assert state.consecutive_working == 1
        assert state.consecutive_off == 0
        assert state.last_shift == ShiftType.NIGHT

    def test_record_day_off_resets_working(self):
        state = EmployeeState(consecutive_working=3)
        state.record(ShiftType.DAY_OFF)
        assert state.consecutive_working == 0
        assert state.consecutive_off == 1

    def test_shift_count(self):
        state = EmployeeState(morning_count=2, evening_count=1, night_count=3)
        assert state.shift_count(ShiftType.MORNING) == 2
        assert state.shift_count(ShiftType.EVENING) == 1
        assert state.shift_count(ShiftType.NIGHT) == 3

    def test_needs_more_work_when_behind(self):
        state = EmployeeState(target_working_days=21, vacation_days=0, total_working=10)
        assert state.needs_more_work(remaining_days=15) is True

    def test_no_more_work_when_target_met(self):
        state = EmployeeState(target_working_days=21, vacation_days=0, total_working=21)
        assert state.needs_more_work(remaining_days=5) is False


class TestBuildDay:
    """Тесты построения расписания на один день."""

    def _make_team(self) -> tuple[list[Employee], dict]:
        employees = [
            _emp("Москва 1"),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            _emp("Хабаровск 1", City.KHABAROVSK),
            _emp("Хабаровск 2", City.KHABAROVSK),
        ]
        states = {e.name: EmployeeState(target_working_days=21) for e in employees}
        return employees, states

    def test_all_shifts_covered(self):
        import random as _random

        employees, states = self._make_team()
        rng = _random.Random(42)
        day = date(2025, 3, 3)  # понедельник
        ds = _build_day(day, employees, states, set(), rng, remaining_days=29)
        assert ds.morning, "Утренняя смена не покрыта"
        assert ds.evening, "Вечерняя смена не покрыта"
        assert ds.night, "Ночная смена не покрыта"

    def test_night_only_khabarovsk(self):
        """В колонке 'night' только хабаровские сотрудники."""
        import random as _random

        employees, states = self._make_team()
        rng = _random.Random(42)
        day = date(2025, 3, 3)
        ds = _build_day(day, employees, states, set(), rng, remaining_days=29)
        khb_names = {"Хабаровск 1", "Хабаровск 2"}
        for name in ds.night:
            assert name in khb_names, f"Ночная смена назначена не хабаровскому: {name}"

    def test_moscow_not_in_night(self):
        """Московские сотрудники НЕ появляются в ночной смене."""
        import random as _random

        employees, states = self._make_team()
        rng = _random.Random(42)
        day = date(2025, 3, 3)
        ds = _build_day(day, employees, states, set(), rng, remaining_days=29)
        moscow_names = {"Москва 1", "Москва 2", "Москва 3", "Москва 4"}
        for name in ds.night:
            assert name not in moscow_names, f"Московский в ночной смене: {name}"

    def test_khabarovsk_not_in_morning_evening(self):
        """Хабаровские сотрудники НЕ появляются в утренней/вечерней MSK сменах."""
        import random as _random

        employees, states = self._make_team()
        rng = _random.Random(42)
        day = date(2025, 3, 3)
        ds = _build_day(day, employees, states, set(), rng, remaining_days=29)
        khb_names = {"Хабаровск 1", "Хабаровск 2"}
        for name in ds.morning:
            assert name not in khb_names, f"Хабаровский в утренней смене MSK: {name}"
        for name in ds.evening:
            assert name not in khb_names, f"Хабаровский в вечерней смене MSK: {name}"

    def test_khabarovsk_workday_on_non_night_day(self):
        """Хабаровский не на ночи и не после ночи — получает workday (норма)."""
        import random as _random

        employees, states = self._make_team()
        rng = _random.Random(42)
        day = date(2025, 3, 3)
        ds = _build_day(day, employees, states, set(), rng, remaining_days=29)
        khb_names = {"Хабаровск 1", "Хабаровск 2"}
        # Один на ночи, второй — либо workday либо day_off
        night_set = set(ds.night)
        workday_set = set(ds.workday)
        day_off_set = set(ds.day_off)
        for name in khb_names:
            assert name in (night_set | workday_set | day_off_set), (
                f"{name} не назначен ни на одну смену"
            )

    def test_no_night_khabarovsk_fails(self):
        """Если все хабаровские в отпуске — ScheduleError."""
        import random as _random

        day = date(2025, 3, 3)
        employees = [
            _emp("Москва 1"),
            _emp("Москва 2"),
            _emp("Москва 3"),
            _emp("Москва 4"),
            Employee(
                name="Хабаровск 1",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=[VacationPeriod(start=day, end=day)],
            ),
            Employee(
                name="Хабаровск 2",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
                vacations=[VacationPeriod(start=day, end=day)],
            ),
        ]
        states = {e.name: EmployeeState(target_working_days=21) for e in employees}
        rng = _random.Random(42)
        with pytest.raises(ScheduleError, match="ночную смену"):
            _build_day(day, employees, states, set(), rng, remaining_days=29)
