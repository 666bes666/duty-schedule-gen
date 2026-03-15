"""Загрузка производственного календаря России через isdayoff.ru."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import httpx

from duty_schedule.logging import get_logger

logger = get_logger()

ISDAYOFF_URL = "https://isdayoff.ru/api/getdata"
TIMEOUT = 5.0

_HOLIDAY_CODE = "1"
_SHORT_DAY_CODE = "2"

RUSSIAN_PUBLIC_HOLIDAYS: frozenset[tuple[int, int]] = frozenset(
    {
        (1, 1),
        (1, 2),
        (1, 3),
        (1, 4),
        (1, 5),
        (1, 6),
        (1, 7),
        (1, 8),
        (2, 23),
        (3, 8),
        (5, 1),
        (5, 9),
        (6, 12),
        (11, 4),
    }
)


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
    return holidays, compute_short_days(year, month, holidays)


def compute_short_days(year: int, month: int, holidays: set[date]) -> set[date]:
    _, days_in_month = calendar.monthrange(year, month)
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    next_month = month % 12 + 1
    next_year = year + (1 if month == 12 else 0)

    target_holidays = set(holidays)
    for m, d in RUSSIAN_PUBLIC_HOLIDAYS:
        if m == next_month:
            target_holidays.add(date(next_year, next_month, d))

    short: set[date] = set()
    for h in target_holidays:
        prev = h - timedelta(days=1)
        while prev >= month_start and (prev.weekday() >= 5 or prev in target_holidays):
            prev -= timedelta(days=1)
        if month_start <= prev <= month_end and prev.weekday() < 5 and prev not in target_holidays:
            short.add(prev)
    return short


def get_all_days(year: int, month: int) -> list[date]:
    """Вернуть все даты указанного месяца."""
    _, days_in_month = calendar.monthrange(year, month)
    return [date(year, month, d) for d in range(1, days_in_month + 1)]
