"""Экспорт расписания в формат Excel (.xlsx)."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from duty_schedule.models import DaySchedule, Schedule

# Цветовая схема по ТЗ
COLORS = {
    "morning": "00B050",  # зелёный
    "evening": "003366",  # тёмно-синий
    "night": "00B0F0",  # бирюзовый
    "workday": "0070C0",  # ярко-синий
    "day_off": "FF6600",  # оранжевый
    "header": "404040",  # тёмно-серый
    "date": "E0E0E0",  # светло-серый
    "vacation": "CC99FF",  # сиреневый
}

# Белый шрифт на тёмном фоне
DARK_BG = {"evening", "header"}


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(bold: bool = False, white: bool = False) -> Font:
    color = "FFFFFF" if white else "000000"
    return Font(bold=bold, color=color, name="Calibri", size=11)


def _align_wrap() -> Alignment:
    return Alignment(wrap_text=True, vertical="top", horizontal="center")


HEADERS = [
    "Дата",
    "Утро\n08:00–17:00",
    "Вечер\n15:00–00:00",
    "Ночь\n00:00–08:00",
    "Рабочий\nдень",
    "Выходной",
]

SHIFT_COLS = ["morning", "evening", "night", "workday", "day_off"]


def export_xls(schedule: Schedule, output_dir: Path) -> Path:
    """
    Сгенерировать .xlsx файл с цветовым кодированием смен.

    Returns:
        Путь к созданному файлу.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"schedule_{schedule.config.year}_{schedule.config.month:02d}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "График дежурств"

    # ── Заголовок (строка 1) ────────────────────────────────────────────────
    ws.row_dimensions[1].height = 40
    for col_idx, header in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = _fill(COLORS["header"])
        cell.font = _font(bold=True, white=True)
        cell.alignment = _align_wrap()

    # ── Данные (строки 2+) ──────────────────────────────────────────────────
    for row_idx, day in enumerate(schedule.days, start=2):
        ws.row_dimensions[row_idx].height = _row_height(day)

        # Столбец 1: Дата
        date_cell = ws.cell(
            row=row_idx,
            column=1,
            value=_format_date(day),
        )
        date_cell.fill = _fill(COLORS["date"])
        date_cell.font = _font(bold=day.is_holiday)
        date_cell.alignment = _align_wrap()

        # Столбцы 2–6: Смены
        for col_idx, shift_key in enumerate(SHIFT_COLS, start=2):
            names = getattr(day, shift_key, [])
            # Добавляем отпускников в выходной столбец
            if shift_key == "day_off":
                names = names + day.vacation
            value = "\n".join(names) if names else ""
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            color_key = shift_key
            if shift_key == "day_off" and day.vacation and not getattr(day, shift_key):
                color_key = "vacation"
            cell.fill = _fill(COLORS.get(color_key, "FFFFFF"))
            cell.font = _font(white=color_key in DARK_BG)
            cell.alignment = _align_wrap()

    # ── Ширина столбцов ────────────────────────────────────────────────────
    col_widths = [14, 22, 22, 22, 22, 22]
    for i, width in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Заморозить заголовок
    ws.freeze_panes = "A2"

    wb.save(filename)
    return filename


def _format_date(day: DaySchedule) -> str:
    DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    MONTHS_RU = [
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
    d = day.date
    dow = DAYS_RU[d.weekday()]
    marker = " 🔴" if day.is_holiday else ""
    return f"{d.day} {MONTHS_RU[d.month]}\n{dow}{marker}"


def _row_height(day: DaySchedule) -> float:
    max_names = max(
        len(day.morning),
        len(day.evening),
        len(day.night),
        len(day.workday),
        len(day.day_off) + len(day.vacation),
        1,
    )
    return max(20.0, max_names * 15.0)
