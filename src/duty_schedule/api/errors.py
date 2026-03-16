from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from duty_schedule.api.auth import AuthInvalidError, AuthMissingError
from duty_schedule.api.ratelimit import RateLimitExceeded
from duty_schedule.calendar import CalendarError
from duty_schedule.scheduler.core import ScheduleError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthMissingError)
    async def handle_auth_missing(request: Request, exc: AuthMissingError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": "auth_required", "detail": "API key is required"},
        )

    @app.exception_handler(AuthInvalidError)
    async def handle_auth_invalid(request: Request, exc: AuthInvalidError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": "auth_invalid", "detail": "Invalid API key"},
        )

    @app.exception_handler(RateLimitExceeded)
    async def handle_rate_limit(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited", "detail": "Rate limit exceeded"},
            headers={"Retry-After": str(exc.retry_after)},
        )

    @app.exception_handler(ScheduleError)
    async def handle_schedule_error(request: Request, exc: ScheduleError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "schedule_error", "detail": str(exc)},
        )

    @app.exception_handler(CalendarError)
    async def handle_calendar_error(request: Request, exc: CalendarError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": "calendar_error", "detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def handle_internal_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": str(exc)},
        )
