"""Загрузка производственного календаря России через isdayoff.ru."""

from __future__ import annotations

import calendar
from datetime import date

import httpx

from duty_schedule.logging import get_logger

logger = get_logger()

ISDAYOFF_URL = "https://isdayoff.ru/api/getdata"
TIMEOUT = 5.0

_HOLIDAY_CODE = "1"
_SHORT_DAY_CODE = "2"


class CalendarError(Exception):
    """Ошибка при получении производственного календаря."""


def fetch_holidays(year: int, month: int) -> tuple[set[date], set[date]]:
    try:
        resp = httpx.get(
            ISDAYOFF_URL,
            params={"year": year, "month": month, "cc": "ru"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CalendarError(f"Не удалось получить производственный календарь: {exc}") from exc

    data = resp.text.strip()
    _, days_in_month = calendar.monthrange(year, month)

    if len(data) != days_in_month:
        raise CalendarError(
            f"Неожиданный ответ isdayoff.ru: ожидалось {days_in_month} "
            f"символов, получено {len(data)}"
        )

    holidays: set[date] = set()
    short_days: set[date] = set()
    for day_idx, code in enumerate(data, start=1):
        if code == _HOLIDAY_CODE:
            holidays.add(date(year, month, day_idx))
        elif code == _SHORT_DAY_CODE:
            short_days.add(date(year, month, day_idx))

    logger.info(
        "Праздники загружены",
        year=year,
        month=month,
        holidays_count=len(holidays),
        short_days_count=len(short_days),
    )
    return holidays, short_days


def parse_manual_holidays(holidays_str: str, year: int, month: int) -> tuple[set[date], set[date]]:
    holidays: set[date] = set()
    for raw in holidays_str.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            raise CalendarError(
                f"Неверный формат даты праздника: {raw!r} (ожидается YYYY-MM-DD)"
            ) from None
        if d.year != year or d.month != month:
            logger.warning("Праздник вне указанного месяца пропущен", date=raw)
            continue
        holidays.add(d)
    return holidays, set()


def get_all_days(year: int, month: int) -> list[date]:
    """Вернуть все даты указанного месяца."""
    _, days_in_month = calendar.monthrange(year, month)
    return [date(year, month, d) for d in range(1, days_in_month + 1)]
