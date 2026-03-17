from __future__ import annotations

import time
import uuid

import structlog
from fastapi import Depends, FastAPI, Request, Response

from duty_schedule.api.errors import register_exception_handlers
from duty_schedule.api.ratelimit import check_rate_limit
from duty_schedule.api.routes.config import router as config_router
from duty_schedule.api.routes.export import router as export_router
from duty_schedule.api.routes.holidays import router as holidays_router
from duty_schedule.api.routes.schedule import router as schedule_router
from duty_schedule.api.routes.whatif import router as whatif_router
from duty_schedule.logging import get_logger, setup_logging

logger = get_logger(__name__)


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="Duty Schedule API",
        version="2.0.0",
        description="REST API для генератора графиков дежурств 24/7",
    )

    register_exception_handlers(app)

    prefix = "/api/v1"
    api_deps = [Depends(check_rate_limit)]
    app.include_router(schedule_router, prefix=prefix, dependencies=api_deps)
    app.include_router(config_router, prefix=prefix, dependencies=api_deps)
    app.include_router(holidays_router, prefix=prefix, dependencies=api_deps)
    app.include_router(export_router, prefix=prefix, dependencies=api_deps)
    app.include_router(whatif_router, prefix=prefix, dependencies=api_deps)

    @app.middleware("http")
    async def log_requests(request: Request, call_next: object) -> Response:
        request_id = uuid.uuid4().hex[:8]
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=str(request.url.path),
        )
        logger.info("request_started")
        start = time.monotonic()
        try:
            response = await call_next(request)  # type: ignore[operator]
            duration_ms = round((time.monotonic() - start) * 1000, 1)
            logger.info(
                "request_finished",
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response  # type: ignore[no-any-return]
        finally:
            structlog.contextvars.clear_contextvars()

    @app.middleware("http")
    async def add_rate_limit_headers(request: Request, call_next: object) -> Response:
        response = await call_next(request)  # type: ignore[operator]
        if hasattr(request.state, "rate_limit"):
            response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(request.state.rate_remaining)
            response.headers["X-RateLimit-Reset"] = str(request.state.rate_reset)
        return response  # type: ignore[no-any-return]

    return app


def run() -> None:
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
