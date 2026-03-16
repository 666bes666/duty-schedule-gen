from __future__ import annotations

from fastapi import APIRouter

from duty_schedule.api.schemas import ConfigValidationResponse
from duty_schedule.models import Config, collect_config_issues

router = APIRouter(prefix="/config", tags=["config"])


@router.post("/validate", response_model=ConfigValidationResponse)
async def validate_config(config: Config) -> ConfigValidationResponse:
    errors, warnings = collect_config_issues(config)
    return ConfigValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )
