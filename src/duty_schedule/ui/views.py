from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.models import Schedule
from duty_schedule.stats import EmployeeStats
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


def _render_red_flags(stats_list: list[EmployeeStats]) -> None:
    flags: list[str] = []
    for s in stats_list:
        if s.max_streak_work > 5:
            flags.append(f"**{s.name}**: серия работы {s.max_streak_work} дней подряд")
        if s.isolated_off > 2:
            flags.append(f"**{s.name}**: {s.isolated_off} изолированных выходных")
        delta = s.total_working - s.target
        if abs(delta) > 2:
            flags.append(f"**{s.name}**: отклонение от нормы {delta:+d} дн.")

    weekend_counts = [s.weekend_work for s in stats_list if s.weekend_work > 0]
    if weekend_counts and len(weekend_counts) >= 2:
        wk_min, wk_max = min(weekend_counts), max(weekend_counts)
        if wk_max - wk_min > 3:
            flags.append(f"Неравномерное распределение работы в выходные: от {wk_min} до {wk_max}")

    if flags:
        st.warning("\n".join([f"- {f}" for f in flags]))
    else:
        st.success("Качество расписания в норме")


def _stats_to_dataframe(stats_list: list[EmployeeStats]) -> pd.DataFrame:
    rows = []
    for s in stats_list:
        rows.append(
            {
                "Загр.%": round(s.target / max(s.target, 1) * 100) if s.target > 0 else 100,
                "Утро": s.morning,
                "Вечер": s.evening,
                "Ночь": s.night,
                "Рабочий": s.workday,
                "Всего смен": s.morning + s.evening + s.night,
                "Выходных": s.day_off,
                "Отпуск": s.vacation,
                "Часы": s.total_hours,
                "Вых.раб.": s.weekend_work,
                "Празд.раб.": s.holiday_work,
                "Макс.серия": s.max_streak_work,
                "Изол.вых.": s.isolated_off,
                "Парн.вых.": s.paired_off,
                "Норма дн.": s.target,
                "Факт дн.": s.total_working,
                "Δ": s.total_working - s.target,
            }
        )
    return pd.DataFrame(rows, index=[s.name for s in stats_list])


def _render_load_dashboard(
    schedule: Schedule,
    employees_df: pd.DataFrame,
    stats_list: list[EmployeeStats] | None = None,
) -> None:
    if stats_list is not None and len(stats_list) > 0:
        _stats = stats_list
    else:
        from duty_schedule.stats import build_assignments, compute_stats

        prod_days = int(schedule.metadata.get("production_working_days", 21))
        assignments = build_assignments(schedule)
        _stats = compute_stats(schedule, assignments, prod_days)

    if not _stats:
        st.info("Нет данных для отображения.")
        return

    workload_map = {
        str(r["Имя"]).strip(): int(r.get("Загрузка%") or 100)
        for _, r in employees_df.iterrows()
        if str(r["Имя"]).strip()
    }
    for s in _stats:
        pct = workload_map.get(s.name, 100)
        if pct != 100:
            pass

    _render_red_flags(_stats)

    show_df = _stats_to_dataframe(_stats)
    for s in _stats:
        show_df.loc[s.name, "Загр.%"] = workload_map.get(s.name, 100)

    display_cols = [
        "Загр.%",
        "Утро",
        "Вечер",
        "Ночь",
        "Рабочий",
        "Всего смен",
        "Выходных",
        "Отпуск",
        "Часы",
        "Вых.раб.",
        "Празд.раб.",
        "Макс.серия",
        "Изол.вых.",
        "Парн.вых.",
        "Норма дн.",
        "Факт дн.",
        "Δ",
    ]
    table_df = show_df[display_cols]

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

    def _streak_style(val: Any) -> str:
        try:
            v = int(val)
        except (ValueError, TypeError):
            return ""
        if v > 5:
            return "color: #C0392B; font-weight: bold;"
        return ""

    def _isolated_style(val: Any) -> str:
        try:
            v = int(val)
        except (ValueError, TypeError):
            return ""
        if v > 0:
            return "background-color: #FFF3CD;"
        return ""

    styled = (
        table_df.style.map(_delta_style, subset=["Δ"])
        .map(_streak_style, subset=["Макс.серия"])
        .map(_isolated_style, subset=["Изол.вых."])
    )
    try:
        import matplotlib  # noqa: F401

        styled = styled.background_gradient(subset=["Всего смен"], cmap="Blues")
    except ImportError:
        pass
    st.dataframe(styled, use_container_width=True)

    shift_df = pd.DataFrame(
        {
            "Утро": [s.morning for s in _stats],
            "Вечер": [s.evening for s in _stats],
            "Ночь": [s.night for s in _stats],
        },
        index=[s.name for s in _stats],
    )
    if shift_df.sum().sum() > 0:
        st.markdown("**Структура дежурных смен**")
        _col_palette = {
            "Утро": _SHIFT_PALETTE["У"],
            "Вечер": _SHIFT_PALETTE["В"],
            "Ночь": _SHIFT_PALETTE["Н"],
        }
        st.bar_chart(
            shift_df,
            color=[_col_palette[c] for c in ["Утро", "Вечер", "Ночь"]],
            use_container_width=True,
        )

    hours_df = pd.DataFrame(
        {"Часы": [s.total_hours for s in _stats], "Норма": [s.target * 8 for s in _stats]},
        index=[s.name for s in _stats],
    )
    st.markdown("**Часы по сотрудникам**")
    st.bar_chart(hours_df, use_container_width=True, horizontal=True)

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


def render_employee_ics_downloads(schedule: Schedule) -> None:
    year = schedule.config.year
    month = schedule.config.month
    cache_key = f"ics_cache_{year}_{month}_{id(schedule)}"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = {}

    employees = sorted(schedule.config.employees, key=lambda e: e.name)

    with st.expander("Скачать календарь для сотрудника"):
        cols = st.columns(4)
        for i, emp in enumerate(employees):
            cache = st.session_state[cache_key]
            if emp.name not in cache:
                cache[emp.name] = generate_employee_ics_bytes(schedule, emp.name)
            cols[i % 4].download_button(
                label=emp.name,
                data=cache[emp.name],
                file_name=f"{emp.name}_{year}_{month:02d}.ics",
                mime="text/calendar",
                key=f"ics_dl_{emp.name}_{year}_{month}",
            )
