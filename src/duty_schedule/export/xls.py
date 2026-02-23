"""Экспорт расписания в формат Excel (.xlsx)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from duty_schedule.models import City, Schedule

# Цветовая схема
COLORS = {
    "morning": "00B050",  # зелёный
    "evening": "003366",  # тёмно-синий
    "night": "00B0F0",  # бирюзовый
    "workday": "0070C0",  # ярко-синий
    "day_off": "FF6600",  # оранжевый
    "vacation": "CC99FF",  # сиреневый
    "header": "404040",  # тёмно-серый
    "name": "D9D9D9",  # светло-серый
    "weekend": "F2F2F2",  # выходная дата
    "ok": "E2EFDA",  # светло-зелёный (норма выполнена)
    "warn": "FFF2CC",  # жёлтый (немного недобирает)
    "bad": "FCE4D6",  # красный (значительно недобирает)
    "over": "DDEBF7",  # голубой (перевыполнение)
    "stat_header": "2F4F8F",  # тёмно-синий заголовок статистики
    "stat_section": "BDD7EE",  # раздел статистики
    "total_row": "595959",  # строка итогов
}

WHITE_FONT_KEYS = {"evening", "header", "workday", "night"}

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


# ── Утилиты стиля ────────────────────────────────────────────────────────────


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(bold: bool = False, white: bool = False, size: int = 10) -> Font:
    color = "FFFFFF" if white else "000000"
    return Font(bold=bold, color=color, name="Calibri", size=size)


def _align(horizontal: str = "center") -> Alignment:
    return Alignment(wrap_text=True, vertical="center", horizontal=horizontal)


# ── Построение индекса назначений ────────────────────────────────────────────


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


# ── Структура статистики ─────────────────────────────────────────────────────


@dataclass
class EmployeeStats:
    name: str
    city: str
    total_working: int  # всего рабочих дней
    target: int  # норма
    morning: int  # утренних смен
    evening: int  # вечерних смен
    night: int  # ночных смен
    workday: int  # рабочих дней (не дежурство)
    day_off: int  # выходных
    vacation: int  # отпуск
    weekend_work: int  # работал в субботу/воскресенье
    holiday_work: int  # работал в официальные праздники (Пн–Пт)
    max_streak_work: int  # макс. серия рабочих дней подряд
    max_streak_rest: int  # макс. серия выходных подряд

    @property
    def deviation(self) -> int:
        return self.total_working - self.target

    @property
    def pct_norm(self) -> float:
        return (self.total_working / self.target * 100) if self.target else 0.0

    @property
    def deviation_color(self) -> str:
        d = self.deviation
        if d == 0:
            return COLORS["ok"]
        if d > 0:
            return COLORS["over"]
        return COLORS["warn"] if d >= -1 else COLORS["bad"]

    @property
    def top_shift(self) -> str:
        """Самый частый тип дежурной смены."""
        counts = {
            "Утро": self.morning,
            "Вечер": self.evening,
            "Ночь": self.night,
        }
        top = max(counts, key=lambda k: counts[k])
        return top if counts[top] > 0 else "—"


def _compute_stats(
    schedule: Schedule,
    assignments: dict[str, dict[date, str]],
    production_days: int,
) -> list[EmployeeStats]:
    """Вычислить статистику для каждого сотрудника."""
    holiday_dates = {day.date for day in schedule.days if day.is_holiday}
    sorted_dates = sorted(day.date for day in schedule.days)

    result = []
    for emp in schedule.config.employees:
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

        # Работал в субботу/воскресенье
        weekend_work = sum(
            1
            for d, v in emp_days.items()
            if d.weekday() >= 5 and v in working_keys
        )

        # Работал в официальные праздники (Пн–Пт, не выходные)
        holiday_work = sum(
            1
            for d, v in emp_days.items()
            if d in holiday_dates and d.weekday() < 5 and v in working_keys
        )

        # Макс. серии
        max_streak_work = _max_streak(sorted_dates, emp_days, working=True)
        max_streak_rest = _max_streak(sorted_dates, emp_days, working=False)

        result.append(
            EmployeeStats(
                name=emp.name,
                city=city,
                total_working=total_working,
                target=production_days,
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


# ── Главный экспорт ──────────────────────────────────────────────────────────


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
    employees = schedule.config.employees
    assignments = _build_assignments(schedule)
    production_days = schedule.metadata.get("production_working_days", 21)
    stats = _compute_stats(schedule, assignments, production_days)

    # ── Лист 1: График ──────────────────────────────────────────────────────
    _build_schedule_sheet(ws, days, employees, assignments)

    # ── Лист 2: Статистика ──────────────────────────────────────────────────
    ws_stat = wb.create_sheet(title="Статистика")
    _build_stats_sheet(ws_stat, stats, schedule)

    # ── Лист 3: Легенда ─────────────────────────────────────────────────────
    _add_legend(wb)

    wb.save(filename)
    return filename


def _build_schedule_sheet(ws, days, employees, assignments) -> None:  # noqa: ANN001
    """Заполнить лист «График дежурств»."""
    total_col = len(days) + 2

    # ── Строка 1: заголовок месяца ───────────────────────────────────────────
    first_day = days[0].date
    month_label = f"График дежурств — {MONTHS_RU[first_day.month]} {first_day.year}"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_col)
    title = ws.cell(row=1, column=1, value=month_label)
    title.fill = _fill(COLORS["header"])
    title.font = _font(bold=True, white=True, size=14)
    title.alignment = _align()
    ws.row_dimensions[1].height = 30

    # ── Строка 2: заголовки дат ──────────────────────────────────────────────
    ws.row_dimensions[2].height = 36

    h = ws.cell(row=2, column=1, value="Сотрудник")
    h.fill = _fill(COLORS["header"])
    h.font = _font(bold=True, white=True, size=11)
    h.alignment = _align()

    for col_idx, day in enumerate(days, start=2):
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

    # ── Строки сотрудников (с 3-й) ───────────────────────────────────────────
    for row_idx, emp in enumerate(employees, start=3):
        ws.row_dimensions[row_idx].height = 20
        nc = ws.cell(row=row_idx, column=1, value=emp.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")

        emp_days = assignments.get(emp.name, {})
        working_total = 0
        for col_idx, day in enumerate(days, start=2):
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
    for col_idx in range(2, len(days) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 5.5
    ws.column_dimensions[get_column_letter(total_col)].width = 8
    ws.freeze_panes = "B3"


def _build_stats_sheet(ws, stats: list[EmployeeStats], schedule: Schedule) -> None:  # noqa: ANN001
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

    # ── Заголовок листа ──────────────────────────────────────────────────────
    ws.merge_cells("A1:N1")
    title_cell = ws.cell(row=1, column=1, value=title)
    title_cell.fill = _fill(COLORS["stat_header"])
    title_cell.font = _font(bold=True, white=True, size=14)
    title_cell.alignment = _align()
    ws.row_dimensions[1].height = 30

    # ── Группы заголовков (строка 2) ─────────────────────────────────────────
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

    # ── Заголовки столбцов (строка 3) ────────────────────────────────────────
    headers = [
        "Сотрудник",        # A  col 1
        "Город",            # B  col 2
        "Рабочих\nдней",    # C  col 3
        "Норма",            # D  col 4
        "Утро",             # E  col 5
        "Вечер",            # F  col 6
        "Ночь",             # G  col 7
        "День",             # H  col 8
        "Выходных",         # I  col 9
        "Отпуск\n(дней)",   # J  col 10
        "Работал в\nвыходные",   # K  col 11  ← Сб/Вс
        "Работал в\nпраздники",  # L  col 12  ← официальные, Пн–Пт
        "Макс. серия\nработы",   # M  col 13
        "Макс. серия\nотдыха",   # N  col 14
    ]
    ws.row_dimensions[3].height = 32
    for col_idx, h in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col_idx, value=h)
        cell.fill = _fill(COLORS["header"])
        cell.font = _font(bold=True, white=True, size=9)
        cell.alignment = _align()

    # ── Строки сотрудников (с 4-й) ───────────────────────────────────────────
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

        # Имя
        nc = ws.cell(row=row_idx, column=1, value=st.name)
        nc.fill = _fill(COLORS["name"])
        nc.font = _font(bold=True, size=10)
        nc.alignment = _align(horizontal="left")

        # Город
        city_color = "D6E4F0" if st.city == "Хабаровск" else "E8F5E9"
        cc = ws.cell(row=row_idx, column=2, value=st.city)
        cc.fill = _fill(city_color)
        cc.font = _font(size=9)
        cc.alignment = _align()

        # Норма
        _stat_cell(ws, row_idx, 3, st.total_working, COLORS["name"])
        _stat_cell(ws, row_idx, 4, st.target, COLORS["name"])

        # Смены
        _stat_cell(ws, row_idx, 5, st.morning or "—", COLORS["morning"], white=False)
        _stat_cell(ws, row_idx, 6, st.evening or "—", COLORS["evening"], white=True)
        _stat_cell(ws, row_idx, 7, st.night or "—", COLORS["night"])
        _stat_cell(ws, row_idx, 8, st.workday or "—", COLORS["workday"], white=True)

        # Отдых
        _stat_cell(ws, row_idx, 9, st.day_off, COLORS["day_off"])
        _stat_cell(ws, row_idx, 10, st.vacation or "—", COLORS["vacation"])

        ww_color = COLORS["warn"] if st.weekend_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 11, st.weekend_work or "—", ww_color)

        hw_color = COLORS["warn"] if st.holiday_work > 0 else COLORS["ok"]
        _stat_cell(ws, row_idx, 12, st.holiday_work or "—", hw_color)

        # Нагрузка
        streak_w_color = COLORS["bad"] if st.max_streak_work >= 5 else COLORS["ok"]
        _stat_cell(ws, row_idx, 13, st.max_streak_work, streak_w_color)
        streak_r_color = COLORS["warn"] if st.max_streak_rest >= 3 else COLORS["ok"]
        _stat_cell(ws, row_idx, 14, st.max_streak_rest, streak_r_color)

        # Накапливаем итоги
        totals["total"] += st.total_working
        totals["morning"] += st.morning
        totals["evening"] += st.evening
        totals["night"] += st.night
        totals["workday"] += st.workday
        totals["day_off"] += st.day_off
        totals["vacation"] += st.vacation
        totals["weekend_work"] += st.weekend_work
        totals["holiday_work"] += st.holiday_work

    # ── Строка итогов по команде ──────────────────────────────────────────────
    total_row = len(stats) + 4
    ws.row_dimensions[total_row].height = 22
    _stat_cell(ws, total_row, 1, "ИТОГО по команде", COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 2, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 3, totals["total"], COLORS["total_row"], white=True, bold=True)
    _stat_cell(ws, total_row, 4, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 5, totals["morning"], COLORS["morning"], bold=True)
    _stat_cell(ws, total_row, 6, totals["evening"], COLORS["evening"], white=True, bold=True)
    _stat_cell(ws, total_row, 7, totals["night"], COLORS["night"], bold=True)
    _stat_cell(ws, total_row, 8, totals["workday"], COLORS["workday"], white=True, bold=True)
    _stat_cell(ws, total_row, 9, totals["day_off"], COLORS["day_off"], bold=True)
    _stat_cell(ws, total_row, 10, totals["vacation"], COLORS["vacation"], bold=True)
    _stat_cell(ws, total_row, 11, totals["weekend_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 12, totals["holiday_work"], COLORS["total_row"], white=True)
    _stat_cell(ws, total_row, 13, "", COLORS["total_row"])
    _stat_cell(ws, total_row, 14, "", COLORS["total_row"])

    # ── Ширина столбцов ───────────────────────────────────────────────────────
    col_widths = [20, 12, 10, 8, 7, 7, 7, 7, 10, 10, 14, 14, 16, 16]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A4"


def _stat_cell(
    ws,  # noqa: ANN001
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
