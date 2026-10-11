from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date

import structlog

from duty_schedule.calendar import CalendarError, calendar_for_config, fetch_production_calendar
from duty_schedule.logging import get_logger
from duty_schedule.models import CarryOverState, Config, ProductionCalendar, Schedule
from duty_schedule.scheduler.core import generate_schedule

logger = get_logger(__name__)


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def generate_multimonth(
    base_config: Config,
    start_month: int,
    start_year: int,
    end_month: int,
    end_year: int,
    saved_calendars: Sequence[ProductionCalendar] | Mapping[str, ProductionCalendar] | None = None,
) -> list[Schedule]:
    date(start_year, start_month, 1)
    date(end_year, end_month, 1)
    if start_year < 2024 or end_year < 2024 or (start_year, start_month) > (end_year, end_month):
        raise ValueError("Некорректный диапазон месяцев")
    snapshots = (
        list(saved_calendars.values())
        if isinstance(saved_calendars, Mapping)
        else list(saved_calendars or [])
    )
    if base_config.production_calendar is not None:
        snapshots.append(base_config.production_calendar)
    context = structlog.contextvars.get_contextvars()
    owns_context = "request_id" not in context and "operation_id" not in context
    if owns_context:
        structlog.contextvars.bind_contextvars(operation_id=uuid.uuid4().hex[:8])
    logger.info(
        "multimonth_start",
        start=f"{start_month:02d}.{start_year}",
        end=f"{end_month:02d}.{end_year}",
    )
    schedules: list[Schedule] = []
    carry_over = list(base_config.carry_over)
    year, month = start_year, start_month
    try:
        while (year, month) <= (end_year, end_month):
            snapshot = next(
                (
                    item
                    for item in snapshots
                    if item.verified and (item.year, item.month) == (year, month)
                ),
                None,
            )
            month_config = base_config.model_copy(
                deep=True,
                update={
                    "month": month,
                    "year": year,
                    "carry_over": carry_over,
                    "production_calendar": None,
                },
            )
            if snapshot is not None:
                calendar = ProductionCalendar.model_validate(snapshot.model_dump())
                calendar.used_saved = True
            else:
                try:
                    calendar = fetch_production_calendar(year, month)
                except CalendarError:
                    calendar = calendar_for_config(month_config)
            month_config.production_calendar = calendar
            if schedules and schedules[-1].status == "ready":
                month_config.previous_schedule = schedules[-1].model_copy(deep=True)
                month_config.previous_schedule.config.previous_schedule = None
            elif schedules:
                month_config.previous_schedule = None
            schedule = generate_schedule(month_config)
            schedules.append(schedule)
            logger.info("multimonth_month_done", year=year, month=month, status=schedule.status)
            if schedule.status != "ready":
                logger.warning("multimonth_stopped_diagnostic", year=year, month=month)
                break
            carry_over = [
                CarryOverState.model_validate(item)
                for item in schedule.metadata.get("carry_over", [])
            ]
            year, month = _next_month(year, month)
    finally:
        if owns_context:
            structlog.contextvars.unbind_contextvars("operation_id")
    return schedules
