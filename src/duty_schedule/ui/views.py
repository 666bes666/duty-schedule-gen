from __future__ import annotations

from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.models import City, Schedule, ScheduleType
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

    _city_order = {City.MOSCOW: 0, City.KHABAROVSK: 1}
    _sched_order = {ScheduleType.FIVE_TWO: 0, ScheduleType.FLEXIBLE: 1}
    emp_by_name = {e.name: e for e in schedule.config.employees}

    def _sort_key(name: str) -> tuple[int, int, int, str]:
        e = emp_by_name.get(name)
        if e is None:
            return (99, 99, 99, name)
        return (
            _city_order.get(e.city, 99),
            int(not e.on_duty),
            _sched_order.get(e.schedule_type, 99),
            name,
        )

    rows = {
        name: {col: emp_days[name].get(col, "") for col in col_order}
        for name in sorted(emp_days, key=_sort_key)
    }
    return pd.DataFrame(rows).T[col_order]


def _style_calendar_cell(val: str) -> str:
    color = _CAL_SHIFT_COLORS.get(str(val), "#FFFFFF")
    return f"background-color: {color}; color: #1a1a1a; text-align: center; font-size: 0.85em;"


def _render_calendar(schedule: Schedule) -> None:
    cal_df = _schedule_to_calendar_df(schedule)

    def _badge(code: str, label: str) -> str:
        bg = _CAL_SHIFT_COLORS.get(code, "#FFFFFF")
        border = _SHIFT_PALETTE.get(code, "#999999")
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


def _render_balance_metrics(stats_list: list[EmployeeStats]) -> None:
    deltas = np.array([s.total_working - s.target for s in stats_list], dtype=float)
    weekends = np.array([s.weekend_work for s in stats_list], dtype=float)
    nights = np.array([s.night for s in stats_list if s.night > 0 or s.morning > 0], dtype=float)

    c1, c2, c3 = st.columns(3)
    c1.metric("Разброс нагрузки (σ)", f"{np.std(deltas):.2f}")
    c2.metric("Разброс выходных (σ)", f"{np.std(weekends):.2f}")
    if len(nights) >= 2:
        c3.metric("Разброс ночных (σ)", f"{np.std(nights):.2f}")
    else:
        c3.metric("Разброс ночных (σ)", "—")


def _render_shift_structure_chart(stats_list: list[EmployeeStats]) -> None:
    rows = []
    for s in stats_list:
        for shift, count in [("Утро", s.morning), ("Вечер", s.evening), ("Ночь", s.night)]:
            if count > 0:
                rows.append({"Сотрудник": s.name, "Смена": shift, "Кол-во": count})
    if not rows:
        return

    st.subheader("Структура дежурных смен")
    df = pd.DataFrame(rows)

    show_pct = st.toggle("Показать долю (%)", value=False, key="shift_struct_toggle")

    _col_palette = alt.Scale(
        domain=["Утро", "Вечер", "Ночь"],
        range=[_SHIFT_PALETTE["У"], _SHIFT_PALETTE["В"], _SHIFT_PALETTE["Н"]],
    )

    sort_order = [s.name for s in stats_list]

    if show_pct:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                y=alt.Y("Сотрудник:N", sort=sort_order, title=None),
                x=alt.X("Кол-во:Q", stack="normalize", title="Доля", axis=alt.Axis(format="%")),
                color=alt.Color("Смена:N", scale=_col_palette, title="Смена"),
                tooltip=["Сотрудник", "Смена", "Кол-во"],
            )
        )
    else:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                y=alt.Y("Сотрудник:N", sort=sort_order, title=None),
                x=alt.X("Кол-во:Q", stack="zero", title="Смен"),
                color=alt.Color("Смена:N", scale=_col_palette, title="Смена"),
                tooltip=["Сотрудник", "Смена", "Кол-во"],
            )
        )

    text = chart.mark_text(dx=0, color="white", fontSize=11, fontWeight="bold").encode(
        text="Кол-во:Q",
    )

    st.altair_chart(chart + text, use_container_width=True)


def _render_norm_vs_fact_chart(stats_list: list[EmployeeStats]) -> None:
    rows = []
    for s in stats_list:
        rows.append({"Сотрудник": s.name, "Тип": "Норма", "Дней": s.target})
        rows.append({"Сотрудник": s.name, "Тип": "Факт", "Дней": s.total_working})

    if not rows:
        return

    st.subheader("Норма vs Факт")
    df = pd.DataFrame(rows)

    sort_order = [s.name for s in sorted(stats_list, key=lambda x: x.total_working - x.target)]

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("Сотрудник:N", sort=sort_order, title=None),
            x=alt.X("Дней:Q", title="Рабочих дней"),
            color=alt.Color(
                "Тип:N",
                scale=alt.Scale(domain=["Норма", "Факт"], range=["#90A4AE", "#009688"]),
                title="Тип",
            ),
            yOffset="Тип:N",
            tooltip=["Сотрудник", "Тип", "Дней"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def _render_coverage_chart(schedule: Schedule) -> None:
    rows = []
    for d in schedule.days:
        day_label = f"{d.date.day} {_WEEKDAY_RU[d.date.weekday()]}"
        is_weekend = d.date.weekday() >= 5
        for shift, names in [
            ("Утро", d.morning),
            ("Вечер", d.evening),
            ("Ночь", d.night),
            ("Рабочий", d.workday),
        ]:
            rows.append(
                {
                    "День": day_label,
                    "Дата": d.date.isoformat(),
                    "Смена": shift,
                    "Кол-во": len(names),
                    "Выходной": is_weekend or d.is_holiday,
                }
            )

    if not rows:
        return

    st.subheader("Покрытие по дням")
    df = pd.DataFrame(rows)

    _palette = alt.Scale(
        domain=["Утро", "Вечер", "Ночь", "Рабочий"],
        range=[
            _SHIFT_PALETTE["У"],
            _SHIFT_PALETTE["В"],
            _SHIFT_PALETTE["Н"],
            _SHIFT_PALETTE["Р"],
        ],
    )

    sort_order = df["День"].unique().tolist()

    weekend_df = df[df["Выходной"]].groupby("День", sort=False).first().reset_index()
    weekend_bg = (
        alt.Chart(weekend_df)
        .mark_bar(color="#90A4AE", opacity=0.12)
        .encode(
            x=alt.X("День:N", sort=sort_order),
            y=alt.value(0),
            y2=alt.value(300),
        )
    )

    bars = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("День:N", sort=sort_order, title=None),
            y=alt.Y("Кол-во:Q", stack="zero", title="Человек"),
            color=alt.Color("Смена:N", scale=_palette, title="Смена"),
            tooltip=["День", "Смена", "Кол-во"],
        )
    )

    rule = (
        alt.Chart(pd.DataFrame({"y": [3]}))
        .mark_rule(strokeDash=[6, 4], color="#E53935", strokeWidth=2)
        .encode(y="y:Q")
    )

    st.altair_chart(weekend_bg + bars + rule, use_container_width=True)


def _render_weekend_holiday_chart(stats_list: list[EmployeeStats]) -> None:
    rows = []
    for s in stats_list:
        if s.weekend_work > 0:
            rows.append({"Сотрудник": s.name, "Тип": "Выходные", "Дней": s.weekend_work})
        if s.holiday_work > 0:
            rows.append({"Сотрудник": s.name, "Тип": "Праздники", "Дней": s.holiday_work})

    if not rows:
        return

    st.subheader("Нагрузка в выходные и праздники")
    df = pd.DataFrame(rows)

    sort_order = [s.name for s in sorted(stats_list, key=lambda x: x.weekend_work + x.holiday_work)]

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            y=alt.Y("Сотрудник:N", sort=sort_order, title=None),
            x=alt.X("Дней:Q", stack="zero", title="Дней"),
            color=alt.Color(
                "Тип:N",
                scale=alt.Scale(domain=["Выходные", "Праздники"], range=["#FFC107", "#E53935"]),
                title="Тип",
            ),
            tooltip=["Сотрудник", "Тип", "Дней"],
        )
    )

    st.altair_chart(chart, use_container_width=True)


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
            return "background-color: #F8D7DA; color: #842029; font-weight: bold;"
        if v < -1:
            return "background-color: #CFE2FF; color: #084298; font-weight: bold;"
        return ""

    def _streak_style(val: Any) -> str:
        try:
            v = int(val)
        except (ValueError, TypeError):
            return ""
        if v > 5:
            return "background-color: #F8D7DA; color: #842029; font-weight: bold;"
        return ""

    def _isolated_style(val: Any) -> str:
        try:
            v = int(val)
        except (ValueError, TypeError):
            return ""
        if v > 0:
            return "background-color: #FFF3CD; color: #664D03; font-weight: bold;"
        return ""

    styled = (
        table_df.style.map(_delta_style, subset=["Δ"])
        .map(_streak_style, subset=["Макс.серия"])
        .map(_isolated_style, subset=["Изол.вых."])
    )
    st.dataframe(styled, use_container_width=True)

    _render_balance_metrics(_stats)
    _render_shift_structure_chart(_stats)
    _render_norm_vs_fact_chart(_stats)
    _render_coverage_chart(schedule)
    _render_weekend_holiday_chart(_stats)


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
