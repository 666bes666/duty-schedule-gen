"""Экспорт расписания в формат Excel (.xlsx)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from duty_schedule.models import Schedule, ShiftType

# Цветовая схема по ТЗ
COLORS = {
    "morning": "00B050",  # зелёный
    "evening": "003366",  # тёмно-синий
    "night": "00B0F0",  # бирюзовый
    "workday": "0070C0",  # ярко-синий
    "day_off": "FF6600",  # оранжевый
    "vacation": "CC99FF",  # сиреневый
    "header": "404040",  # тёмно-серый
    "name": "D9D9D9",  # светло-серый (столбец имён)
    "weekend": "F2F2F2",  # чуть серее белого (выходная дата)
}

# Ключи смен с белым шрифтом
WHITE_FONT_KEYS = {"evening", "header", "workday", "night"}

# Краткие обозначения смен в ячейках
SHIFT_LABELS = {
    "morning": "Утро",
    "evening": "Вечер",
    "night": "Ночь",
    "workday": "РД",
    "day_off": "—",
    "vacation": "Отп",
}

DAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def _fill(hex_color: str) -> PatternFill:
    return PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")


def _font(bold: bool = False, white: bool = False, size: int = 10) -> Font:
    color = "FFFFFF" if white else "000000"
    return Font(bold=bold, color=color, name="Calibri", size=size)


def _align(horizontal: str = "center") -> Alignment:
    return Alignment(wrap_text=True, vertical="center", horizontal=horizontal)


def _build_assignments(schedule: Schedule) -> dict[str, dict[date, str]]:
    """Построить индекс: имя сотрудника → дата → ключ смены."""
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


def export_xls(schedule: Schedule, output_dir: Path) -> Path:
    """
    Сгенерировать .xlsx файл: строки — сотрудники, столбцы — даты.

    Каждая ячейка на пересечении показывает тип смены сотрудника в этот день
    с цветовым кодированием.

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

    # ── Строка 1: заголовок с датами ────────────────────────────────────────
    ws.row_dimensions[1].height = 36

    # Ячейка A1 — «Сотрудник»
    header_cell = ws.cell(row=1, column=1, value="Сотрудник")
    header_cell.fill = _fill(COLORS["header"])
    header_cell.font = _font(bold=True, white=True, size=11)
    header_cell.alignment = _align()

    for col_idx, day in enumerate(days, start=2):
        d = day.date
        dow = DAYS_RU[d.weekday()]
        label = f"{d.day}\n{dow}"
        cell = ws.cell(row=1, column=col_idx, value=label)
        bg = COLORS["weekend"] if day.is_holiday else "FFFFFF"
        cell.fill = _fill(bg)
        cell.font = _font(bold=day.is_holiday, size=9)
        cell.alignment = _align()

    # ── Строки 2+: по одной на каждого сотрудника ───────────────────────────
    for row_idx, emp in enumerate(employees, start=2):
        ws.row_dimensions[row_idx].height = 20

        # Столбец A: имя сотрудника
        name_cell = ws.cell(row=row_idx, column=1, value=emp.name)
        name_cell.fill = _fill(COLORS["name"])
        name_cell.font = _font(bold=True, size=10)
        name_cell.alignment = _align(horizontal="left")

        # Столбцы B+: смена на каждую дату
        emp_days = assignments.get(emp.name, {})
        for col_idx, day in enumerate(days, start=2):
            shift_key = emp_days.get(day.date, "day_off")
            label = SHIFT_LABELS.get(shift_key, "?")
            color = COLORS.get(shift_key, "FFFFFF")

            cell = ws.cell(row=row_idx, column=col_idx, value=label)
            cell.fill = _fill(color)
            cell.font = _font(white=shift_key in WHITE_FONT_KEYS, size=9)
            cell.alignment = _align()

    # ── Ширина столбцов ─────────────────────────────────────────────────────
    ws.column_dimensions["A"].width = 18  # имена
    for col_idx in range(2, len(days) + 2):
        ws.column_dimensions[get_column_letter(col_idx)].width = 5.5

    # ── Добавляем легенду на отдельный лист ─────────────────────────────────
    _add_legend(wb)

    # Заморозить первый столбец и первую строку
    ws.freeze_panes = "B2"

    wb.save(filename)
    return filename


def _add_legend(wb: Workbook) -> None:
    """Добавить лист с легендой цветов."""
    ws = wb.create_sheet(title="Легенда")
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 25

    items = [
        ("Утро", "morning", "08:00–17:00 МСК"),
        ("Вечер", "evening", "15:00–00:00 МСК"),
        ("Ночь", "night", "00:00–08:00 МСК (07:00–15:00 ХБ)"),
        ("РД", "workday", "Рабочий день 09:00–18:00"),
        ("Отп", "vacation", "Отпуск"),
        ("—", "day_off", "Выходной"),
    ]

    ws.cell(row=1, column=1, value="Обозн.").font = _font(bold=True, size=11)
    ws.cell(row=1, column=2, value="Описание").font = _font(bold=True, size=11)

    for i, (label, key, desc) in enumerate(items, start=2):
        color = COLORS[key]
        cell_label = ws.cell(row=i, column=1, value=label)
        cell_label.fill = _fill(color)
        cell_label.font = _font(white=key in WHITE_FONT_KEYS, bold=True, size=10)
        cell_label.alignment = _align()

        cell_desc = ws.cell(row=i, column=2, value=desc)
        cell_desc.font = _font(size=10)
        cell_desc.alignment = _align(horizontal="left")

        ws.row_dimensions[i].height = 20


def _shift_key_for(name: str, day_schedule, shift_types: list[ShiftType]) -> str:
    """Вспомогательная функция — не используется в основном потоке."""
    _ = (name, day_schedule, shift_types)
    return "day_off"
