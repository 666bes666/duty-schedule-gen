from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import ValidationError

from duty_schedule._errors_fmt import format_validation_errors
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)
from duty_schedule.ui.mappings import (
    _WEEKDAY_RU,
)


def _build_employees(
    df: pd.DataFrame,
    employee_dates: dict | None = None,
) -> tuple[list[Employee], list[str]]:
    from duty_schedule.ui.config_io import employees_from_table

    try:
        return employees_from_table(df, employee_dates), []
    except (ValueError, TypeError) as exc:
        return [], [str(exc)]


def _schedule_to_edit_df(schedule: Schedule) -> pd.DataFrame:
    rows = []
    for d in schedule.days:
        rows.append(
            {
                "Дата": f"{d.date.day:02d}.{d.date.month:02d} {_WEEKDAY_RU[d.date.weekday()]}",
                "Утро 08–17": list(d.morning),
                "Вечер 15–00": list(d.evening),
                "Ночь 00–08": list(d.night),
                "Рабочий день": list(d.workday),
            }
        )
    return pd.DataFrame(rows)


def _edit_df_to_schedule(df: pd.DataFrame, schedule: Schedule) -> Schedule:
    new_days = []
    for (_, row), orig_day in zip(
        df.iterrows(),
        schedule.days,
        strict=False,
    ):
        _row = row

        def _names(col: str, _r: Any = _row) -> list[str]:
            value = _r.get(col, [])
            if value is None or (isinstance(value, float) and pd.isna(value)):
                value = []
            if isinstance(value, str):
                value = [value] if value else []
            names = list(value)
            known = {employee.name for employee in schedule.config.employees}
            if any(name not in known for name in names):
                raise ValueError(f"{col}: выберите сотрудника из состава")
            return names

        all_assigned = set(
            _names("Утро 08–17")
            + _names("Вечер 15–00")
            + _names("Ночь 00–08")
            + _names("Рабочий день")
        )
        orig_all = set(
            orig_day.morning
            + orig_day.evening
            + orig_day.night
            + orig_day.workday
            + orig_day.day_off
            + orig_day.vacation
            + orig_day.sick_leave
        )
        day_off = [n for n in orig_day.day_off if n not in all_assigned]
        vacation = list(orig_day.vacation)
        sick_leave = list(orig_day.sick_leave)
        unassigned = [
            n
            for n in orig_all
            if n not in all_assigned
            and n not in day_off
            and n not in vacation
            and n not in sick_leave
        ]
        day_off.extend(unassigned)

        new_days.append(
            DaySchedule(
                date=orig_day.date,
                is_holiday=orig_day.is_holiday,
                morning=_names("Утро 08–17"),
                evening=_names("Вечер 15–00"),
                night=_names("Ночь 00–08"),
                workday=_names("Рабочий день"),
                day_off=day_off,
                vacation=vacation,
                sick_leave=sick_leave,
                workday_hours={
                    name: hours
                    for name, hours in orig_day.workday_hours.items()
                    if name in _names("Рабочий день")
                },
            )
        )

    meta = dict(schedule.metadata)
    meta["total_mornings"] = sum(len(d.morning) for d in new_days)
    meta["total_evenings"] = sum(len(d.evening) for d in new_days)
    meta["total_nights"] = sum(len(d.night) for d in new_days)
    return Schedule.model_construct(config=schedule.config, days=new_days, metadata=meta)


def _validate_edited_schedule(schedule: Schedule) -> list[str]:
    from duty_schedule.scheduler.validation import validate_schedule_result

    return [item.detail for item in validate_schedule_result(schedule).diagnostics]


def _validate_config(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    active = [row for _, row in df.iterrows() if str(row["Имя"]).strip()]
    if not active:
        errors.append("Добавьте хотя бы одного сотрудника.")
        return errors, warnings

    employees: list[Employee] = []
    for row in active:
        city = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
        stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO
        try:
            employees.append(
                Employee(
                    name=str(row["Имя"]).strip(),
                    city=city,
                    schedule_type=stype,
                    on_duty=bool(row.get("Дежурный", True)),
                    always_on_duty=bool(row.get("Всегда на деж.", False)),
                    morning_only=bool(row.get("Только утро", False)),
                    evening_only=bool(row.get("Только вечер", False)),
                )
            )
        except ValidationError as exc:
            errors.extend(format_validation_errors(exc))

    if employees:
        try:
            Config(month=1, year=2026, employees=employees)
        except ValidationError as exc:
            errors.extend(format_validation_errors(exc))

    return errors, warnings
