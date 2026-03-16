from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    Config,
    Employee,
    PinnedAssignment,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)
from duty_schedule.validation import validate_pre_generation


def _base_employees() -> list[Employee]:
    msk = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE, on_duty=True)
        for i in range(1, 5)
    ]
    khb = [
        Employee(
            name=f"K{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE, on_duty=True
        )
        for i in range(1, 3)
    ]
    return msk + khb


def test_no_errors_clean_config() -> None:
    config = Config(month=3, year=2026, employees=_base_employees())
    errors, warnings = validate_pre_generation(config, set())
    assert errors == []


def test_pin_on_vacation_date() -> None:
    emps = _base_employees()
    emps[0] = emps[0].model_copy(
        update={"vacations": [VacationPeriod(start=date(2026, 3, 10), end=date(2026, 3, 15))]}
    )
    config = Config(
        month=3,
        year=2026,
        employees=emps,
        pins=[
            PinnedAssignment(date=date(2026, 3, 12), employee_name="M1", shift=ShiftType.MORNING)
        ],
    )
    errors, warnings = validate_pre_generation(config, set())
    assert any("отпуском" in e for e in errors)


def test_pin_on_unavailable_date() -> None:
    emps = _base_employees()
    emps[0] = emps[0].model_copy(update={"unavailable_dates": [date(2026, 3, 5)]})
    config = Config(
        month=3,
        year=2026,
        employees=emps,
        pins=[PinnedAssignment(date=date(2026, 3, 5), employee_name="M1", shift=ShiftType.MORNING)],
    )
    errors, warnings = validate_pre_generation(config, set())
    assert any("недоступностью" in e for e in errors)


def test_city_incompatible_pin() -> None:
    emps = _base_employees()
    config = Config(
        month=3,
        year=2026,
        employees=emps,
        pins=[PinnedAssignment(date=date(2026, 3, 5), employee_name="K1", shift=ShiftType.MORNING)],
    )
    errors, warnings = validate_pre_generation(config, set())
    assert any("Хабаровск" in e for e in errors)


def test_morning_only_pinned_evening() -> None:
    emps = _base_employees()
    emps[0] = emps[0].model_copy(update={"morning_only": True})
    config = Config(
        month=3,
        year=2026,
        employees=emps,
        pins=[PinnedAssignment(date=date(2026, 3, 5), employee_name="M1", shift=ShiftType.EVENING)],
    )
    errors, warnings = validate_pre_generation(config, set())
    assert any("morning_only" in e for e in errors)
