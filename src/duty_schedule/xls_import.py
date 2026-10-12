from __future__ import annotations

import json
import re
from datetime import date, timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any

from openpyxl import load_workbook

from duty_schedule.export.xls import SHIFT_LABELS
from duty_schedule.models import CarryOverState, ShiftType

if TYPE_CHECKING:
    from openpyxl.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

LABEL_TO_SHIFT: dict[str, ShiftType] = {
    label.strip().lower(): ShiftType(key) for key, label in SHIFT_LABELS.items()
}

SCHED_SHEET_NAME = "График дежурств"

WORKING_SHIFTS = frozenset(
    {ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY}
)


class XlsImportError(Exception):
    pass


def _find_sheet(wb: Workbook) -> Worksheet:
    for name in wb.sheetnames:
        if name == SCHED_SHEET_NAME:
            return wb[name]
    return wb.worksheets[0]


def _resolve_shift(raw: object) -> ShiftType:
    if raw is None:
        raise XlsImportError("Пустая ячейка смены не является подтверждённым выходным")
    text = str(raw).strip().lower()
    if re.fullmatch(r"день \(\d+\s*ч\)", text):
        return ShiftType.WORKDAY
    if text == "б":
        return ShiftType.SICK_LEAVE
    shift = LABEL_TO_SHIFT.get(text)
    if shift is None:
        raise XlsImportError(f"Неизвестная ячейка смены: {raw!r}")
    return shift


def _find_day_columns(ws: Worksheet) -> tuple[int, int]:
    start_col = 3
    end_col = start_col
    for col in range(start_col, ws.max_column + 1):
        val = ws.cell(row=2, column=col).value
        if val is not None and "итого" in str(val).strip().lower():
            break
        end_col = col
    if end_col < start_col:
        raise XlsImportError(
            "Не удалось определить диапазон дней в строке 2. "
            "Убедитесь, что файл содержит корректный график дежурств."
        )
    return start_col, end_col


def _build_carry_over(
    name: str,
    shifts: list[ShiftType],
    employee_id: str | None = None,
    as_of: date | None = None,
    initial: CarryOverState | None = None,
) -> CarryOverState:
    last = initial.last_shift if initial else None
    working = initial.consecutive_working if initial else 0
    off = initial.consecutive_off if initial else 0
    same = initial.consecutive_same_shift if initial else 0
    for shift in shifts:
        if shift in WORKING_SHIFTS:
            working += 1
            off = 0
            same = same + 1 if shift == last else 1
        else:
            off += 1
            working = 0
            same = 0
        last = shift
    return CarryOverState(
        employee_name=name,
        employee_id=employee_id,
        last_shift=last,
        consecutive_working=working,
        consecutive_off=off,
        consecutive_same_shift=same,
        as_of=as_of,
        source="xls" if as_of else "legacy",
    )


def _read_metadata(wb: Workbook) -> dict[str, Any]:
    name = "__duty_schedule_metadata__"
    if name not in wb.sheetnames:
        return {}
    try:
        result = json.loads(
            "".join(
                str(wb[name].cell(row=row, column=1).value)
                for row in range(1, wb[name].max_row + 1)
                if wb[name].cell(row=row, column=1).value is not None
            )
        )
        if not isinstance(result, dict) or result.get("format_version") != 1:
            raise ValueError("Неподдерживаемая версия XLS metadata")
        if not isinstance(result.get("employee_ids", {}), dict):
            raise ValueError("Некорректные идентификаторы сотрудников")
        date(int(result["year"]), int(result["month"]), 1)
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise XlsImportError(f"Некорректные metadata XLS: {exc}") from exc


def parse_carry_over_from_xls(file_bytes: bytes) -> list[CarryOverState]:
    try:
        wb = load_workbook(BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise XlsImportError(f"Не удалось открыть файл: {exc}") from exc

    ws = _find_sheet(wb)
    metadata = _read_metadata(wb)

    try:
        start_col, end_col = _find_day_columns(ws)
    except XlsImportError:
        raise
    except Exception as exc:
        raise XlsImportError(f"Ошибка при разборе структуры файла: {exc}") from exc

    as_of = None
    initial_history: list[CarryOverState] = []
    if metadata:
        try:
            as_of = date(int(metadata["year"]), int(metadata["month"]), end_col - start_col + 1)
            initial_history = [
                CarryOverState.model_validate(item) for item in metadata.get("initial_history", [])
            ]
            for col in range(start_col, end_col + 1):
                label = str(ws.cell(row=2, column=col).value)
                match = re.match(r"^(\d+)", label)
                if match is None or int(match[1]) != col - start_col + 1:
                    raise ValueError("Неоднозначные или пропущенные даты XLS")
        except (TypeError, ValueError) as exc:
            raise XlsImportError(f"Неверный период XLS: {exc}") from exc
    results: list[CarryOverState] = []
    row = 3
    expected_names = set(metadata.get("employee_ids", {}))
    while row <= ws.max_row:
        name_val = ws.cell(row=row, column=1).value
        if name_val is None or str(name_val).strip() == "":
            if any(
                ws.cell(row=row, column=col).value is not None
                for col in range(start_col, end_col + 1)
            ):
                raise XlsImportError(f"Строка {row}: пустое имя сотрудника")
            row += 1
            continue
        name = str(name_val)
        if name not in expected_names and name.startswith("'") and name[1:] in expected_names:
            name = name[1:]
        if expected_names and name not in expected_names:
            raise XlsImportError(f"Строка {row}: неизвестное имя {name!r}")

        shifts: list[ShiftType] = []
        for col in range(start_col, end_col + 1):
            cell_val = ws.cell(row=row, column=col).value
            shifts.append(_resolve_shift(cell_val))

        employee_id = metadata.get("employee_ids", {}).get(name)
        if employee_id is not None and not isinstance(employee_id, str):
            raise XlsImportError("Идентификатор сотрудника должен быть строкой")
        initial = (
            next(
                (
                    carry
                    for carry in initial_history
                    if carry.employee_id == employee_id
                    if employee_id
                ),
                None,
            )
            if employee_id
            else next((carry for carry in initial_history if carry.employee_name == name), None)
        )
        if initial and initial.as_of != date(
            int(metadata["year"]), int(metadata["month"]), 1
        ) - timedelta(days=1):
            raise XlsImportError("Исходная история XLS относится к неверному периоду")
        results.append(_build_carry_over(name, shifts, employee_id, as_of, initial))
        row += 1

    if expected_names and {item.employee_name for item in results} != expected_names:
        raise XlsImportError("XLS содержит неполный состав сотрудников")
    return results
