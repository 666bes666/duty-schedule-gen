from __future__ import annotations

import asyncio

from fastapi import APIRouter

from duty_schedule.api.schemas import EmployeeStatsSchema
from duty_schedule.calendar import fetch_holidays
from duty_schedule.models import Config, Schedule
from duty_schedule.scheduler import generate_schedule
from duty_schedule.scheduler.constraints import _calc_production_days
from duty_schedule.stats import build_assignments, compute_stats

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.post("/generate", response_model=Schedule)
async def generate(config: Config) -> Schedule:
    holidays, _short_days = await asyncio.to_thread(fetch_holidays, config.year, config.month)
    schedule = await asyncio.to_thread(generate_schedule, config, holidays)
    return schedule


@router.post("/stats", response_model=list[EmployeeStatsSchema])
async def stats(schedule: Schedule) -> list[EmployeeStatsSchema]:
    assignments = build_assignments(schedule)
    holidays = {day.date for day in schedule.days if day.is_holiday}
    production_days = _calc_production_days(schedule.config.year, schedule.config.month, holidays)
    result = compute_stats(schedule, assignments, production_days)
    return [
        EmployeeStatsSchema(
            name=s.name,
            city=s.city,
            total_working=s.total_working,
            target=s.target,
            morning=s.morning,
            evening=s.evening,
            night=s.night,
            workday=s.workday,
            day_off=s.day_off,
            vacation=s.vacation,
            weekend_work=s.weekend_work,
            holiday_work=s.holiday_work,
            max_streak_work=s.max_streak_work,
            max_streak_rest=s.max_streak_rest,
            isolated_off=s.isolated_off,
            paired_off=s.paired_off,
            total_hours=s.total_hours,
        )
        for s in result
    ]
