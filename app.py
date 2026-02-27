"""Streamlit-интерфейс генератора графика дежурств."""

from __future__ import annotations

import contextlib
import tempfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from duty_schedule.calendar import CalendarError, fetch_holidays
from duty_schedule.export.xls import export_xls
from duty_schedule.models import (
    CarryOverState,
    City,
    Config,
    Employee,
    PinnedAssignment,
    ScheduleType,
    ShiftType,
    VacationPeriod,
    collect_config_issues,
)
from duty_schedule.scheduler import ScheduleError, generate_schedule


MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
_WEEKDAY_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_CITY_TO_RU  = {"moscow": "Москва", "khabarovsk": "Хабаровск"}
_RU_TO_CITY  = {"Москва": "moscow", "Хабаровск": "khabarovsk"}
_STYPE_TO_RU = {"flexible": "Гибкий", "5/2": "5/2"}
_RU_TO_STYPE = {"Гибкий": "flexible", "5/2": "5/2"}

_WEEKDAY_SHORT_TO_INT = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
_INT_TO_WEEKDAY_SHORT = {v: k.capitalize() for k, v in _WEEKDAY_SHORT_TO_INT.items()}
_WEEKDAY_INT_TO_RU    = {0: "Пн", 1: "Вт", 2: "Ср", 3: "Чт", 4: "Пт", 5: "Сб", 6: "Вс"}
_WEEKDAY_RU_TO_INT    = {v: k for k, v in _WEEKDAY_INT_TO_RU.items()}
_WEEKDAY_OPTIONS      = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_EMPTY_ROW = {
    "Имя": "",
    "Город": "Москва",
    "График": "Гибкий",
    "Дежурный": True,
    "Всегда на деж.": False,
    "Только утро": False,
    "Только вечер": False,
    "Предпочт. смена": "",
    "Загрузка%": 100,
    "Макс. утренних": None,
    "Макс. вечерних": None,
    "Макс. ночных": None,
    "Макс. подряд": 5,
    "Группа": "",
}

_DEFAULT_ROWS = [
    {**_EMPTY_ROW, "Имя": "Левченко",    "График": "5/2",                          "Дежурный": False},
    {**_EMPTY_ROW, "Имя": "Хадзугов",    "График": "5/2",                          "Дежурный": False},
    {**_EMPTY_ROW, "Имя": "Абашина",                       "Предпочт. смена": "Утро"},
    {**_EMPTY_ROW, "Имя": "Екат",         "График": "5/2", "Только утро": True, "Всегда на деж.": True},
    {**_EMPTY_ROW, "Имя": "Ищенко"},
    {**_EMPTY_ROW, "Имя": "Пантелеймон"},
    {**_EMPTY_ROW, "Имя": "Ужахов"},
    {**_EMPTY_ROW, "Имя": "Кочкин",      "Город": "Хабаровск", "График": "5/2",   "Дежурный": False},
    {**_EMPTY_ROW, "Имя": "Вика",         "Город": "Хабаровск"},
    {**_EMPTY_ROW, "Имя": "Голубев",     "Город": "Хабаровск"},
    {**_EMPTY_ROW, "Имя": "Карпенко",    "Город": "Хабаровск"},
]

_TABLE_KEY_PREFIX = "employees_table"

_SHIFTS_RU = ["Утро", "Вечер", "Ночь", "Рабочий день", "Выходной"]
_RU_TO_SHIFT = {
    "Утро":         ShiftType.MORNING,
    "Вечер":        ShiftType.EVENING,
    "Ночь":         ShiftType.NIGHT,
    "Рабочий день": ShiftType.WORKDAY,
    "Выходной":     ShiftType.DAY_OFF,
}
_SHIFT_TO_RU = {v: k for k, v in _RU_TO_SHIFT.items()}

_EMPTY_PIN_ROW = {"Дата": None, "Сотрудник": "", "Смена": "Утро"}

_EmployeeDates = dict


def _init_state() -> None:
    if "table_version" not in st.session_state:
        st.session_state["table_version"] = 0
    if "employees_df" not in st.session_state:
        st.session_state["employees_df"] = pd.DataFrame(_DEFAULT_ROWS)
    if "cfg_month" not in st.session_state:
        st.session_state["cfg_month"] = date.today().month
    if "cfg_year" not in st.session_state:
        st.session_state["cfg_year"] = date.today().year
    if "cfg_seed" not in st.session_state:
        st.session_state["cfg_seed"] = 42
    if "pins_df" not in st.session_state:
        st.session_state["pins_df"] = pd.DataFrame([_EMPTY_PIN_ROW])
    if "carry_over" not in st.session_state:
        st.session_state["carry_over"] = []
    if "employee_dates" not in st.session_state:
        st.session_state["employee_dates"] = {}
    if "_df_for_download" not in st.session_state:
        st.session_state["_df_for_download"] = pd.DataFrame(_DEFAULT_ROWS)
    if "_pins_for_download" not in st.session_state:
        st.session_state["_pins_for_download"] = pd.DataFrame([_EMPTY_PIN_ROW])
    if "last_result" not in st.session_state:
        st.session_state["last_result"] = None


def _bump_table() -> None:
    st.session_state["table_version"] += 1


def _get_emp_dates(name: str) -> _EmployeeDates:
    """Вернуть (и создать при необходимости) конфиг дат для сотрудника."""
    ed = st.session_state["employee_dates"]
    if name not in ed:
        ed[name] = {"vacations": [], "unavailable": [], "days_off_weekly": []}
    elif "days_off_weekly" not in ed[name]:
        ed[name]["days_off_weekly"] = []
    return ed[name]


def _emp_dates_to_yaml_fields(name: str) -> tuple[list[dict], list[str]]:
    """Вернуть vacations/unavailable_dates в формате YAML-словарей."""
    cfg = st.session_state["employee_dates"].get(name, {})
    vac_yaml = [
        {"start": s.isoformat(), "end": e.isoformat()}
        for s, e in cfg.get("vacations", [])
    ]
    unavail_yaml = [d.isoformat() for d in cfg.get("unavailable", [])]
    return vac_yaml, unavail_yaml


def _emp_dates_from_yaml(emp: dict) -> _EmployeeDates:
    """Распарсить vacations/unavailable_dates из YAML-словаря сотрудника."""
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
    """Сериализовать таблицу сотрудников в YAML."""
    ed = employee_dates or {}
    employees = []

    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue

        _emp_cfg = ed.get(name, {"vacations": [], "unavailable": []})
        vac_yaml = [
            {"start": s.isoformat(), "end": e.isoformat()}
            for s, e in _emp_cfg.get("vacations", [])
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

        def _parse_limit(val: object) -> int | None:
            try:
                v = int(val)
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        max_morning = _parse_limit(row.get("Макс. утренних"))
        max_evening = _parse_limit(row.get("Макс. вечерних"))
        max_night   = _parse_limit(row.get("Макс. ночных"))
        max_cw      = _parse_limit(row.get("Макс. подряд"))
        group = str(row.get("Группа", "")).strip() or None

        emp: dict = {
            "name":          name,
            "city":          _RU_TO_CITY.get(str(row["Город"]), "moscow"),
            "schedule_type": _RU_TO_STYPE.get(str(row["График"]), "flexible"),
            "on_duty":       bool(row["Дежурный"]),
            "always_on_duty": bool(row.get("Всегда на деж.", False)),
            "morning_only":  bool(row["Только утро"]),
            "evening_only":  bool(row["Только вечер"]),
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
        if group is not None:
            emp["group"] = group
        employees.append(emp)

    config_dict: dict = {
        "month": int(month),
        "year":  int(year),
        "seed":  int(seed),
        "employees": employees,
    }
    if pins_df is not None:
        pins_list = _pins_df_to_list(pins_df, year)
        if pins_list:
            config_dict["pins"] = pins_list
    if carry_over:
        config_dict["carry_over"] = carry_over
    return yaml.dump(config_dict, allow_unicode=True, default_flow_style=False, sort_keys=False)


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
        rows.append({
            "Дата":      d,
            "Сотрудник": str(p.get("employee_name", "")),
            "Смена":     shift_ru,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame([_EMPTY_PIN_ROW])


def _yaml_to_df(
    raw_yaml: str, year: int,
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, list[dict], int, int, int, dict, str | None]:
    """Загрузить YAML конфиг.

    Returns:
        (employees_df, pins_df, carry_over, month, year, seed, employee_dates, error)
    """
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        return None, None, [], 0, 0, 42, {}, f"Ошибка разбора YAML: {e}"

    if not isinstance(data, dict):
        return None, None, [], 0, 0, 42, {}, "Неверный формат файла конфигурации."

    month   = int(data.get("month", date.today().month))
    year_val = int(data.get("year", year))
    seed    = int(data.get("seed", 42))

    rows = []
    employee_dates: dict = {}
    for emp in data.get("employees", []):
        name = emp.get("name", "")

        employee_dates[name] = _emp_dates_from_yaml(emp)

        pref_shift_raw = emp.get("preferred_shift", "") or ""
        pref_shift_ru = _SHIFT_TO_RU.get(
            ShiftType(pref_shift_raw), ""
        ) if pref_shift_raw else ""

        rows.append({
            "Имя":             name,
            "Город":           _CITY_TO_RU.get(emp.get("city", "moscow"), "Москва"),
            "График":          _STYPE_TO_RU.get(emp.get("schedule_type", "flexible"), "Гибкий"),
            "Дежурный":        bool(emp.get("on_duty", True)),
            "Всегда на деж.":  bool(emp.get("always_on_duty", False)),
            "Только утро":     bool(emp.get("morning_only", False)),
            "Только вечер":    bool(emp.get("evening_only", False)),
            "Предпочт. смена": pref_shift_ru,
            "Загрузка%":       int(emp.get("workload_pct", 100)),
            "Макс. утренних":  emp.get("max_morning_shifts"),
            "Макс. вечерних":  emp.get("max_evening_shifts"),
            "Макс. ночных":    emp.get("max_night_shifts"),
            "Макс. подряд":    emp.get("max_consecutive_working"),
            "Группа":          emp.get("group", "") or "",
        })

    if not rows:
        rows = _DEFAULT_ROWS.copy()

    pins_df   = _pins_list_to_df(data.get("pins", []), year_val)
    carry_over = data.get("carry_over", [])
    return pd.DataFrame(rows), pins_df, carry_over, month, year_val, seed, employee_dates, None


def _build_employees(
    df: pd.DataFrame,
    employee_dates: dict | None = None,
) -> tuple[list[Employee], list[str]]:
    """DataFrame + employee_dates → список Employee."""
    employees: list[Employee] = []
    errors: list[str] = []
    ed = employee_dates or {}

    for _, row in df.iterrows():
        name = str(row["Имя"]).strip()
        if not name:
            continue

        city  = City.MOSCOW if row["Город"] == "Москва" else City.KHABAROVSK
        stype = ScheduleType.FLEXIBLE if row["График"] == "Гибкий" else ScheduleType.FIVE_TWO

        cfg = ed.get(name, {"vacations": [], "unavailable": []})
        vacations: list[VacationPeriod] = []
        for s, e in cfg.get("vacations", []):
            try:
                vacations.append(VacationPeriod(start=s, end=e))
            except Exception as ex:
                errors.append(f"«{name}»: {ex}")
        unavailable: list[date] = list(cfg.get("unavailable", []))

        pref_shift_ru = str(row.get("Предпочт. смена", "")).strip()
        preferred_shift = _RU_TO_SHIFT.get(pref_shift_ru) if pref_shift_ru else None

        workload_raw = row.get("Загрузка%", 100)
        try:
            workload_pct = int(str(workload_raw).strip()) if str(workload_raw).strip() else 100
            workload_pct = max(1, min(100, workload_pct))
        except (ValueError, TypeError):
            workload_pct = 100

        days_off_weekly: list[int] = cfg.get("days_off_weekly", [])

        def _parse_limit(val: object) -> int | None:
            try:
                v = int(val)
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        max_morning = _parse_limit(row.get("Макс. утренних"))
        max_evening = _parse_limit(row.get("Макс. вечерних"))
        max_night   = _parse_limit(row.get("Макс. ночных"))
        max_cw      = _parse_limit(row.get("Макс. подряд"))
        group = str(row.get("Группа", "")).strip() or None

        try:
            employees.append(Employee(
                name=name, city=city, schedule_type=stype,
                on_duty=bool(row["Дежурный"]),
                always_on_duty=bool(row.get("Всегда на деж.", False)),
                morning_only=bool(row["Только утро"]),
                evening_only=bool(row["Только вечер"]),
                vacations=vacations,
                unavailable_dates=unavailable,
                preferred_shift=preferred_shift,
                workload_pct=workload_pct,
                days_off_weekly=days_off_weekly,
                max_morning_shifts=max_morning,
                max_evening_shifts=max_evening,
                max_night_shifts=max_night,
                max_consecutive_working=max_cw,
                group=group,
            ))
        except Exception as e:
            errors.append(f"«{name}»: {e}")

    return employees, errors


def _schedule_to_edit_df(schedule: object) -> pd.DataFrame:
    rows = []
    for d in schedule.days:
        rows.append({
            "Дата":         f"{d.date.day:02d}.{d.date.month:02d} {_WEEKDAY_RU[d.date.weekday()]}",
            "Утро 08–17":   ", ".join(d.morning),
            "Вечер 15–00":  ", ".join(d.evening),
            "Ночь 00–08":   ", ".join(d.night),
            "Рабочий день": ", ".join(d.workday),
        })
    return pd.DataFrame(rows)


def _edit_df_to_schedule(df: pd.DataFrame, schedule: object) -> object:
    from duty_schedule.models import DaySchedule
    from duty_schedule.models import Schedule as ScheduleModel

    new_days = []
    for (_, row), orig_day in zip(
        df.iterrows(), schedule.days, strict=False
    ):
        _row = row

        def _names(col: str, _r: object = _row) -> list[str]:
            val = str(_r.get(col, "")).strip()
            return [n.strip() for n in val.split(",") if n.strip()] if val else []

        all_assigned = set(
            _names("Утро 08–17") + _names("Вечер 15–00")
            + _names("Ночь 00–08") + _names("Рабочий день")
        )
        orig_all = set(
            orig_day.morning + orig_day.evening + orig_day.night
            + orig_day.workday + orig_day.day_off + orig_day.vacation
        )
        day_off  = [n for n in orig_day.day_off  if n not in all_assigned]
        vacation = [n for n in orig_day.vacation if n not in all_assigned]
        unassigned = [
            n for n in orig_all
            if n not in all_assigned and n not in day_off and n not in vacation
        ]
        day_off.extend(unassigned)

        new_days.append(DaySchedule(
            date=orig_day.date,
            is_holiday=orig_day.is_holiday,
            morning=_names("Утро 08–17"),
            evening=_names("Вечер 15–00"),
            night=_names("Ночь 00–08"),
            workday=_names("Рабочий день"),
            day_off=day_off,
            vacation=vacation,
        ))

    meta = dict(schedule.metadata)
    meta["total_mornings"] = sum(len(d.morning) for d in new_days)
    meta["total_evenings"] = sum(len(d.evening) for d in new_days)
    meta["total_nights"]   = sum(len(d.night)   for d in new_days)
    return ScheduleModel(config=schedule.config, days=new_days, metadata=meta)


def _validate_config(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Проверить конфигурацию перед генерацией.

    Returns:
        (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    active = [row for _, row in df.iterrows() if str(row["Имя"]).strip()]
    if not active:
        errors.append("Добавьте хотя бы одного сотрудника.")
        return errors, warnings

    moscow_duty = [
        r for r in active
        if r["Город"] == "Москва"
        and bool(r.get("Дежурный", True))
    ]
    khab_duty = [
        r for r in active
        if r["Город"] == "Хабаровск"
        and bool(r.get("Дежурный", True))
    ]

    if len(moscow_duty) < 4:
        errors.append(
            f"Москва: {len(moscow_duty)} дежурных, нужно минимум 4."
        )
    if len(khab_duty) < 2:
        errors.append(
            f"Хабаровск: {len(khab_duty)} дежурных, нужно минимум 2."
        )

    for r in active:
        name = str(r["Имя"]).strip()
        if bool(r.get("Только утро")) and bool(r.get("Только вечер")):
            errors.append(
                f"«{name}»: нельзя одновременно «Только утро» и «Только вечер»."
            )
        if bool(r.get("Всегда на деж.", False)):
            if not bool(r.get("Дежурный", True)):
                errors.append(f"«{name}»: «Всегда на деж.» требует включённого «Деж.».")
            if str(r.get("Город", "")) != "Москва":
                errors.append(f"«{name}»: «Всегда на деж.» поддерживается только для Москвы.")
            if not bool(r.get("Только утро")) and not bool(r.get("Только вечер")):
                errors.append(
                    f"«{name}»: «Всегда на деж.» требует указания «Утро▲» или «Вечер▲»."
                )

    return errors, warnings


_CAL_SHIFT_COLORS = {
    "У": "#FFF3CD",
    "В": "#CCE5FF",
    "Н": "#D6CCE5",
    "Р": "#D4EDDA",
    "–": "#F2F3F4",
    "О": "#F5C6CB",
}


def _schedule_to_calendar_df(schedule: object) -> pd.DataFrame:
    """Сводная таблица: строки = сотрудники, столбцы = дни месяца."""
    emp_days: dict[str, dict[str, str]] = {}
    col_order: list[str] = []

    for d in schedule.days:
        header = f"{d.date.day} {_WEEKDAY_RU[d.date.weekday()]}"
        if header not in col_order:
            col_order.append(header)
        for nm in d.morning:
            emp_days.setdefault(nm, {})[header] = "У"
        for nm in d.evening:
            emp_days.setdefault(nm, {})[header] = "В"
        for nm in d.night:
            emp_days.setdefault(nm, {})[header] = "Н"
        for nm in d.workday:
            emp_days.setdefault(nm, {})[header] = "Р"
        for nm in d.day_off:
            emp_days.setdefault(nm, {})[header] = "–"
        for nm in d.vacation:
            emp_days.setdefault(nm, {})[header] = "О"

    rows = {
        name: {col: emp_days[name].get(col, "") for col in col_order}
        for name in sorted(emp_days)
    }
    return pd.DataFrame(rows).T[col_order]


def _style_calendar_cell(val: str) -> str:
    color = _CAL_SHIFT_COLORS.get(str(val), "#FFFFFF")
    return f"background-color: {color}; text-align: center; font-size: 0.85em;"


def _render_calendar(schedule: object) -> None:
    """Цветовой календарь расписания."""
    cal_df = _schedule_to_calendar_df(schedule)
    legend = (
        "🟡 **У** — утро  ·  🔵 **В** — вечер  ·  🟣 **Н** — ночь  ·  "
        "🟢 **Р** — рабочий  ·  ⬜ **–** — выходной  ·  🔴 **О** — отпуск"
    )
    st.caption(legend)
    height = min(600, 35 * (len(cal_df) + 2))
    styled = cal_df.style.map(_style_calendar_cell)
    st.dataframe(styled, use_container_width=True, height=height)


def _compute_employee_stats(schedule: object) -> pd.DataFrame:
    """Количество смен каждого типа по каждому сотруднику."""
    stats: dict[str, dict[str, int]] = {}
    _zero: dict[str, int] = {
        "Утро": 0, "Вечер": 0, "Ночь": 0,
        "Рабочий": 0, "Выходных": 0, "Отпуск": 0,
    }

    for d in schedule.days:
        for nm in d.morning:
            stats.setdefault(nm, dict(_zero))["Утро"] += 1
        for nm in d.evening:
            stats.setdefault(nm, dict(_zero))["Вечер"] += 1
        for nm in d.night:
            stats.setdefault(nm, dict(_zero))["Ночь"] += 1
        for nm in d.workday:
            stats.setdefault(nm, dict(_zero))["Рабочий"] += 1
        for nm in d.day_off:
            stats.setdefault(nm, dict(_zero))["Выходных"] += 1
        for nm in d.vacation:
            stats.setdefault(nm, dict(_zero))["Отпуск"] += 1

    if not stats:
        return pd.DataFrame()

    result = pd.DataFrame(stats).T.fillna(0).astype(int)
    result["Всего смен"] = result["Утро"] + result["Вечер"] + result["Ночь"]
    return result


def _render_load_dashboard(schedule: object, employees_df: pd.DataFrame) -> None:
    """Дашборд нагрузки по сотрудникам."""
    stats_df = _compute_employee_stats(schedule)
    if stats_df.empty:
        st.info("Нет данных для отображения.")
        return

    workload_map = {
        str(r["Имя"]).strip(): int(r.get("Загрузка%") or 100)
        for _, r in employees_df.iterrows()
        if str(r["Имя"]).strip()
    }
    prod_days = int(
        schedule.metadata.get("production_working_days", 0)
    )

    display_cols = [
        c for c in ["Утро", "Вечер", "Ночь", "Рабочий", "Всего смен", "Выходных", "Отпуск"]
        if c in stats_df.columns
    ]
    show_df = stats_df[display_cols].copy()
    show_df.insert(0, "Загр.%", show_df.index.map(lambda n: workload_map.get(n, 100)))
    show_df["Норма дн."] = (show_df["Загр.%"] * prod_days / 100).round(0).astype(int)
    show_df["Факт дн."]  = show_df.get("Всего смен", 0) + show_df.get("Рабочий", 0)
    show_df["Δ"]         = show_df["Факт дн."] - show_df["Норма дн."]

    def _delta_style(val: object) -> str:
        try:
            v = int(val)
        except (ValueError, TypeError):
            return ""
        if v > 1:
            return "color: #C0392B; font-weight: bold;"
        if v < -1:
            return "color: #2471A3; font-weight: bold;"
        return ""

    styled = show_df.style.map(_delta_style, subset=["Δ"])
    try:
        import matplotlib  # noqa: F401
        styled = styled.background_gradient(subset=["Всего смен"], cmap="Blues")
    except ImportError:
        pass
    st.dataframe(styled, use_container_width=True)

    chart_cols = [c for c in ["Утро", "Вечер", "Ночь"] if c in stats_df.columns]
    if chart_cols:
        st.markdown("**Структура дежурных смен**")
        st.bar_chart(stats_df[chart_cols], use_container_width=True)


st.set_page_config(page_title="График дежурств", page_icon="📅", layout="wide")
_init_state()

st.title("📅 График дежурств")

with st.sidebar:
    st.header("⚙️ Конфигурация")

    uploaded = st.file_uploader(
        "Загрузить конфиг (.yaml)",
        type=["yaml", "yml"],
        help="Файл конфигурации, ранее сохранённый через кнопку «Скачать конфиг».",
    )
    if uploaded is not None:
        raw = uploaded.read().decode("utf-8")
        df_loaded, pins_loaded, co_loaded, m, y, s, emp_dates_loaded, err = _yaml_to_df(
            raw, st.session_state["cfg_year"]
        )
        if err:
            st.error(err)
        else:
            st.session_state["employees_df"]    = df_loaded
            st.session_state["pins_df"]         = pins_loaded
            st.session_state["carry_over"]      = co_loaded
            st.session_state["cfg_month"]       = m
            st.session_state["cfg_year"]        = y
            st.session_state["cfg_seed"]        = s
            st.session_state["employee_dates"]  = emp_dates_loaded
            st.session_state["_df_for_download"]   = df_loaded
            st.session_state["_pins_for_download"] = pins_loaded
            _bump_table()
            msg = f"Загружен конфиг: {len(df_loaded)} сотрудников"
            if co_loaded:
                msg += f", перенос состояния для {len(co_loaded)} сотрудников"
            st.success(msg)
            st.rerun()

    st.divider()
    st.caption("Сохранить текущую конфигурацию:")

    _dl_df   = st.session_state["_df_for_download"]
    _dl_pins = st.session_state["_pins_for_download"]
    _cfg_month = st.session_state.get("cfg_month", date.today().month)
    _cfg_year  = st.session_state.get("cfg_year",  date.today().year)
    _cfg_seed  = st.session_state.get("cfg_seed",  42)

    yaml_str = _df_to_yaml(
        _dl_df, _cfg_month, _cfg_year, _cfg_seed,
        employee_dates=st.session_state["employee_dates"],
        pins_df=_dl_pins,
    )
    st.download_button(
        label="⬇️ Скачать конфиг (.yaml)",
        data=yaml_str.encode("utf-8"),
        file_name=f"config_{_cfg_year}_{_cfg_month:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
    )

col_m, col_y, _ = st.columns([2, 1, 6])
with col_m:
    month: int = st.selectbox(
        "Месяц",
        range(1, 13),
        index=st.session_state["cfg_month"] - 1,
        format_func=lambda m: MONTHS_RU[m - 1],
        key="cfg_month",
    )
with col_y:
    year: int = st.number_input(
        "Год", min_value=2024, max_value=2030,
        value=st.session_state["cfg_year"], step=1,
        key="cfg_year",
    )

st.divider()

_setup_tab1, _setup_tab2, _setup_tab3 = st.tabs(
    ["1️⃣ Состав", "2️⃣ Ограничения", "3️⃣ Пины"]
)

with _setup_tab1:
    st.subheader("Сотрудники")
    st.caption(
        "Добавляйте строки кнопкой **+** снизу. "
        "Удалить строку — галочка слева + **Delete**."
    )

    _gopt_key = f"_gopt_{st.session_state['table_version']}"
    if _gopt_key not in st.session_state:
        st.session_state[_gopt_key] = [""] + sorted({
            str(r["Имя"]).strip()
            for _, r in st.session_state["employees_df"].iterrows()
            if str(r["Имя"]).strip()
        })
    _group_options: list[str] = st.session_state[_gopt_key]

    _sort_cols = st.columns([3, 1, 1])
    _sort_by = _sort_cols[0].selectbox(
        "Сортировать по столбцу",
        options=["—", "Имя", "Город", "График", "Дежурный", "Загрузка%"],
        key="sort_by_col",
        label_visibility="collapsed",
    )
    _sort_asc = _sort_cols[1].radio(
        "Направление", ["↑ А→Я", "↓ Я→А"], key="sort_dir", horizontal=False,
        label_visibility="collapsed",
    ) == "↑ А→Я"
    if _sort_cols[2].button("Сортировать", use_container_width=True, key="sort_btn") and _sort_by != "—":
        _cur_df = st.session_state.get("_df_for_download", st.session_state["employees_df"])
        st.session_state["employees_df"] = _cur_df.sort_values(
            _sort_by, ascending=_sort_asc
        ).reset_index(drop=True)
        _bump_table()
        st.rerun()

    _table_key = f"{_TABLE_KEY_PREFIX}_{st.session_state['table_version']}"
    _base_df = st.session_state["employees_df"]
    _display_df = _base_df.copy()
    _display_df.insert(0, "№", range(1, len(_display_df) + 1))
    _edited_raw: pd.DataFrame = st.data_editor(
        _display_df,
        column_config={
            "№":               st.column_config.NumberColumn("№"),
            "Имя":             st.column_config.TextColumn("Имя"),
            "Город":           st.column_config.SelectboxColumn(
                                   "Город", options=["Москва", "Хабаровск"],
                               ),
            "График":          st.column_config.SelectboxColumn(
                                   "График", options=["Гибкий", "5/2"],
                               ),
            "Дежурный":        st.column_config.CheckboxColumn(
                                   "Деж.",
                                   help="Участвует в назначении дежурных смен",
                               ),
            "Всегда на деж.":  st.column_config.CheckboxColumn(
                                   "Всегда",
                                   help="Назначается на дежурство каждый доступный рабочий день. "
                                        "Требует: Деж.=✓, Город=Москва, указан тип смены (Утро▲ или Вечер▲).",
                               ),
            "Только утро":     st.column_config.CheckboxColumn(
                                   "Утро▲",
                                   help="Только утренние смены 08:00–17:00 МСК",
                               ),
            "Только вечер":    st.column_config.CheckboxColumn(
                                   "Вечер▲",
                                   help="Только вечерние смены 15:00–00:00 МСК",
                               ),
            "Предпочт. смена": st.column_config.SelectboxColumn(
                                   "Пред. смена",
                                   options=["", "Утро", "Вечер", "Ночь", "Рабочий день"],
                                   help="Предпочтительная смена (мягкий приоритет)",
                               ),
            "Загрузка%":       st.column_config.NumberColumn(
                                   "Загр.%",
                                   min_value=1, max_value=100, step=1,
                                   help="Норма нагрузки: 100 = полная ставка, 50 = полставки",
                               ),
            "Макс. утренних":  st.column_config.NumberColumn(
                                   "↑Утр",
                                   min_value=1, step=1,
                                   help="Макс. утренних смен в месяц (пусто = без ограничений)",
                               ),
            "Макс. вечерних":  st.column_config.NumberColumn(
                                   "↑Веч",
                                   min_value=1, step=1,
                                   help="Макс. вечерних смен в месяц (пусто = без ограничений)",
                               ),
            "Макс. ночных":    st.column_config.NumberColumn(
                                   "↑Ноч",
                                   min_value=1, step=1,
                                   help="Макс. ночных смен в месяц (пусто = без ограничений)",
                               ),
            "Макс. подряд":    st.column_config.NumberColumn(
                                   "↑Подряд",
                                   min_value=1, step=1,
                                   help="Макс. рабочих дней подряд (пусто = 5)",
                               ),
            "Группа":          st.column_config.SelectboxColumn(
                                   "Группа",
                                   options=_group_options,
                                   help="Сотрудников одной группы не ставят вместе на одну смену",
                               ),
        },
        column_order=[
            "№", "Имя", "Город", "График",
            "Дежурный", "Всегда на деж.", "Только утро", "Только вечер",
            "Предпочт. смена", "Загрузка%",
            "Макс. утренних", "Макс. вечерних", "Макс. ночных", "Макс. подряд",
            "Группа",
        ],
        disabled=["№"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=_table_key,
    )
    edited_df = _edited_raw.drop(columns=["№"], errors="ignore").reset_index(drop=True)
    st.session_state["_df_for_download"] = edited_df

    st.caption("Быстро добавить сотрудника с типовыми настройками:")
    _pr1, _pr2, _pr3 = st.columns(3)
    if _pr1.button("＋ Москва, дежурный", use_container_width=True, key="preset_msk"):
        _preset_row = {**_EMPTY_ROW, "Город": "Москва", "Дежурный": True}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])], ignore_index=True,
        )
        _bump_table()
        st.rerun()
    if _pr2.button("＋ Хабаровск, ночной", use_container_width=True, key="preset_khb"):
        _preset_row = {**_EMPTY_ROW, "Город": "Хабаровск", "Дежурный": True}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])], ignore_index=True,
        )
        _bump_table()
        st.rerun()
    if _pr3.button("＋ Не дежурит (5/2)", use_container_width=True, key="preset_nodty"):
        _preset_row = {**_EMPTY_ROW, "Дежурный": False, "График": "5/2"}
        st.session_state["employees_df"] = pd.concat(
            [edited_df, pd.DataFrame([_preset_row])], ignore_index=True,
        )
        _bump_table()
        st.rerun()

with _setup_tab2:
    _emp_names = [
        str(r["Имя"]).strip()
        for _, r in edited_df.iterrows()
        if str(r["Имя"]).strip()
    ]

    if not _emp_names:
        st.info("Сначала добавьте сотрудников на вкладке **1️⃣ Состав**.")
    else:
        _sel = st.selectbox("Сотрудник", _emp_names, key="date_emp_selector")
        _cfg = _get_emp_dates(_sel)

        _emp_row = edited_df[edited_df["Имя"].astype(str).str.strip() == _sel]
        if not _emp_row.empty:
            _er = _emp_row.iloc[0]
            _sc1, _sc2, _sc3, _sc4 = st.columns(4)
            _sc1.metric("Город", _er["Город"])
            _sc2.metric("График", _er["График"])
            _sc3.metric("Загрузка", f"{int(_er.get('Загрузка%') or 100)}%")
            _sc4.metric("Группа", str(_er.get("Группа", "") or "—"))
            _flags: list[str] = []
            if _er.get("Дежурный"):
                _flags.append("Дежурный")
            if _er.get("Всегда на деж.", False):
                _flags.append("Всегда на деж.")
            if _er.get("Только утро"):
                _flags.append("Только утро")
            if _er.get("Только вечер"):
                _flags.append("Только вечер")
            _flag_str = "  ·  ".join(_flags) if _flags else "—"
            _pref = str(_er.get("Предпочт. смена", "")).strip()
            _detail_parts = [f"Флаги: {_flag_str}"]
            if _pref:
                _detail_parts.append(f"Предпочт. смена: {_pref}")
            st.caption("  ·  ".join(_detail_parts))

        st.divider()

        st.markdown("**Отпуска**")
        _vac_del: list[int] = []
        for _i, (_vs, _ve) in enumerate(_cfg["vacations"]):
            _c1, _c2, _c3 = st.columns([4, 4, 1])
            with _c1:
                _new_vs = st.date_input(
                    "Начало", value=_vs, key=f"vs_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            with _c2:
                _new_ve = st.date_input(
                    "Конец",
                    value=_ve if _ve >= _new_vs else _new_vs,
                    min_value=_new_vs,
                    key=f"ve_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            _cfg["vacations"][_i] = (_new_vs, _new_ve)
            with _c3:
                if st.button("✕", key=f"vdel_{_sel}_{_i}", help="Удалить период"):
                    _vac_del.append(_i)

        for _i in reversed(_vac_del):
            _cfg["vacations"].pop(_i)
            st.rerun()

        if st.button("＋ Добавить период отпуска", key=f"vadd_{_sel}"):
            _cfg["vacations"].append((date(year, month, 1), date(year, month, 7)))
            st.rerun()

        st.divider()

        st.markdown("**Недоступные дни** (не отпуск — разовые блокировки)")
        _unavail_del: list[int] = []
        for _i, _ud in enumerate(_cfg["unavailable"]):
            _c1, _c2 = st.columns([8, 1])
            with _c1:
                _new_ud = st.date_input(
                    "Дата", value=_ud, key=f"ud_{_sel}_{_i}",
                    label_visibility="collapsed",
                )
            _cfg["unavailable"][_i] = _new_ud
            with _c2:
                if st.button("✕", key=f"udel_{_sel}_{_i}", help="Удалить дату"):
                    _unavail_del.append(_i)

        for _i in reversed(_unavail_del):
            _cfg["unavailable"].pop(_i)
            st.rerun()

        if st.button("＋ Добавить недоступный день", key=f"uadd_{_sel}"):
            _cfg["unavailable"].append(date(year, month, 1))
            st.rerun()

        st.divider()

        st.markdown("**Постоянные выходные дни недели**")
        st.caption("Сотрудник не будет назначаться в эти дни недели каждую неделю.")
        _current_days_off = _cfg.get("days_off_weekly", [])
        _current_labels = [
            _WEEKDAY_INT_TO_RU[d] for d in _current_days_off if d in _WEEKDAY_INT_TO_RU
        ]
        _new_days_labels = st.multiselect(
            "Выберите дни",
            options=_WEEKDAY_OPTIONS,
            default=_current_labels,
            key=f"days_off_{_sel}",
            label_visibility="collapsed",
        )
        _cfg["days_off_weekly"] = [_WEEKDAY_RU_TO_INT[d] for d in _new_days_labels]

    st.divider()

    with st.expander("ℹ️ Правила заполнения"):
        st.markdown("""
| Поле | Описание |
|---|---|
| **Дежурный** | Участвует в дежурных сменах (утро/вечер для Москвы, ночь для Хабаровска) |
| **Только утро** | Назначается только на утренние смены (08:00–17:00 МСК) |
| **Только вечер** | Назначается только на вечерние смены (15:00–00:00 МСК) |
| **5/2** | Не работает в субботу и воскресенье |
| **Предпочт. смена** | Мягкий приоритет при выборе смены (не гарантирует назначение) |
| **Загрузка%** | Норма нагрузки: 100 = полная ставка, 50 = полставки |
| **Макс. утр./веч./ноч.** | Лимит смен данного типа в месяц (пусто = без ограничений) |
| **Макс. подряд** | Индивидуальный лимит рабочих дней подряд (пусто = 5) |
| **Группа** | Не ставить двух из одной группы на одну смену в один день |

**Минимальный состав:** 4 дежурных в Москве, 2 дежурных в Хабаровске.
        """)

with _setup_tab3:
    st.subheader("📌 Фиксированные назначения")
    st.caption("Зафиксировать конкретного сотрудника на определённый день и смену.")
    pins_edited: pd.DataFrame = st.data_editor(
        st.session_state["pins_df"],
        column_config={
            "Дата":      st.column_config.DateColumn(
                             "Дата", format="DD.MM", width="small",
                             help="Выберите дату через календарь",
                         ),
            "Сотрудник": st.column_config.TextColumn("Сотрудник", width="medium"),
            "Смена":     st.column_config.SelectboxColumn(
                             "Смена", options=_SHIFTS_RU, width="small"
                         ),
        },
        num_rows="dynamic",
        use_container_width=True,
        key="pins_table",
    )
    st.session_state["_pins_for_download"] = pins_edited

    st.divider()

    seed: int = st.number_input(
        "Seed (для воспроизводимости результата)",
        min_value=0, value=st.session_state["cfg_seed"], step=1,
        key="cfg_seed",
        help="При одинаковом seed и тех же данных всегда получается одинаковый график.",
    )

st.divider()

_val_errors, _val_warnings = _validate_config(edited_df)
for _verr in _val_errors:
    st.error(f"⛔ {_verr}")
for _vwarn in _val_warnings:
    st.warning(f"⚠️ {_vwarn}")

if st.button("⚡ Сгенерировать расписание", type="primary", use_container_width=True):
    employees, errors = _build_employees(
        edited_df, employee_dates=st.session_state["employee_dates"]
    )

    if errors:
        for err in errors:
            st.error(err)
        st.stop()
    if not employees:
        st.warning("Добавьте хотя бы одного сотрудника.")
        st.stop()

    pins: list[PinnedAssignment] = []
    for _, pin_row in pins_edited.iterrows():
        raw_date = pin_row.get("Дата")
        emp_name = str(pin_row.get("Сотрудник", "")).strip()
        shift_ru = str(pin_row.get("Смена", "")).strip()
        if not raw_date or not emp_name or not shift_ru:
            continue
        if isinstance(raw_date, date):
            pin_date = raw_date
        else:
            try:
                pin_date = datetime.strptime(
                    f"{str(raw_date).strip()}.{year}", "%d.%m.%Y"
                ).date()
            except ValueError:
                st.warning(f"Пин: неверный формат даты «{raw_date}» — пропущен.")
                continue
        shift = _RU_TO_SHIFT.get(shift_ru)
        if shift is None:
            continue
        try:
            pins.append(
                PinnedAssignment(date=pin_date, employee_name=emp_name, shift=shift)
            )
        except Exception as e:
            st.warning(f"Пин ({emp_name} / {raw_date}): {e}")

    carry_over_raw: list[dict] = st.session_state.get("carry_over", [])
    carry_over_objs: list[CarryOverState] = []
    for co in carry_over_raw:
        with contextlib.suppress(Exception):
            carry_over_objs.append(CarryOverState(**co))

    try:
        config = Config(
            month=month,
            year=year,
            seed=seed,
            employees=employees,
            pins=pins,
            carry_over=carry_over_objs,
        )
    except Exception as e:
        st.error(f"Ошибка конфигурации: {e}")
        st.stop()

    cfg_errors, cfg_warnings = collect_config_issues(config)
    if cfg_errors:
        for msg in cfg_errors:
            st.error(msg)
        for msg in cfg_warnings:
            st.warning(msg)
        st.stop()
    for msg in cfg_warnings:
        st.warning(msg)

    with st.spinner("Загружаем производственный календарь (isdayoff.ru)…"):
        try:
            holidays = fetch_holidays(year, month)
        except CalendarError as e:
            st.error(f"Не удалось загрузить производственный календарь: {e}")
            st.info("Проверьте подключение к интернету.")
            st.stop()

    with st.spinner("Генерируем расписание…"):
        try:
            schedule = generate_schedule(config, holidays)
        except ScheduleError as e:
            st.error(f"Не удалось построить расписание: {e}")
            st.stop()

    next_month = month % 12 + 1
    next_year  = year + (1 if month == 12 else 0)
    final_carry_over: list[dict] = schedule.metadata.get("carry_over", [])
    next_yaml = _df_to_yaml(
        edited_df, next_month, next_year, seed,
        employee_dates=st.session_state["employee_dates"],
        pins_df=None,
        carry_over=final_carry_over,
    )

    st.session_state["last_result"] = {
        "schedule":    schedule,
        "schedule_df": _schedule_to_edit_df(schedule),
        "meta":        dict(schedule.metadata),
        "next_month":  next_month,
        "next_year":   next_year,
        "next_yaml":   next_yaml,
        "gen_at":      datetime.now().strftime("%d.%m %H:%M"),
        "emp_count":   len(employees),
        "gen_month":   month,
        "gen_year":    year,
        "emp_df_snap": edited_df.copy(),
    }

if st.session_state.get("last_result"):
    _res      = st.session_state["last_result"]
    _schedule = _res["schedule"]
    _meta     = _res["meta"]

    st.success(
        f"✅ {MONTHS_RU[_res['gen_month'] - 1]} {_res['gen_year']} — "
        f"{len(_schedule.days)} дней, {_res['emp_count']} сотрудников, "
        f"норма {_meta.get('production_working_days', '?')} дн. "
        f"· сгенерировано в {_res['gen_at']}"
    )

    _rc1, _rc2, _rc3 = st.columns(3)
    _rc1.metric("Утренних смен", _meta.get("total_mornings", 0))
    _rc2.metric("Вечерних смен", _meta.get("total_evenings", 0))
    _rc3.metric("Ночных смен",   _meta.get("total_nights",   0))

    _tab_cal, _tab_dash, _tab_edit = st.tabs(
        ["📅 Календарь", "📊 Нагрузка", "✏️ Редактирование"]
    )

    with _tab_cal:
        _render_calendar(_schedule)

    with _tab_dash:
        _render_load_dashboard(_schedule, _res["emp_df_snap"])

    edited_schedule_df: pd.DataFrame = _res["schedule_df"]
    with _tab_edit:
        st.caption(
            "Можно вручную изменить назначения. Имена сотрудников через запятую. "
            "Нажмите **⬇️ Скачать XLS** — в файл попадёт актуальная версия таблицы."
        )
        edited_schedule_df = st.data_editor(
            _res["schedule_df"],
            column_config={
                "Дата":         st.column_config.TextColumn(
                                    "Дата", disabled=True, width="small"
                                ),
                "Утро 08–17":   st.column_config.TextColumn("Утро 08–17",   width="large"),
                "Вечер 15–00":  st.column_config.TextColumn("Вечер 15–00",  width="large"),
                "Ночь 00–08":   st.column_config.TextColumn("Ночь 00–08",   width="large"),
                "Рабочий день": st.column_config.TextColumn("Рабочий день", width="large"),
            },
            use_container_width=True,
            hide_index=True,
            key="schedule_editor",
        )

    final_schedule = _edit_df_to_schedule(edited_schedule_df, _schedule)

    _xls_hash = pd.util.hash_pandas_object(edited_schedule_df).sum()
    if st.session_state.get("_xls_hash") != _xls_hash:
        with tempfile.TemporaryDirectory() as tmpdir:
            xls_path = export_xls(final_schedule, Path(tmpdir))
            st.session_state["_xls_bytes"] = xls_path.read_bytes()
            st.session_state["_xls_hash"]  = _xls_hash
    xls_bytes: bytes = st.session_state["_xls_bytes"]

    st.download_button(
        label="⬇️ Скачать XLS",
        data=xls_bytes,
        file_name=f"schedule_{_res['gen_year']}_{_res['gen_month']:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
    st.download_button(
        label=(
            f"📅 Скачать конфиг для "
            f"{MONTHS_RU[_res['next_month'] - 1]} {_res['next_year']}"
        ),
        data=_res["next_yaml"].encode("utf-8"),
        file_name=f"config_{_res['next_year']}_{_res['next_month']:02d}.yaml",
        mime="text/yaml",
        use_container_width=True,
        help="Конфиг содержит состояния сотрудников на конец этого месяца.",
    )
