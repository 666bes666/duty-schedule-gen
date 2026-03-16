from __future__ import annotations

import asyncio

from fastapi import APIRouter, Path

from duty_schedule.api.schemas import HolidaysResponse
from duty_schedule.calendar import fetch_holidays

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.get("/{year}/{month}", response_model=HolidaysResponse)
async def get_holidays(
    year: int = Path(ge=2024),
    month: int = Path(ge=1, le=12),
) -> HolidaysResponse:
    holidays, short_days = await asyncio.to_thread(fetch_holidays, year, month)
    return HolidaysResponse(
        year=year,
        month=month,
        holidays=sorted(holidays),
        short_days=sorted(short_days),
    )
