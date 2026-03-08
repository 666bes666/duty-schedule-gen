from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    Config,
    Employee,
    PinnedAssignment,
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


class TestPinnedMorning:
    def test_pin_moscow_employee_to_morning(self):
        emps = _base_team()
        pin_date = date(2025, 3, 5)
        pins = [PinnedAssignment(date=pin_date, employee_name="Москва 2", shift=ShiftType.MORNING)]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        target_day = next(d for d in schedule.days if d.date == pin_date)
        assert "Москва 2" in target_day.morning, (
            f"Москва 2 должен быть на утренней смене {pin_date}"
        )


class TestPinnedEvening:
    def test_pin_moscow_employee_to_evening(self):
        emps = _base_team()
        pin_date = date(2025, 3, 10)
        pins = [PinnedAssignment(date=pin_date, employee_name="Москва 3", shift=ShiftType.EVENING)]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        target_day = next(d for d in schedule.days if d.date == pin_date)
        assert "Москва 3" in target_day.evening, (
            f"Москва 3 должен быть на вечерней смене {pin_date}"
        )


class TestPinnedNight:
    def test_pin_khabarovsk_employee_to_night(self):
        emps = _base_team()
        pin_date = date(2025, 3, 12)
        pins = [PinnedAssignment(date=pin_date, employee_name="Хабаровск 1", shift=ShiftType.NIGHT)]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        target_day = next(d for d in schedule.days if d.date == pin_date)
        assert "Хабаровск 1" in target_day.night, (
            f"Хабаровск 1 должен быть на ночной смене {pin_date}"
        )


class TestPinnedMultiple:
    def test_two_pins_same_date_different_shifts(self):
        emps = _base_team()
        pin_date = date(2025, 3, 17)
        pins = [
            PinnedAssignment(date=pin_date, employee_name="Москва 1", shift=ShiftType.MORNING),
            PinnedAssignment(date=pin_date, employee_name="Москва 4", shift=ShiftType.EVENING),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        target_day = next(d for d in schedule.days if d.date == pin_date)
        assert "Москва 1" in target_day.morning, (
            f"Москва 1 должен быть на утренней смене {pin_date}"
        )
        assert "Москва 4" in target_day.evening, (
            f"Москва 4 должен быть на вечерней смене {pin_date}"
        )


class TestPinnedSurvivesPostProcessing:
    def test_pinned_assignments_persist_in_final_schedule(self):
        emps = _base_team()
        pins = [
            PinnedAssignment(
                date=date(2025, 3, 3), employee_name="Москва 1", shift=ShiftType.MORNING
            ),
            PinnedAssignment(
                date=date(2025, 3, 7), employee_name="Москва 2", shift=ShiftType.EVENING
            ),
            PinnedAssignment(
                date=date(2025, 3, 14), employee_name="Хабаровск 2", shift=ShiftType.NIGHT
            ),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        day_3 = next(d for d in schedule.days if d.date == date(2025, 3, 3))
        assert "Москва 1" in day_3.morning, (
            "Пин Москва 1 -> утро 2025-03-03 не должен быть снят постобработкой"
        )

        day_7 = next(d for d in schedule.days if d.date == date(2025, 3, 7))
        assert "Москва 2" in day_7.evening, (
            "Пин Москва 2 -> вечер 2025-03-07 не должен быть снят постобработкой"
        )

        day_14 = next(d for d in schedule.days if d.date == date(2025, 3, 14))
        assert "Хабаровск 2" in day_14.night, (
            "Пин Хабаровск 2 -> ночь 2025-03-14 не должен быть снят постобработкой"
        )

    def test_schedule_covered_with_pins(self):
        emps = _base_team()
        pins = [
            PinnedAssignment(
                date=date(2025, 3, 5), employee_name="Москва 2", shift=ShiftType.MORNING
            ),
            PinnedAssignment(
                date=date(2025, 3, 10), employee_name="Москва 3", shift=ShiftType.EVENING
            ),
        ]
        config = Config(month=3, year=2025, seed=42, employees=emps, pins=pins)
        schedule = generate_schedule(config, set())

        for day in schedule.days:
            assert day.is_covered(), f"Смены не покрыты на {day.date}"
