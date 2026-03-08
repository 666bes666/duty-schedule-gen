from __future__ import annotations

import contextlib
from datetime import date, datetime
from typing import Any

import pandas as pd
import streamlit as st
import yaml  # type: ignore[import-untyped]

from duty_schedule.models import ShiftType
from duty_schedule.ui.mappings import (
    _CITY_TO_RU,
    _DEFAULT_ROWS,
    _EMPTY_PIN_ROW,
    _RU_TO_CITY,
    _RU_TO_SHIFT,
    _RU_TO_STYPE,
    _SHIFT_TO_RU,
    _STYPE_TO_RU,
    _EmployeeDates,
)


def _emp_dates_to_yaml_fields(name: str) -> tuple[list[dict], list[str]]:
    cfg = st.session_state["employee_dates"].get(name, {})
    vac_yaml = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in cfg.get("vacations", [])]
    unavail_yaml = [d.isoformat() for d in cfg.get("unavailable", [])]
    return vac_yaml, unavail_yaml


def _emp_dates_from_yaml(emp: dict) -> _EmployeeDates:
    vacations = []
    for v in emp.get("vacations", []):
        try:
            s = date.fromisoformat(str(v["start"]))
            e = date.fromisoformat(str(v["end"]))
            vacations.append((s, e))
        except (ValueError, KeyError):
            pass
    unavailable = []
    for d in emp.get("unavailable_dates", []):
        with contextlib.suppress(ValueError):
            unavailable.append(date.fromisoformat(str(d)))
    days_off_weekly = []
    for d in emp.get("days_off_weekly", []) or []:
        with contextlib.suppress(ValueError, TypeError):
            days_off_weekly.append(int(d))
    return {"vacations": vacations, "unavailable": unavailable, "days_off_weekly": days_off_weekly}


def _df_to_yaml(
    df: pd.DataFrame,
    month: int,
    year: int,
    seed: int,
    employee_dates: dict | None = None,
    pins_df: pd.DataFrame | None = None,
    carry_over: list[dict] | None = None,
) -> str:
    ed = employee_dates or {}
    employees = []

    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue

        _emp_cfg = ed.get(name, {"vacations": [], "unavailable": []})
        vac_yaml = [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in _emp_cfg.get("vacations", [])
        ]
        unavail_yaml = [d.isoformat() for d in _emp_cfg.get("unavailable", [])]

        pref_shift_ru = str(row.get("Предпочт. смена", "")).strip()
        pref_shift = _RU_TO_SHIFT.get(pref_shift_ru)

        workload_raw = row.get("Загрузка%", 100)
        try:
            workload_pct = int(str(workload_raw).strip()) if str(workload_raw).strip() else 100
            workload_pct = max(1, min(100, workload_pct))
        except (ValueError, TypeError):
            workload_pct = 100

        days_off_weekly: list[int] = _emp_cfg.get("days_off_weekly", [])

        def _parse_limit(val: Any) -> int | None:
            try:
                v = int(val)  # type: ignore[arg-type]
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        max_morning = _parse_limit(row.get("Макс. утренних"))
        max_evening = _parse_limit(row.get("Макс. вечерних"))
        max_night = _parse_limit(row.get("Макс. ночных"))
        max_cw = _parse_limit(row.get("Макс. подряд"))
        max_consec_morning = _parse_limit(row.get("Подряд: утро"))
        max_consec_evening = _parse_limit(row.get("Подряд: вечер"))
        max_consec_workday = _parse_limit(row.get("Подряд: день"))
        group = str(row.get("Группа", "")).strip() or None

        emp: dict = {
            "name": name,
            "city": _RU_TO_CITY.get(str(row["Город"]), "moscow"),
            "schedule_type": _RU_TO_STYPE.get(str(row["График"]), "flexible"),
            "on_duty": bool(row["Дежурный"]),
            "always_on_duty": bool(row.get("Всегда на деж.", False)),
            "morning_only": bool(row["Только утро"]),
            "evening_only": bool(row["Только вечер"]),
        }
        if vac_yaml:
            emp["vacations"] = vac_yaml
        if unavail_yaml:
            emp["unavailable_dates"] = unavail_yaml
        if pref_shift is not None:
            emp["preferred_shift"] = str(pref_shift)
        if workload_pct != 100:
            emp["workload_pct"] = workload_pct
        if days_off_weekly:
            emp["days_off_weekly"] = days_off_weekly
        if max_morning is not None:
            emp["max_morning_shifts"] = max_morning
        if max_evening is not None:
            emp["max_evening_shifts"] = max_evening
        if max_night is not None:
            emp["max_night_shifts"] = max_night
        if max_cw is not None:
            emp["max_consecutive_working"] = max_cw
        if max_consec_morning is not None:
            emp["max_consecutive_morning"] = max_consec_morning
        if max_consec_evening is not None:
            emp["max_consecutive_evening"] = max_consec_evening
        if max_consec_workday is not None:
            emp["max_consecutive_workday"] = max_consec_workday
        if group is not None:
            emp["group"] = group
        employees.append(emp)

    config_dict: dict = {
        "month": int(month),
        "year": int(year),
        "seed": int(seed),
        "employees": employees,
    }
    if pins_df is not None:
        pins_list = _pins_df_to_list(pins_df, year)
        if pins_list:
            config_dict["pins"] = pins_list
    if carry_over:
        config_dict["carry_over"] = carry_over
    result: str = yaml.dump(
        config_dict,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return result


def _pins_df_to_list(pins_df: pd.DataFrame, year: int) -> list[dict]:
    result = []
    for _, row in pins_df.iterrows():
        raw_date = row.get("Дата")
        emp_name = str(row.get("Сотрудник", "")).strip()
        shift_ru = str(row.get("Смена", "")).strip()
        if not raw_date or not emp_name or not shift_ru:
            continue
        if isinstance(raw_date, date):
            d = raw_date
        else:
            try:
                d = datetime.strptime(f"{str(raw_date).strip()}.{year}", "%d.%m.%Y").date()
            except ValueError:
                continue
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            continue
        result.append({"date": d.isoformat(), "employee_name": emp_name, "shift": str(shift)})
    return result


def _pins_list_to_df(pins: list[dict], year: int) -> pd.DataFrame:
    rows = []
    for p in pins:
        try:
            d = date.fromisoformat(str(p["date"]))
        except (ValueError, KeyError):
            continue
        if d.year != year:
            continue
        shift_str = str(p.get("shift", ""))
        shift_ru = _SHIFT_TO_RU.get(ShiftType(shift_str), "Утро") if shift_str else "Утро"
        rows.append(
            {
                "Дата": d,
                "Сотрудник": str(p.get("employee_name", "")),
                "Смена": shift_ru,
            }
        )
    return pd.DataFrame(rows) if rows else pd.DataFrame([_EMPTY_PIN_ROW])


def _yaml_to_df(
    raw_yaml: str,
    year: int,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[dict], int, int, int, dict, str | None]:
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return None, None, [], 0, 0, 42, {}, f"Ошибка разбора YAML: {e}"

    if not isinstance(data, dict):
        return None, None, [], 0, 0, 42, {}, "Неверный формат файла конфигурации."

    month = int(data.get("month", date.today().month))
    year_val = int(data.get("year", year))
    seed = int(data.get("seed", 42))

    rows = []
    employee_dates: dict = {}
    for emp in data.get("employees", []):
        name = emp.get("name", "")

        employee_dates[name] = _emp_dates_from_yaml(emp)

        pref_shift_raw = emp.get("preferred_shift", "") or ""
        pref_shift_ru = _SHIFT_TO_RU.get(ShiftType(pref_shift_raw), "") if pref_shift_raw else ""

        rows.append(
            {
                "Имя": name,
                "Город": _CITY_TO_RU.get(emp.get("city", "moscow"), "Москва"),
                "График": _STYPE_TO_RU.get(emp.get("schedule_type", "flexible"), "Гибкий"),
                "Дежурный": bool(emp.get("on_duty", True)),
                "Всегда на деж.": bool(emp.get("always_on_duty", False)),
                "Только утро": bool(emp.get("morning_only", False)),
                "Только вечер": bool(emp.get("evening_only", False)),
                "Предпочт. смена": pref_shift_ru,
                "Загрузка%": int(emp.get("workload_pct", 100)),
                "Макс. утренних": emp.get("max_morning_shifts"),
                "Макс. вечерних": emp.get("max_evening_shifts"),
                "Макс. ночных": emp.get("max_night_shifts"),
                "Макс. подряд": emp.get("max_consecutive_working"),
                "Подряд: утро": emp.get("max_consecutive_morning"),
                "Подряд: вечер": emp.get("max_consecutive_evening"),
                "Подряд: день": emp.get("max_consecutive_workday"),
                "Группа": emp.get("group", "") or "",
            }
        )

    if not rows:
        rows = _DEFAULT_ROWS.copy()

    pins_df = _pins_list_to_df(data.get("pins", []), year_val)
    carry_over = data.get("carry_over", [])
    return pd.DataFrame(rows), pins_df, carry_over, month, year_val, seed, employee_dates, None
