from __future__ import annotations

from duty_schedule.calendar import fetch_holidays
from duty_schedule.logging import get_logger
from duty_schedule.models import CarryOverState, Config, Schedule
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
) -> list[Schedule]:
    logger.info(
        "multimonth_start",
        start=f"{start_month:02d}.{start_year}",
        end=f"{end_month:02d}.{end_year}",
    )
    schedules: list[Schedule] = []
    current_year, current_month = start_year, start_month
    carry_over: list[CarryOverState] = list(base_config.carry_over)

    while (current_year, current_month) <= (end_year, end_month):
        month_config = base_config.model_copy(
            update={
                "month": current_month,
                "year": current_year,
                "carry_over": carry_over,
            }
        )

        holidays, _short_days = fetch_holidays(current_year, current_month)
        schedule = generate_schedule(month_config, holidays)
        schedules.append(schedule)
        logger.info("multimonth_month_done", month=current_month, year=current_year)

        raw_carry = schedule.metadata.get("carry_over", [])
        carry_over = []
        for co in raw_carry:
            if isinstance(co, CarryOverState):
                carry_over.append(co)
            elif isinstance(co, dict):
                carry_over.append(CarryOverState(**co))

        current_year, current_month = _next_month(current_year, current_month)

    return schedules
