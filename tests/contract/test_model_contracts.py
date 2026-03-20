from __future__ import annotations

from datetime import date

import pytest

from duty_schedule.models import (
    CarryOverState,
    City,
    Config,
    DaySchedule,
    Employee,
    PinnedAssignment,
    Schedule,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)


class TestEmployeeSerializationRoundtrip:
    def test_basic_employee(self):
        emp = Employee(name="Тест", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        data = emp.model_dump()
        restored = Employee.model_validate(data)
        assert restored == emp

    def test_employee_with_all_fields(self):
        emp = Employee(
            name="Полный",
            city=City.KHABAROVSK,
            schedule_type=ScheduleType.FIVE_TWO,
            on_duty=False,
            morning_only=False,
            evening_only=False,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 5))],
            unavailable_dates=[date(2025, 3, 15)],
            preferred_shift=ShiftType.NIGHT,
            days_off_weekly=[5, 6],
            max_consecutive_working=5,
        )
        data = emp.model_dump()
        restored = Employee.model_validate(data)
        assert restored == emp

    def test_employee_json_roundtrip(self):
        emp = Employee(
            name="JSON",
            city=City.MOSCOW,
            schedule_type=ScheduleType.FLEXIBLE,
            vacations=[VacationPeriod(start=date(2025, 3, 1), end=date(2025, 3, 3))],
        )
        json_str = emp.model_dump_json()
        restored = Employee.model_validate_json(json_str)
        assert restored == emp


class TestConfigSerializationRoundtrip:
    def _make_config(self) -> Config:
        employees = [
            Employee(name=f"М{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(4)
        ] + [
            Employee(name=f"Х{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
            for i in range(2)
        ]
        return Config(
            month=3,
            year=2025,
            seed=42,
            employees=employees,
            pins=[
                PinnedAssignment(date=date(2025, 3, 1), employee_name="М0", shift=ShiftType.MORNING)
            ],
            carry_over=[
                CarryOverState(
                    employee_name="М0", last_shift=ShiftType.MORNING, consecutive_working=3
                )
            ],
        )

    def test_config_roundtrip(self):
        cfg = self._make_config()
        data = cfg.model_dump()
        restored = Config.model_validate(data)
        assert restored.month == cfg.month
        assert restored.year == cfg.year
        assert len(restored.employees) == len(cfg.employees)
        assert len(restored.pins) == len(cfg.pins)
        assert len(restored.carry_over) == len(cfg.carry_over)

    def test_config_json_roundtrip(self):
        cfg = self._make_config()
        json_str = cfg.model_dump_json()
        restored = Config.model_validate_json(json_str)
        assert restored == cfg


class TestScheduleSerializationRoundtrip:
    def test_schedule_roundtrip(self, minimal_config):
        schedule = Schedule(
            config=minimal_config,
            days=[
                DaySchedule(
                    date=date(2025, 3, 1),
                    is_holiday=False,
                    morning=["Иванов Иван"],
                    evening=["Петров Пётр"],
                    night=["Дальнев Дмитрий"],
                ),
            ],
            metadata={"total_nights": 1},
        )
        data = schedule.model_dump()
        restored = Schedule.model_validate(data)
        assert len(restored.days) == 1
        assert restored.days[0].morning == ["Иванов Иван"]
        assert restored.metadata["total_nights"] == 1


class TestEnumSerialization:
    @pytest.mark.parametrize("city", list(City))
    def test_city_roundtrip(self, city):
        assert City(city.value) == city

    @pytest.mark.parametrize("shift", list(ShiftType))
    def test_shift_type_roundtrip(self, shift):
        assert ShiftType(shift.value) == shift

    @pytest.mark.parametrize("schedule_type", list(ScheduleType))
    def test_schedule_type_roundtrip(self, schedule_type):
        assert ScheduleType(schedule_type.value) == schedule_type
