from __future__ import annotations

import os
import sys
from datetime import date
from html import escape
from io import BytesIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weasyprint.urls import URLFetcher

if sys.platform == "darwin":
    for _brew_lib in ("/opt/homebrew/lib", "/usr/local/lib"):
        if os.path.isdir(_brew_lib):
            _existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
            if _brew_lib not in _existing:
                os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = (
                    f"{_brew_lib}:{_existing}" if _existing else _brew_lib
                )
            break

from duty_schedule.constants import MONTHS_RU, SHIFT_COLORS_CELL, SHIFT_COLORS_HEADER
from duty_schedule.models import City, Employee, Schedule, ScheduleType
from duty_schedule.stats import (
    EmployeeStats,
    build_assignments,
    compute_stats,
)

SHIFT_LABELS = {
    "morning": "У",
    "evening": "В",
    "night": "Н",
    "workday": "Р",
    "day_off": "–",
    "vacation": "О",
    "sick_leave": "Б",
}

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _hex_to_css(hex_color: str) -> str:
    return f"#{hex_color}"


def _darken(hex_color: str, factor: float = 0.88) -> str:
    r = int(int(hex_color[0:2], 16) * factor)
    g = int(int(hex_color[2:4], 16) * factor)
    b = int(int(hex_color[4:6], 16) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


def _build_css(page_size: str) -> str:
    return f"""
@page {{
    size: {page_size} landscape;
    margin: 8mm;
}}
body {{
    font-family: DejaVu Sans, Arial, Helvetica, sans-serif;
    font-size: 7pt;
    margin: 0;
    padding: 0;
}}
h1 {{
    font-size: 11pt;
    text-align: center;
    margin: 0 0 4mm 0;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    table-layout: fixed;
}}
th, td {{
    border: 0.5pt solid #999;
    text-align: center;
    padding: 1pt 2pt;
    vertical-align: middle;
    overflow: hidden;
    white-space: nowrap;
}}
th {{
    background: #404040;
    color: #fff;
    font-weight: bold;
    font-size: 6.5pt;
}}
th.name-col {{
    text-align: left;
    width: 70px;
}}
th.city-col {{
    width: 30px;
}}
th.day-col {{
    width: auto;
}}
th.total-col {{
    width: 28px;
}}
td.name-cell {{
    text-align: left;
    font-weight: bold;
    background: #d9d9d9;
}}
td.city-cell {{
    font-size: 6pt;
}}
td.weekend-header {{
    background: #f2f2f2;
    color: #000;
    font-weight: bold;
}}
td.total-cell {{
    background: #d9d9d9;
    font-weight: bold;
}}
.stats-table {{
    margin-top: 4mm;
}}
.stats-table th {{
    font-size: 6pt;
}}
.stats-table td {{
    font-size: 6.5pt;
}}
"""


def _sort_employees(employees: list[Employee]) -> list[Employee]:
    return sorted(
        employees,
        key=lambda e: (
            0 if e.city == City.MOSCOW else 1,
            0 if not e.on_duty else 1,
            0 if e.schedule_type == ScheduleType.FIVE_TWO else 1,
            e.name,
        ),
    )


def _build_schedule_html(
    schedule: Schedule,
    assignments: dict[str, dict[date, str]],
    employees: list[Employee],
    stats: list[EmployeeStats],
) -> str:
    days = schedule.days
    month_label = f"{MONTHS_RU[schedule.config.month]} {schedule.config.year}"

    header_cells = ['<th class="name-col">Сотрудник</th>', '<th class="city-col">Г.</th>']
    for day in days:
        d = day.date
        cls = "weekend-header" if day.is_holiday else "day-col"
        header_cells.append(f'<th class="{cls}">{d.day}<br>{DAYS_RU[d.weekday()]}</th>')
    header_cells.append('<th class="total-col">Дн</th>')
    header_cells.append('<th class="total-col">Ч</th>')

    rows = []
    stats_map = {s.name: s for s in stats}
    for emp in employees:
        emp_days = assignments.get(emp.name, {})
        city_label = "М" if emp.city == City.MOSCOW else "Х"
        city_bg = "#E8F5E9" if emp.city == City.MOSCOW else "#D6E4F0"

        cells = [
            f'<td class="name-cell">{escape(emp.name)}</td>',
            f'<td class="city-cell" style="background:{city_bg}">{city_label}</td>',
        ]
        work_count = 0
        for day in days:
            shift_key = emp_days.get(day.date, "day_off")
            label = SHIFT_LABELS.get(shift_key, "?")
            if shift_key == "workday" and emp.name in day.workday_hours:
                label = f"Р ({day.workday_hours[emp.name]}ч)"
            color = SHIFT_COLORS_CELL.get(shift_key, "FFFFFF")
            if day.is_holiday:
                color = _darken(color)
            cells.append(f'<td style="background:#{color}">{label}</td>')
            if shift_key not in ("day_off", "vacation", "sick_leave"):
                work_count += 1

        s = stats_map.get(emp.name)
        total_hours = s.total_hours if s else 0
        cells.append(f'<td class="total-cell">{work_count}</td>')
        cells.append(f'<td class="total-cell">{total_hours}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    schedule_table = (
        f"<h1>{month_label}</h1>"
        f"<table><thead><tr>{''.join(header_cells)}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    stats_headers = [
        "Сотрудник",
        "Г.",
        "Раб",
        "Цель ч",
        "± ч",
        "Часов",
        "Кал. ч",
        "Корр. ч",
        "Отс. ч",
        "У",
        "В",
        "Н",
        "Р",
        "Вых",
        "Отп",
        "Бол",
        "Вых.раб",
        "Празд",
        "С.раб",
        "С.отд",
        "Изол",
        "Парн",
        "Ч.надб",
    ]
    stats_header_row = "".join(f"<th>{h}</th>" for h in stats_headers)
    stats_rows = []
    for emp in employees:
        s = stats_map.get(emp.name)
        if not s:
            continue
        city_label = "М" if s.city == "Москва" else "Х"
        delta = s.hours_delta
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        stats_rows.append(
            f"<tr>"
            f'<td style="text-align:left;font-weight:bold">{escape(s.name)}</td>'
            f"<td>{city_label}</td>"
            f"<td>{s.total_working}</td>"
            f"<td>{s.target_hours}</td>"
            f"<td>{delta_str}</td>"
            f"<td>{s.total_hours}</td>"
            f"<td>{s.calendar_hours}</td>"
            f"<td>{s.adjusted_hours}</td>"
            f"<td>{s.absence_reduction_hours}</td>"
            f"<td>{s.morning}</td>"
            f"<td>{s.evening}</td>"
            f"<td>{s.night}</td>"
            f"<td>{s.workday}</td>"
            f"<td>{s.day_off}</td>"
            f"<td>{s.vacation}</td>"
            f"<td>{s.sick_leave}</td>"
            f"<td>{s.weekend_work}</td>"
            f"<td>{s.holiday_work}</td>"
            f"<td>{s.max_streak_work}</td>"
            f"<td>{s.max_streak_rest}</td>"
            f"<td>{s.isolated_off}</td>"
            f"<td>{s.paired_off}</td>"
            f"<td>{s.cost_hours:.1f}</td>"
            f"</tr>"
        )

    stats_table = (
        f'<table class="stats-table"><thead><tr>{stats_header_row}</tr></thead>'
        f"<tbody>{''.join(stats_rows)}</tbody></table>"
    )

    legend_items = [
        ("У", SHIFT_COLORS_HEADER["morning"], "Утро 08–17 МСК"),
        ("В", SHIFT_COLORS_HEADER["evening"], "Вечер 15–00 МСК"),
        ("Н", SHIFT_COLORS_HEADER["night"], "Ночь 00–08 МСК"),
        ("Р", SHIFT_COLORS_HEADER["workday"], "Рабочий день с 09 местного времени"),
        ("О", SHIFT_COLORS_HEADER["vacation"], "Отпуск"),
        ("Б", SHIFT_COLORS_HEADER.get("sick_leave", "A6A6A6"), "Больничный"),
        ("–", SHIFT_COLORS_HEADER["day_off"], "Выходной"),
    ]
    legend_parts = []
    for code, color, desc in legend_items:
        legend_parts.append(
            f'<span style="display:inline-block;width:14px;height:14px;'
            f"background:#{color};text-align:center;color:#fff;font-size:7pt;"
            f'margin-right:2px;vertical-align:middle">{code}</span>'
            f'<span style="font-size:7pt;margin-right:8px">{desc}</span>'
        )
    legend = f'<div style="margin-top:3mm">{"".join(legend_parts)}</div>'

    return schedule_table + stats_table + legend


def _safe_url_fetcher() -> URLFetcher:
    from weasyprint.urls import URLFetcher

    return URLFetcher(allowed_protocols=())


def generate_schedule_pdf(
    schedule: Schedule,
    page_size: str = "A3",
    short_days: set[date] | None = None,
) -> bytes:
    from duty_schedule.project import ensure_exportable

    schedule = ensure_exportable(schedule)
    employees = _sort_employees(schedule.config.employees)
    assignments = build_assignments(schedule)
    production_days = schedule.metadata.get("production_working_days", 21)
    stats = compute_stats(schedule, assignments, production_days, short_days=short_days)

    css = _build_css(page_size)
    body = _build_schedule_html(schedule, assignments, employees, stats)
    from duty_schedule.quality_history import quality_report

    report = quality_report(schedule)
    body += (
        f"<p>Окно качества: {escape(report['window'])}; история: {escape(report['history'])}; "
        f"источник: {escape(report['source'])}; "
        f"версия: {escape(report['source_revision_id'] or 'без ID')}; "
        f"баланс: {report['fairness']}</p>"
    )

    body += (
        "<table><tr><th>Сотрудник</th><th>Серия в месяце</th><th>Серия с границей</th></tr>"
        + "".join(
            f"<tr><td>{escape(stat.name)}</td><td>{stat.max_streak_work}</td>"
            f"<td>{stat.boundary_max_streak_work}</td></tr>"
            for stat in stats
        )
        + "</table>"
    )
    html_str = f"<!DOCTYPE html><html><head><style>{css}</style></head><body>{body}</body></html>"

    try:
        from weasyprint import HTML
    except OSError:
        raise RuntimeError("weasyprint unavailable: system libraries missing") from None

    buf = BytesIO()
    HTML(string=html_str, url_fetcher=_safe_url_fetcher()).write_pdf(buf)
    return buf.getvalue()
