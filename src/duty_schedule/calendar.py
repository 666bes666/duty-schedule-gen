"""Загрузка производственного календаря России через isdayoff.ru."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Literal

import httpx

from duty_schedule.logging import get_logger, log_duration
from duty_schedule.models import CalendarDay, Config, ProductionCalendar

logger = get_logger(__name__)

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


def fetch_production_calendar(
    year: int, month: int, saved: ProductionCalendar | None = None
) -> ProductionCalendar:
    try:
        with log_duration(
            logger, "holidays_api_call", level="debug", year=year, month=month
        ) as bag:
            response = httpx.get(
                ISDAYOFF_URL,
                params={"year": year, "month": month, "cc": "ru", "pre": 1},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            bag["status_code"] = response.status_code
        data = response.text.strip()
        expected = calendar.monthrange(year, month)[1]
        if len(data) != expected:
            raise CalendarError(
                f"Неожиданный ответ: ожидалось {expected} символов, получено {len(data)}"
            )
        if any(code not in "012" for code in data):
            raise CalendarError(
                "Производственный календарь содержит неполные или неизвестные данные"
            )
        kinds: dict[str, Literal["working", "off", "short"]] = {
            "0": "working",
            "1": "off",
            "2": "short",
        }
        result = ProductionCalendar(
            year=year,
            month=month,
            days=[
                CalendarDay(
                    date=date(year, month, index),
                    kind=kinds[code],
                )
                for index, code in enumerate(data, start=1)
            ],
            source=ISDAYOFF_URL,
            fetched_at=datetime.now(UTC),
        )
    except (httpx.HTTPError, ValueError, CalendarError) as exc:
        if saved is not None and saved.verified and (saved.year, saved.month) == (year, month):
            try:
                result = ProductionCalendar.model_validate(saved.model_dump())
            except ValueError:
                raise CalendarError(
                    f"Не удалось получить производственный календарь: {exc}"
                ) from exc
            result.used_saved = True
            logger.warning("saved_calendar_used", year=year, month=month, source=result.source)
            return result
        raise CalendarError(f"Не удалось получить производственный календарь: {exc}") from exc
    logger.info(
        "holidays_loaded",
        year=year,
        month=month,
        holidays_count=len(result.off_dates()),
        short_days_count=len(result.short_dates()),
    )
    return result


def fetch_holidays(year: int, month: int) -> tuple[set[date], set[date]]:
    result = fetch_production_calendar(year, month)
    return result.off_dates(), result.short_dates()


def calendar_for_config(config: Config, holidays: set[date] | None = None) -> ProductionCalendar:
    if config.production_calendar is not None:
        result = ProductionCalendar.model_validate(config.production_calendar.model_dump())
        if (result.year, result.month) != (config.year, config.month):
            raise CalendarError("Период производственного календаря не совпадает с графиком")
        return result
    return ProductionCalendar(
        year=config.year,
        month=config.month,
        days=[
            CalendarDay(
                date=day,
                kind="off" if day.weekday() >= 5 or day in (holidays or set()) else "working",
            )
            for day in get_all_days(config.year, config.month)
        ],
        source="legacy_weekday_fallback",
        fetched_at=datetime.now(UTC),
        verified=False,
    )


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
            logger.warning("holiday_outside_month_skipped", date=raw)
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
