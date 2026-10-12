from __future__ import annotations

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from duty_schedule.api.planning import plan_schedule
from duty_schedule.api.schemas import (
    EmployeeStatsSchema,
    MultiMonthRequest,
    MultiMonthResponse,
    ScheduleNotReadyResponse,
)
from duty_schedule.calendar import calendar_for_config
from duty_schedule.logging import get_logger
from duty_schedule.models import Config, Schedule, collect_config_issues
from duty_schedule.project import ensure_exportable
from duty_schedule.scheduler import generate_schedule
from duty_schedule.stats import build_assignments, compute_stats

logger = get_logger(__name__)
router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/plan", response_model=Schedule)
async def plan(config: Config) -> Schedule:
    logger.info("schedule_plan_start", month=config.month, year=config.year, solver=config.solver)
    schedule = await asyncio.to_thread(plan_schedule, config, generate_schedule)
    logger.info("schedule_plan_done", status=schedule.status, days=len(schedule.days))
    return schedule


@router.post(
    "/generate",
    response_model=Schedule,
    responses={
        409: {"model": ScheduleNotReadyResponse, "description": "Schedule failed mandatory checks"}
    },
)
async def generate(config: Config) -> Schedule:
    cfg_errors, _cfg_warnings = collect_config_issues(config)
    if cfg_errors:
        raise HTTPException(status_code=400, detail=cfg_errors)
    schedule = await plan(config)
    return ensure_exportable(schedule)


@router.post("/stats", response_model=list[EmployeeStatsSchema])
async def stats(schedule: Schedule) -> list[EmployeeStatsSchema]:
    assignments = build_assignments(schedule)
    calendar = calendar_for_config(schedule.config)
    production_days = sum(calendar.is_working(day.date) for day in calendar.days)
    result = compute_stats(
        schedule, assignments, production_days, short_days=calendar.short_dates()
    )
    return [EmployeeStatsSchema(**asdict(item)) for item in result]


@router.post("/generate-range", response_model=MultiMonthResponse)
async def generate_range(request: MultiMonthRequest) -> MultiMonthResponse:
    from duty_schedule.scheduler.multimonth import generate_multimonth

    schedules = await asyncio.to_thread(
        generate_multimonth,
        request.config,
        request.start_month,
        request.start_year,
        request.end_month,
        request.end_year,
    )
    return MultiMonthResponse(schedules=schedules)
