from __future__ import annotations

import secrets
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from duty_schedule.api.settings import ApiSettings, get_settings

logger = structlog.get_logger()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthMissingError(Exception):
    pass


class AuthInvalidError(Exception):
    pass


async def verify_api_key(
    request: Request,
    api_key: Annotated[str | None, Depends(api_key_header)] = None,
    settings: ApiSettings = Depends(get_settings),
) -> str | None:
    if not settings.auth_enabled:
        return None

    if api_key is None:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            api_key = auth_header[7:].strip()

    if not api_key:
        await logger.ainfo("auth_missing", path=str(request.url.path))
        raise AuthMissingError

    valid_keys = settings.parsed_keys
    if not valid_keys:
        await logger.awarning("no_api_keys_configured")
        raise AuthMissingError

    if not any(secrets.compare_digest(api_key, k) for k in valid_keys):
        await logger.awarning("auth_invalid", path=str(request.url.path))
        raise AuthInvalidError

    return api_key
