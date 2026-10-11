from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from duty_schedule.calendar import CalendarError
from duty_schedule.export.ics import generate_employee_ics_bytes
from duty_schedule.models import City, Schedule, ScheduleType
from duty_schedule.stats import EmployeeStats, diff_schedules
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
            hours = d.workday_hours.get(nm)
            emp_days.setdefault(nm, {})[header] = f"Р ({hours}ч)" if hours is not None else "Р"
        for nm in d.day_off:
            emp_days.setdefault(nm, {})[header] = "–"
        for nm in d.vacation:
            emp_days.setdefault(nm, {})[header] = "О"
        for nm in d.sick_leave:
            emp_days.setdefault(nm, {})[header] = "Б"

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


def _style_calendar_cell(val: object) -> str:
    code = "Р" if str(val).startswith("Р (") else str(val)
    color = _CAL_SHIFT_COLORS.get(code, "#D9E2F3" if code == "Б" else "#FFFFFF")
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
        _badge("Б", "больничный"),
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
        delta = s.hours_delta
        if delta:
            flags.append(f"**{s.name}**: отклонение от выбранной нормы {delta:+d} ч")

    weekend_counts = [s.weekend_work for s in stats_list if s.weekend_work > 0]
    if weekend_counts and len(weekend_counts) >= 2:
        wk_min, wk_max = min(weekend_counts), max(weekend_counts)
        if wk_max - wk_min > 3:
            flags.append(f"Неравномерное распределение работы в выходные: от {wk_min} до {wk_max}")

    if flags:
        st.warning("\n".join([f"- {f}" for f in flags]))
    else:
        st.caption("По показателям качества дополнительных замечаний нет")


def _stats_to_dataframe(stats_list: list[EmployeeStats]) -> pd.DataFrame:
    rows = []
    for s in stats_list:
        rows.append(
            {
                "Утро": s.morning,
                "Вечер": s.evening,
                "Ночь": s.night,
                "Рабочий": s.workday,
                "Всего смен": s.morning + s.evening + s.night,
                "Выходных": s.day_off,
                "Отпуск": s.vacation,
                "Больничный": s.sick_leave,
                "Часы": s.total_hours,
                "Часы с надб.": s.cost_hours,
                "Вых.раб.": s.weekend_work,
                "Празд.раб.": s.holiday_work,
                "Макс.серия": s.max_streak_work,
                "Макс.серия с границей": s.boundary_max_streak_work,
                "Изол.вых.": s.isolated_off,
                "Парн.вых.": s.paired_off,
                "Календарная норма, ч": s.calendar_hours,
                "После отсутствий, ч": s.adjusted_hours,
                "Выбранная цель, ч": s.selected_hours,
                "Факт дней": s.total_working,
                "Δ ч": s.hours_delta,
            }
        )
    return pd.DataFrame(rows, index=[s.name for s in stats_list])


def _render_balance_metrics(stats_list: list[EmployeeStats], schedule: Schedule) -> None:
    from duty_schedule.api.whatif_service import compute_summary

    summary = compute_summary(stats_list, schedule)
    st.caption(
        f"Окно качества: {summary.quality_context['window']}; "
        f"история: {summary.quality_context['history']}; "
        f"источник: {summary.quality_context['source']}; "
        f"версия: {summary.quality_context['source_revision_id'] or 'без ID'}"
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Баланс дежурств", f"{summary.fairness_score:.4f}")
    c2.metric("Баланс выходных", f"{summary.weekend_balance_stddev:.4f}")
    c3.metric("Отклонение часов (σ)", f"{np.std([s.hours_delta for s in stats_list]):.2f}")


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
    for item in stats_list:
        for label, hours in (
            ("Календарная", item.calendar_hours),
            ("После отсутствий", item.adjusted_hours),
            ("Выбранная цель", item.selected_hours),
            ("Факт", item.total_hours),
        ):
            rows.append({"Сотрудник": item.name, "Тип": label, "Часы": hours})
    if not rows:
        return
    st.subheader("Норма и фактические часы")
    chart = (
        alt.Chart(pd.DataFrame(rows))
        .mark_bar()
        .encode(
            y=alt.Y("Сотрудник:N", sort=[item.name for item in stats_list], title=None),
            x=alt.X("Часы:Q", title="Рабочие часы"),
            color=alt.Color("Тип:N", title="Норма"),
            yOffset="Тип:N",
            tooltip=["Сотрудник", "Тип", "Часы"],
        )
    )
    st.altair_chart(chart, use_container_width=True)


def _render_coverage_chart(schedule: Schedule) -> None:
    rows = []
    for d in schedule.days:
        day_label = f"{d.date.day} {_WEEKDAY_RU[d.date.weekday()]}"
        is_weekend = d.is_holiday
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

    _render_red_flags(_stats)

    show_df = _stats_to_dataframe(_stats)

    display_cols = [
        "Утро",
        "Вечер",
        "Ночь",
        "Рабочий",
        "Всего смен",
        "Выходных",
        "Отпуск",
        "Больничный",
        "Часы",
        "Часы с надб.",
        "Вых.раб.",
        "Празд.раб.",
        "Макс.серия",
        "Изол.вых.",
        "Парн.вых.",
        "Календарная норма, ч",
        "После отсутствий, ч",
        "Выбранная цель, ч",
        "Факт дней",
        "Δ ч",
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
        table_df.style.map(_delta_style, subset=["Δ ч"])
        .map(_streak_style, subset=["Макс.серия"])
        .map(_isolated_style, subset=["Изол.вых."])
    )
    st.dataframe(styled, use_container_width=True)

    _render_balance_metrics(_stats, schedule)
    _render_shift_structure_chart(_stats)
    _render_norm_vs_fact_chart(_stats)
    _render_coverage_chart(schedule)
    _render_weekend_holiday_chart(_stats)


def _render_changelog(schedule: Schedule) -> None:
    changelog = schedule.metadata.get("changelog")
    entries = (
        changelog.get("entries", [])
        if isinstance(changelog, dict)
        else [asdict(entry) for entry in changelog.entries]
        if changelog
        else []
    )
    provenance = schedule.metadata.get("optimization")
    if provenance:
        st.write(
            f"Оптимизация: {provenance['status']}; изменённых ячеек: {provenance['changed_cells']}"
        )
        st.dataframe(
            pd.DataFrame(
                {
                    "Показатель (меньше лучше)": provenance["quality_labels"],
                    "До": provenance["quality_before"],
                    "После": provenance["quality_after"],
                }
            ),
            hide_index=True,
        )
        st.caption("Ограниченный поиск; глобальный оптимум не доказан.")
    else:
        st.info("log_unavailable: данные об изменениях оптимизации недоступны.")
    if not entries:
        return
    names = sorted({entry["employee"] for entry in entries})
    selected = st.selectbox("Фильтр по сотруднику", ["Все"] + names, key="changelog_filter")
    rows = [
        {
            "Этап": entry["stage"],
            "Действие": entry["action"],
            "Сотрудник": entry["employee"],
            "Дата": str(entry["day"]),
            "Детали": entry.get("detail", ""),
        }
        for entry in entries
        if selected == "Все" or entry["employee"] == selected
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Всего записей: {len(rows)}")


SHIFT_LABEL_MAP = {
    "morning": "Утро",
    "evening": "Вечер",
    "night": "Ночь",
    "workday": "Рабочий",
    "day_off": "Выходной",
    "vacation": "Отпуск",
    "sick_leave": "Больничный",
}


def _diff_workday_hours(schedule: Schedule, difference: dict[str, Any], field: str) -> int | None:
    if difference[f"{field}_shift"] != "workday":
        return None
    hours = difference.get(f"{field}_hours")
    if hours is not None:
        return int(hours)
    day = next((day for day in schedule.days if day.date.isoformat() == difference["date"]), None)
    if day is None:
        return None
    calendar = schedule.config.production_calendar
    return (calendar.hours(day.date) or 8) if calendar else 8


def _render_schedule_diff(schedule: Schedule) -> None:
    history: list[dict] = st.session_state.get("schedule_history", [])
    if len(history) < 2:
        st.info("Сравнение доступно после двух или более генераций.")
        return

    labels = [h["label"] for h in history]
    c1, c2 = st.columns(2)
    idx_a = c1.selectbox(
        "Расписание A",
        range(len(labels)),
        format_func=lambda i: labels[i],
        index=len(labels) - 2,
        key="diff_a",
    )
    idx_b = c2.selectbox(
        "Расписание B",
        range(len(labels)),
        format_func=lambda i: labels[i],
        index=len(labels) - 1,
        key="diff_b",
    )

    sched_a = history[idx_a]["schedule"]
    sched_b = history[idx_b]["schedule"]

    diffs = diff_schedules(sched_a, sched_b)
    if not diffs:
        st.success("Расписания идентичны.")
        return

    rows = []
    for d in diffs:
        row = {
            "Дата": d["date"],
            "Сотрудник": d["employee"],
            "Было": SHIFT_LABEL_MAP.get(d["old_shift"], d["old_shift"]),
            "Стало": SHIFT_LABEL_MAP.get(d["new_shift"], d["new_shift"]),
        }
        if "old_hours" in d:
            row["Было, ч"] = _diff_workday_hours(sched_a, d, "old")
            row["Стало, ч"] = _diff_workday_hours(sched_b, d, "new")
        rows.append(row)

    st.caption(f"Изменений: {len(rows)}")

    emp_filter = st.selectbox(
        "Фильтр по сотруднику",
        ["Все"] + sorted({r["Сотрудник"] for r in rows}),
        key="diff_emp_filter",
    )
    if emp_filter != "Все":
        rows = [r for r in rows if r["Сотрудник"] == emp_filter]

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_whatif_panel(schedule: Schedule, holidays: set, short_days: set) -> None:
    from duty_schedule.api.schemas import EmployeeStatsSchema, VariantPatch
    from duty_schedule.api.whatif_service import (
        apply_patch,
        compute_deltas,
        compute_summary,
        generate_scenario,
    )
    from duty_schedule.ui.components import WHATIF_PARAMETERS

    st.caption("Изменения относятся к текущему месяцу. Другой период рассчитывается диапазоном.")
    with st.expander("Доступные параметры"):
        st.write(", ".join(WHATIF_PARAMETERS))
    if "whatif_variants" not in st.session_state:
        st.session_state["whatif_variants"] = [{"name": "Вариант 1", "patch": {"seed": 99}}]
    variants: list[dict] = st.session_state["whatif_variants"]
    for index, variant in enumerate(variants):
        with st.expander(variant["name"], expanded=True):
            variant["name"] = st.text_input(
                "Название", value=variant["name"], key=f"wi_name_{index}"
            )
            raw = st.text_area(
                "Изменения JSON",
                value=json.dumps(variant["patch"], ensure_ascii=False, indent=2),
                key=f"wi_patch_{index}",
            )
            try:
                patch = VariantPatch(name=variant["name"], patch=json.loads(raw))
                if set(patch.patch) - set(WHATIF_PARAMETERS):
                    raise ValueError("Изменения содержат неизвестные параметры")
                variant["patch"] = patch.patch
                if not patch.patch:
                    st.caption("Этот вариант не изменяет параметры")
                variant.pop("error", None)
            except ValueError as exc:
                variant["error"] = str(exc)
                st.error(str(exc))
    c1, c2 = st.columns(2)
    if c1.button("+ Добавить вариант", disabled=len(variants) >= 5, key="wi_add"):
        variants.append({"name": f"Вариант {len(variants) + 1}", "patch": {"seed": 99}})
        st.rerun()
    if c2.button("Удалить последний", disabled=len(variants) <= 1, key="wi_remove"):
        variants.pop()
        st.rerun()
    if st.button("Симулировать", key="wi_run"):
        from duty_schedule.stats import build_assignments, compute_stats

        calendar = schedule.config.production_calendar
        production_days = sum(day.kind != "off" for day in calendar.days) if calendar else 0
        baseline_raw = compute_stats(
            schedule, build_assignments(schedule), production_days, short_days=short_days
        )
        baseline_stats = [EmployeeStatsSchema.model_validate(asdict(item)) for item in baseline_raw]
        baseline_summary = compute_summary(baseline_raw, schedule)
        baseline_targets = {item.name: item.target for item in baseline_stats}
        for variant in variants:
            if variant.get("error"):
                continue
            try:
                config = apply_patch(schedule.config, variant["patch"])
                stats, summary, generated = generate_scenario(config, holidays, short_days)
            except (CalendarError, ValueError) as exc:
                st.error(f"{variant['name']}: {exc}")
                continue
            st.subheader(variant["name"])
            if generated.status != "ready":
                st.warning("Вариант остаётся диагностическим")
                st.write([item.detail for item in generated.diagnostics])
            st.metric(
                "Баланс дежурств",
                f"{summary.fairness_score:.4f}",
                delta=f"{summary.fairness_score - baseline_summary.fairness_score:.4f}",
                delta_color="inverse",
            )
            differences = compute_deltas(
                baseline_stats, stats, baseline_targets, {item.name: item.target for item in stats}
            )
            rows = [
                {
                    "Сотрудник": item.name,
                    "Метрика": metric,
                    "Было": value.baseline,
                    "Стало": value.variant,
                    "Δ": value.delta,
                }
                for item in differences
                for metric, value in item.metrics.items()
                if value.delta
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def render_employee_ics_downloads(schedule: Schedule) -> None:
    year = schedule.config.year
    month = schedule.config.month
    digest = hashlib.sha256(schedule.model_dump_json().encode()).hexdigest()
    cache_key = f"ics_cache_{digest}"

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
