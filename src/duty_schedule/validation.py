from __future__ import annotations

from collections import defaultdict
from datetime import date

from duty_schedule.models import City, Config, ShiftType


def validate_pre_generation(
    config: Config,
    holidays: set[date],
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    emp_by_name = {e.name: e for e in config.employees}

    duty_pins: dict[date, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for pin in config.pins:
        emp = emp_by_name.get(pin.employee_name)
        if emp is None:
            continue

        if pin.shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT):
            duty_pins[pin.date][pin.shift.value].append(pin.employee_name)

    for d, shifts in duty_pins.items():
        for shift_key, names in shifts.items():
            if len(names) > 1:
                errors.append(
                    f"{d.isoformat()}: несколько сотрудников закреплены на {shift_key}: "
                    f"{', '.join(names)}"
                )

    for pin in config.pins:
        emp = emp_by_name.get(pin.employee_name)
        if emp is None:
            continue
        if emp.is_on_vacation(pin.date):
            errors.append(
                f"{pin.date.isoformat()}: пин «{emp.name}» на {pin.shift.value} "
                f"конфликтует с отпуском"
            )
        if pin.date in emp.unavailable_dates:
            errors.append(
                f"{pin.date.isoformat()}: пин «{emp.name}» на {pin.shift.value} "
                f"конфликтует с недоступностью"
            )

    for pin in config.pins:
        emp = emp_by_name.get(pin.employee_name)
        if emp is None:
            continue
        if emp.city == City.MOSCOW and pin.shift == ShiftType.NIGHT:
            errors.append(
                f"{pin.date.isoformat()}: «{emp.name}» (Москва) не может быть на ночной смене"
            )
        if emp.city == City.KHABAROVSK and pin.shift in (ShiftType.MORNING, ShiftType.EVENING):
            errors.append(
                f"{pin.date.isoformat()}: «{emp.name}» (Хабаровск) не может быть "
                f"на {pin.shift.value}"
            )
        if emp.morning_only and pin.shift == ShiftType.EVENING:
            errors.append(
                f"{pin.date.isoformat()}: «{emp.name}» (morning_only) не может быть на вечерней"
            )
        if emp.evening_only and pin.shift == ShiftType.MORNING:
            errors.append(
                f"{pin.date.isoformat()}: «{emp.name}» (evening_only) не может быть на утренней"
            )

    from duty_schedule.calendar import get_all_days

    all_days = get_all_days(config.year, config.month)
    for day in all_days:
        available_duty = []
        for emp in config.employees:
            if not emp.on_duty:
                continue
            if emp.is_blocked(day):
                continue
            available_duty.append(emp)

        required_shifts = 3
        if len(available_duty) < required_shifts:
            warnings.append(
                f"{day.isoformat()}: доступных дежурных ({len(available_duty)}) "
                f"может не хватить для {required_shifts} обязательных смен"
            )

    return errors, warnings
