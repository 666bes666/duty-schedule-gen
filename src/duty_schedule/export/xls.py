"""Экспорт расписания в формат Excel (.xlsx)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from duty_schedule.models import City, Schedule

COLORS = {
    "morning": "FFC107",
    "evening": "3F51B5",
    "night": "673AB7",
    "workday": "009688",
    "day_off": "90A4AE",
    "vacation": "FF5722",
    "header": "404040",
    "name": "D9D9D9",
    "weekend": "F2F2F2",
    "ok": "E2EFDA",
    "warn": "FFF2CC",
    "bad": "FCE4D6",
    "over": "DDEBF7",
    "stat_header": "2F4F8F",
    "stat_section": "BDD7EE",
    "total_row": "595959",
}

WHITE_FONT_KEYS = {"evening", "header", "workday", "night", "vacation"}

SHIFT_LABELS = {
    "morning": "Утро",
    "evening": "Вечер",
    "night": "Ночь",
    "workday": "День",
    "day_off": "—",
    "vacation": "Отп",
}

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = [
    "",
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]
MONTHS_RU_SHORT = [
    "",
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
]


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(bold: bool = False, white: bool = False, size: int = 10) -> Font:
    color = "FFFFFF" if white else "000000"
    return Font(bold=bold, color=color, name="Calibri", size=size)


def _align(horizontal: str = "center") -> Alignment:
    return Alignment(wrap_text=True, vertical="center", horizontal=horizontal)


def _build_assignments(schedule: Schedule) -> dict[str, dict[date, str]]:
    """Построить индекс: имя → дата → ключ смены."""
    result: dict[str, dict[date, str]] = {}
    for day in schedule.days:
        mapping = {
            "morning": day.morning,
            "evening": day.evening,
            "night": day.night,
            "workday": day.workday,
            "day_off": day.day_off,
            "vacation": day.vacation,
        }
        for shift_key, names in mapping.items():
            for name in names:
                result.setdefault(name, {})[day.date] = shift_key
    return result


@dataclass
class EmployeeStats:
    name: str
    city: str
    total_working: int
    target: int
    morning: int
    evening: int
    night: int
    workday: int
    day_off: int
    vacation: int
    weekend_work: int
    holiday_work: int
    max_streak_work: int
    max_streak_rest: int


def _compute_stats(
    schedule: Schedule,
    assignments: dict[str, dict[date, str]],
    production_days: int,
    employees: list | None = None,
) -> list[EmployeeStats]:
    """Вычислить статистику для каждого сотрудника."""
    holiday_dates = {day.date for day in schedule.days if day.is_holiday}
    sorted_dates = sorted(day.date for day in schedule.days)
    _employees = employees if employees is not None else schedule.config.employees

    result = []
    for emp in _employees:
        emp_days = assignments.get(emp.name, {})
        city = "Москва" if emp.city == City.MOSCOW else "Хабаровск"

        morning = sum(1 for v in emp_days.values() if v == "morning")
        evening = sum(1 for v in emp_days.values() if v == "evening")
        night = sum(1 for v in emp_days.values() if v == "night")
        workday = sum(1 for v in emp_days.values() if v == "workday")
        day_off = sum(1 for v in emp_days.values() if v == "day_off")
        vacation = sum(1 for v in emp_days.values() if v == "vacation")
        total_working = morning + evening + night + workday

        working_keys = {"morning", "evening", "night", "workday"}

        weekend_work = sum(1 for d, v in emp_days.items() if d.weekday() >= 5 and v in working_keys)

        holiday_work = sum(
            1
            for d, v in emp_days.items()
            if d in holiday_dates and d.weekday() < 5 and v in working_keys
        )

        max_streak_work = _max_streak(sorted_dates, emp_days, working=True)
        max_streak_rest = _max_streak(sorted_dates, emp_days, working=False)

        result.append(
            EmployeeStats(
                name=emp.name,
                city=city,
                total_working=total_working,
                target=round(production_days * emp.workload_pct / 100),
                morning=morning,
                evening=evening,
                night=night,
                workday=workday,
                day_off=day_off,
                vacation=vacation,
                weekend_work=weekend_work,
                holiday_work=holiday_work,
                max_streak_work=max_streak_work,
                max_streak_rest=max_streak_rest,
            )
        )
    return result


def _max_streak(
    sorted_dates: list[date],
    emp_days: dict[date, str],
    working: bool,
) -> int:
    """Вычислить максимальную серию рабочих или нерабочих дней подряд."""
    working_keys = {"morning", "evening", "night", "workday"}
    max_s = cur = 0
    for d in sorted_dates:
        key = emp_days.get(d, "day_off")
        is_working = key in working_keys
        if is_working == working:
            cur += 1
            max_s = max(max_s, cur)
        else:
            cur = 0
    return max_s


def export_xls(schedule: Schedule, output_dir: Path) -> Path:
    """
    Сгенерировать .xlsx файл с тремя листами:
      1. «График дежурств» — строки=сотрудники, столбцы=даты
      2. «Статистика» — детальные показатели каждого сотрудника за месяц
      3. «Легенда» — расшифровка цветов

    Returns:
        Путь к созданному файлу.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"schedule_{schedule.config.year}_{schedule.config.month:02d}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "График дежурств"

    days = schedule.days
    employees = sorted(
        schedule.config.employees,
        key=lambda e: (0 if e.city == City.MOSCOW else 1, 0 if not e.on_duty else 1, e.name),
    )
    assignments = _build_assignments(schedule)
    production_days = schedule.metadata.get("production_working_days", 21)
    stats = _compute_stats(schedule, assignments, production_days, employees)

    _build_schedule_sheet(ws, days, employees, assignments)

    ws_stat = wb.create_sheet(title="Статистика")
    _build_stats_sheet(ws_stat, stats, schedule)

    _add_legend(wb)

    wb.save(filename)
    return filename


def _build_schedule_sheet(ws, days, employees, assignments) -> None:
    """Заполнить лист «График дежурств»."""
    total_col = len(days) + 3

    first_day = days[0].date
    month_label = f"График дежурств — {MONTHS_RU[first_day.month]} {first_day.year}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_col)
    title = ws.cell(row=1, column=1, value=month_label)
    title.fill = _fill(COLORS["header"])
    title.font = _font(bold=True, white=True, size=14)
    title.alignment = _align()
    ws.row_dimensions[1].height = 30

    ws.row_dimensions[2].height = 36

    h = ws.cell(row=2, column=1, value="Сотрудник")
    h.fill = _fill(COLORS["header"])
    h.font = _font(bold=True, white=True, size=11)
    h.alignment = _align()

    hc = ws.cell(row=2, column=2, value="Город")
    hc.fill = _fill(COLORS["header"])
    hc.font = _font(bold=True, white=True, size=9)
    hc.alignment = _align()

    for col_idx, day in enumerate(days, start=3):
        d = day.date
        label = f"{d.day}\n{DAYS_RU[d.weekday()]}"
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = _fill(COLORS["weekend"] if day.is_holiday else "FFFFFF")
        cell.font = _font(bold=day.is_holiday, size=9)
        cell.alignment = _align()

    tc = ws.cell(row=2, column=total_col, value="Итого\nдней")
    tc.fill = _fill(COLORS["header"])
    tc.font = _font(bold=True, white=True, size=9)
    tc.alignment = _align()

    for row_idx, emp in enumerate(employees, start=3):
        ws.row_dimensions[row_idx].height = 20
        nc = ws.cell(row=row_idx, column=1, value=emp.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")

        city_label = "Москва" if emp.city == City.MOSCOW else "Хабаровск"
        city_color = "E8F5E9" if emp.city == City.MOSCOW else "D6E4F0"
        cc = ws.cell(row=row_idx, column=2, value=city_label)
        cc.fill = _fill(city_color)
        cc.font = _font(size=9)
        cc.alignment = _align()

        emp_days = assignments.get(emp.name, {})
        working_total = 0
        for col_idx, day in enumerate(days, start=3):
            shift_key = emp_days.get(day.date, "day_off")
            if shift_key in ("morning", "evening", "night", "workday"):
                working_total += 1
            label = SHIFT_LABELS.get(shift_key, "?")
            color = COLORS.get(shift_key, "FFFFFF")
            cell = ws.cell(row=row_idx, column=col_idx, value=label)
            cell.fill = _fill(color)
            cell.font = _font(white=shift_key in WHITE_FONT_KEYS, size=9)
            cell.alignment = _align()

        itogo = ws.cell(row=row_idx, column=total_col, value=working_total)
        itogo.fill = _fill(COLORS["name"])
        itogo.font = _font(bold=True, size=10)
        itogo.alignment = _align()

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 12
    for col_idx in range(3, len(days) + 3):
        ws.column_dimensions[get_column_letter(col_idx)].width = 5.5
    ws.column_dimensions[get_column_letter(total_col)].width = 8
    ws.freeze_panes = "C3"


def _build_stats_sheet(ws, stats: list[EmployeeStats], schedule: Schedule) -> None:
    """
    Заполнить лист «Статистика».

    Метрики, которые важны дежурному:
    ┌─────────────────────────────────────────────────────────────────┐
    │  Сотрудник │ Город │ Рабочих │ Норма │ +/- │ % нормы           │
    │  Утро │ Вечер │ Ночь │ РД │ Выходных │ Отпуск              │
    │  В праздники │ Макс. серия работы │ Макс. серия отдыха    │
    │  Любимая смена                                             │
    └─────────────────────────────────────────────────────────────────┘
    """
    month = schedule.config.month
    year = schedule.config.year
    title = f"Статистика дежурств — {MONTHS_RU[month]} {year}"

    ws.merge_cells("A1:N1")
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.fill = _fill(COLORS["stat_header"])
    title_cell.font = _font(bold=True, white=True, size=14)
    title_cell.alignment = _align()
    ws.row_dimensions[1].height = 30

    groups = [
        (1, 1, ""),
        (2, 2, ""),
        (3, 4, "Норма"),
        (5, 8, "Смены"),
        (9, 12, "Отдых"),
        (13, 14, "Нагрузка"),
    ]
    for start, end, label in groups:
        if label:
            ws.merge_cells(start_row=2, start_column=start, end_row=2, end_column=end)
        cell = ws.cell(row=2, column=start, value=label)
        cell.fill = _fill(COLORS["stat_section"])
        cell.font = _font(bold=True, size=9)
        cell.alignment = _align()
    ws.row_dimensions[2].height = 16

    headers = [
        "Сотрудник",
        "Город",
        "Рабочих\nдней",
        "Норма",
        "Утро",
        "Вечер",
        "Ночь",
        "День",
        "Выходных",
        "Отпуск\n(дней)",
        "Работал в\nвыходные",
        "Работал в\nпраздники",
        "Макс. серия\nработы",
        "Макс. серия\nотдыха",
    ]
    ws.row_dimensions[3].height = 32
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx, value=h)
        cell.fill = _fill(COLORS["header"])
        cell.font = _font(bold=True, white=True, size=9)
        cell.alignment = _align()

    totals = {
        "total": 0,
        "morning": 0,
        "evening": 0,
        "night": 0,
        "workday": 0,
        "day_off": 0,
        "vacation": 0,
        "weekend_work": 0,
        "holiday_work": 0,
    }

    for row_idx, st in enumerate(stats, start=4):
        ws.row_dimensions[row_idx].height = 20

        nc = ws.cell(row=row_idx, column=1, value=st.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")

        city_color = "D6E4F0" if st.city == "Хабаровск" else "E8F5E9"
        cc = ws.cell(row=row_idx, column=2, value=st.city)
        cc.fill = _fill(city_color)
        cc.font = _font(size=9)
        cc.alignment = _align()

        _stat_cell(ws, row_idx, 3, st.total_working, COLORS["name"])
        _stat_cell(ws, row_idx, 4, st.target, COLORS["name"])

        _stat_cell(ws, row_idx, 5, st.morning or "—", COLORS["morning"], white=False)
        _stat_cell(ws, row_idx, 6, st.evening or "—", COLORS["evening"], white=True)
        _stat_cell(ws, row_idx, 7, st.night or "—", COLORS["night"], white=True)
        _stat_cell(ws, row_idx, 8, st.workday or "—", COLORS["workday"], white=True)

        _stat_cell(ws, row_idx, 9, st.day_off, COLORS["day_off"])
        _stat_cell(ws, row_idx, 10, st.vacation or "—", COLORS["vacation"], white=True)

        ww_color = COLORS["warn"] if st.weekend_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 11, st.weekend_work or "—", ww_color)

        hw_color = COLORS["warn"] if st.holiday_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 12, st.holiday_work or "—", hw_color)

        streak_w_color = COLORS["bad"] if st.max_streak_work >= 5 else COLORS["ok"]
        _stat_cell(ws, row_idx, 13, st.max_streak_work, streak_w_color)
        streak_r_color = COLORS["warn"] if st.max_streak_rest >= 3 else COLORS["ok"]
        _stat_cell(ws, row_idx, 14, st.max_streak_rest, streak_r_color)

        totals["total"] += st.total_working
        totals["morning"] += st.morning
        totals["evening"] += st.evening
        totals["night"] += st.night
        totals["workday"] += st.workday
        totals["day_off"] += st.day_off
        totals["vacation"] += st.vacation
        totals["weekend_work"] += st.weekend_work
        totals["holiday_work"] += st.holiday_work

    total_row = len(stats) + 4
    ws.row_dimensions[total_row].height = 22
    _stat_cell(ws, total_row, 1, "ИТОГО по команде", COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 2, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 3, totals["total"], COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 4, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 5, totals["morning"], COLORS["morning"], bold=True)
    _stat_cell(ws, total_row, 6, totals["evening"], COLORS["evening"], white=True, bold=True)
    _stat_cell(ws, total_row, 7, totals["night"], COLORS["night"], white=True, bold=True)
    _stat_cell(ws, total_row, 8, totals["workday"], COLORS["workday"], white=True, bold=True)
    _stat_cell(ws, total_row, 9, totals["day_off"], COLORS["day_off"], bold=True)
    _stat_cell(ws, total_row, 10, totals["vacation"], COLORS["vacation"], white=True, bold=True)
    _stat_cell(ws, total_row, 11, totals["weekend_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 12, totals["holiday_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 13, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 14, "", COLORS["total_row"])

    col_widths = [20, 12, 10, 8, 7, 7, 7, 7, 10, 10, 14, 14, 16, 16]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A4"


def _stat_cell(
    ws,
    row: int,
    col: int,
    value: object,
    bg: str,
    white: bool = False,
    bold: bool = False,
) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.fill = _fill(bg)
    cell.font = _font(bold=bold, white=white, size=10)
    cell.alignment = _align()


def _add_legend(wb: Workbook) -> None:
    """Добавить лист с легендой цветов."""
    ws = wb.create_sheet(title="Легенда")
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 30

    items = [
        ("Утро", "morning", "08:00–17:00 МСК"),
        ("Вечер", "evening", "15:00–00:00 МСК"),
        ("Ночь", "night", "00:00–08:00 МСК (07:00–15:00 ХБ)"),
        ("День", "workday", "Рабочий день 09:00–18:00"),
        ("Отп", "vacation", "Отпуск"),
        ("—", "day_off", "Выходной"),
    ]
    ws.cell(row=1, column=1, value="Обозн.").font = _font(bold=True, size=11)
    ws.cell(row=1, column=2, value="Описание").font = _font(bold=True, size=11)

    for i, (label, key, desc) in enumerate(items, start=2):
        c1 = ws.cell(row=i, column=1, value=label)
        c1.fill = _fill(COLORS[key])
        c1.font = _font(white=key in WHITE_FONT_KEYS, bold=True, size=10)
        c1.alignment = _align()
        c2 = ws.cell(row=i, column=2, value=desc)
        c2.font = _font(size=10)
        c2.alignment = _align(horizontal="left")
        ws.row_dimensions[i].height = 20
