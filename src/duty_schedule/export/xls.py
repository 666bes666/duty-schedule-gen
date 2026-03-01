"""Экспорт расписания в формат Excel (.xlsx)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from duty_schedule.models import City, Schedule, ScheduleType

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

CELL_COLORS = {
    "morning": "FFE082",
    "evening": "C5CAE9",
    "night": "EDE7F6",
    "workday": "B2DFDB",
    "day_off": "ECEFF1",
    "vacation": "FFCCBC",
}

WHITE_FONT_KEYS = {"evening", "header", "workday", "night", "vacation"}

THIN_SIDE = Side(style="thin", color="BFBFBF")
MEDIUM_SIDE = Side(style="medium", color="808080")
THIN_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
MONDAY_BORDER = Border(left=MEDIUM_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
SECTION_BORDER = Border(left=MEDIUM_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
SECTION_COLS = {3, 6, 10, 14}

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


def _darken(hex_color: str, factor: float = 0.88) -> str:
    r = int(int(hex_color[0:2], 16) * factor)
    g = int(int(hex_color[2:4], 16) * factor)
    b = int(int(hex_color[4:6], 16) * factor)
    return f"{r:02X}{g:02X}{b:02X}"


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
    isolated_off: int
    paired_off: int


def _count_isolated_off(emp_name: str, schedule: Schedule) -> int:
    count = 0
    days = schedule.days
    for i, day in enumerate(days):
        if emp_name not in day.day_off:
            continue
        left_ok = i == 0 or emp_name in days[i - 1].day_off or emp_name in days[i - 1].vacation
        right_ok = (
            i == len(days) - 1
            or emp_name in days[i + 1].day_off
            or emp_name in days[i + 1].vacation
        )
        if not left_ok and not right_ok:
            count += 1
    return count


def _count_paired_off(emp_name: str, schedule: Schedule) -> int:
    count = 0
    days = schedule.days
    i = 0
    while i < len(days):
        if emp_name in days[i].day_off or emp_name in days[i].vacation:
            j = i
            while j < len(days) and (emp_name in days[j].day_off or emp_name in days[j].vacation):
                j += 1
            if j - i >= 2:
                count += 1
            i = j
        else:
            i += 1
    return count


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
        isolated_off = _count_isolated_off(emp.name, schedule)
        paired_off = _count_paired_off(emp.name, schedule)

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
                isolated_off=isolated_off,
                paired_off=paired_off,
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
        key=lambda e: (
            0 if e.city == City.MOSCOW else 1,
            0 if not e.on_duty else 1,
            0 if e.schedule_type == ScheduleType.FIVE_TWO else 1,
            e.name,
        ),
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
    title.border = THIN_BORDER
    ws.row_dimensions[1].height = 30

    ws.row_dimensions[2].height = 36

    h = ws.cell(row=2, column=1, value="Сотрудник")
    h.fill = _fill(COLORS["header"])
    h.font = _font(bold=True, white=True, size=11)
    h.alignment = _align()
    h.border = THIN_BORDER

    hc = ws.cell(row=2, column=2, value="Город")
    hc.fill = _fill(COLORS["header"])
    hc.font = _font(bold=True, white=True, size=9)
    hc.alignment = _align()
    hc.border = THIN_BORDER

    for col_idx, day in enumerate(days, start=3):
        d = day.date
        label = f"{d.day}\n{DAYS_RU[d.weekday()]}"
        cell = ws.cell(row=2, column=col_idx, value=label)
        cell.fill = _fill(COLORS["weekend"] if day.is_holiday else "FFFFFF")
        cell.font = _font(bold=day.is_holiday, size=9)
        cell.alignment = _align()
        cell.border = MONDAY_BORDER if d.weekday() == 0 else THIN_BORDER

    tc = ws.cell(row=2, column=total_col, value="Итого\nдней")
    tc.fill = _fill(COLORS["header"])
    tc.font = _font(bold=True, white=True, size=9)
    tc.alignment = _align()
    tc.border = THIN_BORDER

    for row_idx, emp in enumerate(employees, start=3):
        ws.row_dimensions[row_idx].height = 20
        nc = ws.cell(row=row_idx, column=1, value=emp.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")
        nc.border = THIN_BORDER

        city_label = "Москва" if emp.city == City.MOSCOW else "Хабаровск"
        city_color = "E8F5E9" if emp.city == City.MOSCOW else "D6E4F0"
        cc = ws.cell(row=row_idx, column=2, value=city_label)
        cc.fill = _fill(city_color)
        cc.font = _font(size=9)
        cc.alignment = _align()
        cc.border = THIN_BORDER

        emp_days = assignments.get(emp.name, {})
        working_total = 0
        for col_idx, day in enumerate(days, start=3):
            shift_key = emp_days.get(day.date, "day_off")
            if shift_key in ("morning", "evening", "night", "workday"):
                working_total += 1
            label = SHIFT_LABELS.get(shift_key, "?")
            color = CELL_COLORS.get(shift_key, "FFFFFF")
            if day.is_holiday:
                color = _darken(color)
            cell = ws.cell(row=row_idx, column=col_idx, value=label)
            cell.fill = _fill(color)
            cell.font = _font(white=False, size=9)
            cell.alignment = _align()
            cell.border = MONDAY_BORDER if day.date.weekday() == 0 else THIN_BORDER

        itogo = ws.cell(row=row_idx, column=total_col, value=working_total)
        itogo.fill = _fill(COLORS["name"])
        itogo.font = _font(bold=True, size=10)
        itogo.alignment = _align()
        itogo.border = THIN_BORDER

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
    │  Сотрудник │ Город │ Рабочих │ Норма │ ±Норма │ % нормы       │
    │  Утро │ Вечер │ Ночь │ РД │ Выходных │ Отпуск              │
    │  В праздники │ Макс. серия работы │ Макс. серия отдыха    │
    │  Любимая смена                                             │
    └─────────────────────────────────────────────────────────────────┘
    """
    month = schedule.config.month
    year = schedule.config.year
    title = f"Статистика дежурств — {MONTHS_RU[month]} {year}"

    ws.merge_cells("A1:Q1")
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.fill = _fill(COLORS["stat_header"])
    title_cell.font = _font(bold=True, white=True, size=14)
    title_cell.alignment = _align()
    title_cell.border = THIN_BORDER
    ws.row_dimensions[1].height = 30

    groups = [
        (1, 1, ""),
        (2, 2, ""),
        (3, 5, "Норма"),
        (6, 9, "Смены"),
        (10, 13, "Отдых"),
        (14, 17, "Нагрузка"),
    ]
    for start, end, label in groups:
        if label:
            ws.merge_cells(start_row=2, start_column=start, end_row=2, end_column=end)
        cell = ws.cell(row=2, column=start, value=label)
        cell.fill = _fill(COLORS["stat_section"])
        cell.font = _font(bold=True, size=9)
        cell.alignment = _align()
        cell.border = SECTION_BORDER if start in SECTION_COLS else THIN_BORDER
    ws.row_dimensions[2].height = 16

    headers = [
        "Сотрудник",
        "Город",
        "Рабочих\nдней",
        "Норма",
        "±Норма",
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
        "Изол.\nвыходных",
        "Сдвоен.\nвыходных",
    ]
    ws.row_dimensions[3].height = 32
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx, value=h)
        cell.fill = _fill(COLORS["header"])
        cell.font = _font(bold=True, white=True, size=9)
        cell.alignment = _align()
        cell.border = SECTION_BORDER if col_idx in SECTION_COLS else THIN_BORDER

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
        "isolated_off": 0,
        "paired_off": 0,
    }

    for row_idx, st in enumerate(stats, start=4):
        ws.row_dimensions[row_idx].height = 20

        nc = ws.cell(row=row_idx, column=1, value=st.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")
        nc.border = THIN_BORDER

        city_color = "D6E4F0" if st.city == "Хабаровск" else "E8F5E9"
        cc = ws.cell(row=row_idx, column=2, value=st.city)
        cc.fill = _fill(city_color)
        cc.font = _font(size=9)
        cc.alignment = _align()
        cc.border = THIN_BORDER

        _stat_cell(ws, row_idx, 3, st.total_working, COLORS["name"])
        _stat_cell(ws, row_idx, 4, st.target, COLORS["name"])

        delta = st.total_working - st.target
        if delta == 0:
            delta_color = COLORS["ok"]
        elif abs(delta) == 1:
            delta_color = COLORS["warn"]
        else:
            delta_color = COLORS["bad"]
        delta_label = f"+{delta}" if delta > 0 else str(delta)
        _stat_cell(ws, row_idx, 5, delta_label, delta_color)

        _stat_cell(ws, row_idx, 6, st.morning or "—", COLORS["morning"], white=False)
        _stat_cell(ws, row_idx, 7, st.evening or "—", COLORS["evening"], white=True)
        _stat_cell(ws, row_idx, 8, st.night or "—", COLORS["night"], white=True)
        _stat_cell(ws, row_idx, 9, st.workday or "—", COLORS["workday"], white=True)

        _stat_cell(ws, row_idx, 10, st.day_off, COLORS["day_off"])
        _stat_cell(ws, row_idx, 11, st.vacation or "—", COLORS["vacation"], white=True)

        ww_color = COLORS["warn"] if st.weekend_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 12, st.weekend_work or "—", ww_color)

        hw_color = COLORS["warn"] if st.holiday_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 13, st.holiday_work or "—", hw_color)

        streak_w_color = COLORS["bad"] if st.max_streak_work >= 5 else COLORS["ok"]
        _stat_cell(ws, row_idx, 14, st.max_streak_work, streak_w_color)
        streak_r_color = COLORS["warn"] if st.max_streak_rest >= 3 else COLORS["ok"]
        _stat_cell(ws, row_idx, 15, st.max_streak_rest, streak_r_color)

        if st.isolated_off >= 2:
            iso_color = COLORS["bad"]
        elif st.isolated_off == 1:
            iso_color = COLORS["warn"]
        else:
            iso_color = COLORS["ok"]
        _stat_cell(ws, row_idx, 16, st.isolated_off, iso_color)

        if st.paired_off >= 3:
            paired_color = COLORS["ok"]
        elif st.paired_off >= 1:
            paired_color = COLORS["warn"]
        else:
            paired_color = COLORS["bad"]
        _stat_cell(ws, row_idx, 17, st.paired_off, paired_color)

        totals["total"] += st.total_working
        totals["morning"] += st.morning
        totals["evening"] += st.evening
        totals["night"] += st.night
        totals["workday"] += st.workday
        totals["day_off"] += st.day_off
        totals["vacation"] += st.vacation
        totals["weekend_work"] += st.weekend_work
        totals["holiday_work"] += st.holiday_work
        totals["isolated_off"] += st.isolated_off
        totals["paired_off"] += st.paired_off

    total_row = len(stats) + 4
    ws.row_dimensions[total_row].height = 22
    _stat_cell(ws, total_row, 1, "ИТОГО по команде", COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 2, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 3, totals["total"], COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 4, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 5, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 6, totals["morning"], COLORS["morning"], bold=True)
    _stat_cell(ws, total_row, 7, totals["evening"], COLORS["evening"], white=True, bold=True)
    _stat_cell(ws, total_row, 8, totals["night"], COLORS["night"], white=True, bold=True)
    _stat_cell(ws, total_row, 9, totals["workday"], COLORS["workday"], white=True, bold=True)
    _stat_cell(ws, total_row, 10, totals["day_off"], COLORS["day_off"], bold=True)
    _stat_cell(ws, total_row, 11, totals["vacation"], COLORS["vacation"], white=True, bold=True)
    _stat_cell(ws, total_row, 12, totals["weekend_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 13, totals["holiday_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 14, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 15, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 16, totals["isolated_off"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 17, totals["paired_off"], COLORS["total_row"], white=True)

    col_widths = [20, 12, 10, 8, 8, 7, 7, 7, 7, 10, 10, 14, 14, 16, 16, 12, 12]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A4"
    ws.auto_filter.ref = f"A3:{get_column_letter(17)}{total_row}"


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
    cell.border = SECTION_BORDER if col in SECTION_COLS else THIN_BORDER


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
    h1 = ws.cell(row=1, column=1, value="Обозн.")
    h1.font = _font(bold=True, size=11)
    h1.border = THIN_BORDER
    h2 = ws.cell(row=1, column=2, value="Описание")
    h2.font = _font(bold=True, size=11)
    h2.border = THIN_BORDER

    for i, (label, key, desc) in enumerate(items, start=2):
        c1 = ws.cell(row=i, column=1, value=label)
        c1.fill = _fill(CELL_COLORS[key])
        c1.font = _font(white=False, bold=True, size=10)
        c1.alignment = _align()
        c1.border = THIN_BORDER
        c2 = ws.cell(row=i, column=2, value=desc)
        c2.font = _font(size=10)
        c2.alignment = _align(horizontal="left")
        c2.border = THIN_BORDER
        ws.row_dimensions[i].height = 20
