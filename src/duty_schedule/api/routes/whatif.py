from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from duty_schedule.api.schemas import WhatIfRequest, WhatIfResponse
from duty_schedule.api.whatif_service import run_whatif
from duty_schedule.calendar import fetch_holidays
from duty_schedule.models import Config
from duty_schedule.scheduler.core import ScheduleError

router = APIRouter(prefix="/whatif", tags=["whatif"])


@router.post("/compare", response_model=WhatIfResponse)
async def compare_scenarios(request: WhatIfRequest) -> WhatIfResponse:
    try:
        baseline_config = Config.model_validate(request.baseline)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Невалидный baseline: {exc}") from exc

    holidays, short_days = await asyncio.to_thread(
        fetch_holidays, baseline_config.year, baseline_config.month
    )

    variant_patches = [(v.name, v.patch) for v in request.variants]

    try:
        result = await asyncio.to_thread(
            run_whatif, baseline_config, variant_patches, holidays, short_days
        )
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result
