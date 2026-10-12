from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from duty_schedule.api.schemas import WhatIfRequest, WhatIfResponse
from duty_schedule.api.whatif_service import run_whatif
from duty_schedule.calendar import fetch_production_calendar
from duty_schedule.logging import get_logger
from duty_schedule.models import Config
from duty_schedule.scheduler.core import ScheduleError

logger = get_logger(__name__)

router = APIRouter(prefix="/whatif", tags=["whatif"])


@router.post("/compare", response_model=WhatIfResponse)
async def compare_scenarios(request: WhatIfRequest) -> WhatIfResponse:
    try:
        baseline_config = Config.model_validate(request.baseline)
    except ValidationError as exc:
        logger.warning("whatif_invalid_baseline", error=str(exc))
        raise HTTPException(status_code=400, detail="Невалидный baseline") from exc

    calendar = baseline_config.production_calendar
    if calendar is None:
        calendar = await asyncio.to_thread(
            fetch_production_calendar, baseline_config.year, baseline_config.month
        )
        baseline_config = baseline_config.model_copy(update={"production_calendar": calendar})
    holidays, short_days = calendar.off_dates(), calendar.short_dates()

    variant_patches = [(v.name, v.patch) for v in request.variants]

    try:
        result = await asyncio.to_thread(
            run_whatif, baseline_config, variant_patches, holidays, short_days
        )
    except ScheduleError as exc:
        logger.warning("whatif_schedule_error", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result
