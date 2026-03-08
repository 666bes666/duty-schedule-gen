from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from duty_schedule.models import Schedule
from duty_schedule.ui.mappings import (
    _CAL_SHIFT_COLORS,
    _SHIFT_PALETTE,
    _WEEKDAY_RU,
)


def _schedule_to_calendar_df(schedule: Schedule) -> pd.DataFrame:
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
        name: {col: emp_days[name].get(col, "") for col in col_order} for name in sorted(emp_days)
    }
    return pd.DataFrame(rows).T[col_order]


def _style_calendar_cell(val: str) -> str:
    color = _CAL_SHIFT_COLORS.get(str(val), "#FFFFFF")
    return f"background-color: {color}; text-align: center; font-size: 0.85em;"


def _render_calendar(schedule: Schedule) -> None:
    cal_df = _schedule_to_calendar_df(schedule)

    def _badge(code: str, label: str) -> str:
        bg = _CAL_SHIFT_COLORS[code]
        border = _SHIFT_PALETTE[code]
        return (
            f'<span style="background:{bg};border:2px solid {border};color:#333;'
            f'padding:1px 8px;border-radius:4px;font-size:0.8em;font-weight:600">'
            f"{code}</span> {label}"
        )

    items = [
        _badge("У", "утро"),
        _badge("В", "вечер"),
        _badge("Н", "ночь"),
        _badge("Р", "рабочий"),
        _badge("–", "выходной"),
        _badge("О", "отпуск"),
    ]
    st.markdown(" &nbsp;·&nbsp; ".join(items), unsafe_allow_html=True)
    height = min(600, 35 * (len(cal_df) + 2))
    styled = cal_df.style.map(_style_calendar_cell)
    st.dataframe(styled, use_container_width=True, height=height)


def _compute_employee_stats(schedule: Schedule) -> pd.DataFrame:
    stats: dict[str, dict[str, int]] = {}
    _zero: dict[str, int] = {
        "Утро": 0,
        "Вечер": 0,
        "Ночь": 0,
        "Рабочий": 0,
        "Выходных": 0,
        "Отпуск": 0,
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


def _render_load_dashboard(schedule: Schedule, employees_df: pd.DataFrame) -> None:
    stats_df = _compute_employee_stats(schedule)
    if stats_df.empty:
        st.info("Нет данных для отображения.")
        return

    workload_map = {
        str(r["Имя"]).strip(): int(r.get("Загрузка%") or 100)
        for _, r in employees_df.iterrows()
        if str(r["Имя"]).strip()
    }
    prod_days = int(schedule.metadata.get("production_working_days", 0))

    display_cols = [
        c
        for c in ["Утро", "Вечер", "Ночь", "Рабочий", "Всего смен", "Выходных", "Отпуск"]
        if c in stats_df.columns
    ]
    show_df = stats_df[display_cols].copy()
    show_df.insert(0, "Загр.%", show_df.index.map(lambda n: workload_map.get(n, 100)))
    show_df["Норма дн."] = (show_df["Загр.%"] * prod_days / 100).round(0).astype(int)
    show_df["Факт дн."] = show_df.get("Всего смен", 0) + show_df.get("Рабочий", 0)
    show_df["Δ"] = show_df["Факт дн."] - show_df["Норма дн."]

    def _delta_style(val: Any) -> str:
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
        _col_palette = {
            "Утро": _SHIFT_PALETTE["У"],
            "Вечер": _SHIFT_PALETTE["В"],
            "Ночь": _SHIFT_PALETTE["Н"],
        }
        st.bar_chart(
            stats_df[chart_cols],
            color=[_col_palette[c] for c in chart_cols],
            use_container_width=True,
        )

    cov_rows = [
        {
            "День": f"{d.date.day} {_WEEKDAY_RU[d.date.weekday()]}",
            "Работают": len(d.morning) + len(d.evening) + len(d.night) + len(d.workday),
        }
        for d in schedule.days
    ]
    if cov_rows:
        cov_df = pd.DataFrame(cov_rows).set_index("День")
        st.markdown("**Покрытие по дням**")
        st.area_chart(cov_df, use_container_width=True, color=_SHIFT_PALETTE["В"])
