from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.calendar import CalendarError
from duty_schedule.scheduler.core import ScheduleError


@pytest.fixture
def app():
    return create_app()


class TestExceptionHandlers:
    @pytest.mark.asyncio
    async def test_schedule_error_returns_400(self, app) -> None:
        @app.get("/test-schedule-error")
        async def _raise():
            raise ScheduleError("test error")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/test-schedule-error")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "schedule_error"
        assert body["detail"] == "test error"

    @pytest.mark.asyncio
    async def test_calendar_error_returns_502(self, app) -> None:
        @app.get("/test-calendar-error")
        async def _raise():
            raise CalendarError("service unavailable")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/test-calendar-error")
        assert resp.status_code == 502
        body = resp.json()
        assert body["error"] == "calendar_error"

    @pytest.mark.asyncio
    async def test_internal_error_returns_500(self, app) -> None:
        @app.get("/test-internal-error")
        async def _raise():
            raise RuntimeError("unexpected")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/test-internal-error")
        assert resp.status_code == 500
