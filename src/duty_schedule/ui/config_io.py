from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st
import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from duty_schedule._errors_fmt import format_validation_errors
from duty_schedule.models import Config, Employee, PinnedAssignment, VacationPeriod
from duty_schedule.ui.mappings import (
    _CITY_TO_RU,
    _EMPTY_PIN_ROW,
    _RU_TO_CITY,
    _RU_TO_SHIFT,
    _RU_TO_STYPE,
    _SHIFT_TO_RU,
    _STYPE_TO_RU,
    _EmployeeDates,
)


@dataclass
class ConfigTables:
    employees: pd.DataFrame
    pins: pd.DataFrame
    employee_dates: dict[str, _EmployeeDates]


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _optional_number(value: Any) -> Any:
    return None if not _text(value) else value


def parse_config_yaml(raw: str) -> Config:
    try:
        return Config.model_validate(yaml.safe_load(raw))
    except yaml.YAMLError as exc:
        raise ValueError(f"Ошибка разбора YAML: {exc}") from exc
    except ValidationError as exc:
        raise ValueError("\n".join(format_validation_errors(exc))) from exc


def dump_config_yaml(config: Config) -> str:
    return str(yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True, sort_keys=False))


def _emp_dates_from_yaml(emp: dict) -> _EmployeeDates:
    return {
        "vacations": [
            (VacationPeriod.model_validate(v).start, VacationPeriod.model_validate(v).end)
            for v in emp.get("vacations", [])
        ],
        "sick_leaves": [
            (VacationPeriod.model_validate(v).start, VacationPeriod.model_validate(v).end)
            for v in emp.get("sick_leaves", [])
        ],
        "unavailable": [date.fromisoformat(str(d)) for d in emp.get("unavailable_dates", [])],
        "days_off_weekly": list(emp.get("days_off_weekly", [])),
    }


def config_to_tables(config: Config) -> ConfigTables:
    rows = []
    employee_dates = {}
    for employee in config.employees:
        rows.append(
            {
                "ID": employee.employee_id,
                "Имя": employee.name,
                "Город": _CITY_TO_RU[employee.city],
                "График": _STYPE_TO_RU[employee.schedule_type],
                "Дежурный": employee.on_duty,
                "Всегда на деж.": employee.always_on_duty,
                "Только утро": employee.morning_only,
                "Только вечер": employee.evening_only,
                "Предпочт. смена": (
                    _SHIFT_TO_RU.get(employee.preferred_shift, "")
                    if employee.preferred_shift is not None
                    else ""
                ),
                "Макс. подряд": employee.max_consecutive_working,
            }
        )
        employee_dates[employee.employee_id] = _emp_dates_from_yaml(
            employee.model_dump(mode="json")
        )
    frame = pd.DataFrame(rows)
    frame.attrs["config"] = config.model_dump(mode="json")
    return ConfigTables(
        frame,
        _pins_list_to_df([p.model_dump(mode="json") for p in config.pins], config.year),
        employee_dates,
    )


def employees_from_table(
    df: pd.DataFrame, employee_dates: dict | None = None, base_config: Config | None = None
) -> list[Employee]:
    by_id = {e.employee_id: e for e in base_config.employees} if base_config else {}
    by_name = {e.name: e for e in base_config.employees} if base_config else {}
    result = []
    for _, row in df.iterrows():
        name = _text(row.get("Имя"))
        if not name:
            continue
        employee_id = _text(row.get("ID"))
        previous = by_id.get(employee_id) or by_name.get(name)
        data = previous.model_dump(mode="json") if previous else {}
        data.update(
            {
                "name": name,
                "employee_id": employee_id or (previous.employee_id if previous else ""),
                "city": _RU_TO_CITY.get(_text(row.get("Город")), _text(row.get("Город"))),
                "schedule_type": _RU_TO_STYPE.get(
                    _text(row.get("График")), _text(row.get("График"))
                ),
            }
        )
        for column, field, default in (
            ("Дежурный", "on_duty", True),
            ("Всегда на деж.", "always_on_duty", False),
            ("Только утро", "morning_only", False),
            ("Только вечер", "evening_only", False),
        ):
            value = row.get(column, default)
            data[field] = default if not _text(value) else value
        preference = _text(row.get("Предпочт. смена"))
        data["preferred_shift"] = _RU_TO_SHIFT.get(preference, preference) if preference else None
        data["max_consecutive_working"] = _optional_number(row.get("Макс. подряд"))
        dates = employee_dates or {}
        periods = dates.get(employee_id, dates.get(name))
        if periods is not None:
            for field in ("vacations", "sick_leaves"):
                if field in periods:
                    data[field] = [
                        {"start": start.isoformat(), "end": end.isoformat()}
                        for start, end in periods[field]
                    ]
            if "unavailable" in periods:
                data["unavailable_dates"] = [d.isoformat() for d in periods["unavailable"]]
            if "days_off_weekly" in periods:
                data["days_off_weekly"] = list(periods["days_off_weekly"])
        result.append(Employee.model_validate(data))
    return result


def config_from_tables(
    df: pd.DataFrame,
    base_config: Config,
    employee_dates: dict | None = None,
    pins_df: pd.DataFrame | None = None,
) -> Config:
    employees = employees_from_table(df, employee_dates, base_config)
    names_by_id = {employee.employee_id: employee.name for employee in employees}
    rename = {
        employee.name: names_by_id.get(employee.employee_id, employee.name)
        for employee in base_config.employees
    }
    data = base_config.model_dump(mode="json")
    data["employees"] = [employee.model_dump(mode="json") for employee in employees]
    if pins_df is not None:
        data["pins"] = _pins_df_to_list(pins_df, base_config.year)
    for field in ("pins", "carry_over", "norm_choices", "approvals"):
        for item in data[field]:
            item["employee_name"] = names_by_id.get(
                item.get("employee_id"), rename.get(item["employee_name"], item["employee_name"])
            )
    return Config.model_validate(data)


def _pins_df_to_list(pins_df: pd.DataFrame, year: int) -> list[dict]:
    result = []
    for _, row in pins_df.iterrows():
        raw_date = row.get("Дата")
        employee_name = _text(row.get("Сотрудник"))
        shift_ru = _text(row.get("Смена"))
        if not _text(raw_date) and not employee_name:
            continue
        if not _text(raw_date) or not employee_name or not shift_ru:
            raise ValueError("Для закрепления нужны дата, сотрудник и смена")
        if isinstance(raw_date, date):
            day = raw_date
        else:
            text = _text(raw_date)
            day = (
                date.fromisoformat(text)
                if len(text) == 10
                else datetime.strptime(f"{text}.{year}", "%d.%m.%Y").date()
            )
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            raise ValueError(f"Неизвестная смена: {shift_ru}")
        pin = PinnedAssignment(
            date=day,
            employee_name=employee_name,
            shift=shift,
            working_hours=_optional_number(row.get("Часы «Р»")),
        )
        result.append(pin.model_dump(mode="json"))
    return result


def _pins_list_to_df(pins: list[dict], year: int) -> pd.DataFrame:
    rows = []
    for item in pins:
        pin = PinnedAssignment.model_validate(item)
        rows.append(
            {
                "Дата": pin.date,
                "Сотрудник": pin.employee_name,
                "Смена": _SHIFT_TO_RU[pin.shift],
                "Часы «Р»": pin.working_hours,
            }
        )
    if not rows:
        rows = [{**_EMPTY_PIN_ROW, "Часы «Р»": None}]
    return pd.DataFrame(rows)


def _emp_dates_to_yaml_fields(name: str) -> tuple[list[dict], list[str]]:
    settings = st.session_state["employee_dates"].get(name, {})
    return (
        [
            {"start": start.isoformat(), "end": end.isoformat()}
            for start, end in settings.get("vacations", [])
        ],
        [day.isoformat() for day in settings.get("unavailable", [])],
    )


def _df_to_yaml(
    df: pd.DataFrame,
    month: int,
    year: int,
    seed: int,
    employee_dates: dict | None = None,
    pins_df: pd.DataFrame | None = None,
    carry_over: list[dict] | None = None,
    optimization_priority: str | None = None,
) -> str:
    source = df.attrs.get("config")
    if source is None:
        source = {
            "month": month,
            "year": year,
            "employees": [
                e.model_dump(mode="json") for e in employees_from_table(df, employee_dates)
            ],
        }
    base = Config.model_validate(source)
    config = config_from_tables(df, base, employee_dates, pins_df)
    data = config.model_dump(mode="json")
    data.update(
        {"month": month, "year": year, "seed": seed, "optimization_priority": optimization_priority}
    )
    if carry_over is not None:
        data["carry_over"] = carry_over
    return dump_config_yaml(Config.model_validate(data))


def _yaml_to_df(
    raw_yaml: str, year: int
) -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    list[dict],
    int,
    int,
    int,
    dict,
    str | None,
    str | None,
]:
    try:
        config = parse_config_yaml(raw_yaml)
        tables = config_to_tables(config)
    except (ValueError, TypeError) as exc:
        return None, None, [], 0, 0, 42, {}, str(exc), None
    return (
        tables.employees,
        tables.pins,
        [carry.model_dump(mode="json") for carry in config.carry_over],
        config.month,
        config.year,
        config.seed,
        tables.employee_dates,
        None,
        config.optimization_priority,
    )
