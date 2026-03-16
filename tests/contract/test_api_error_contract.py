from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from duty_schedule.calendar import CalendarError
from duty_schedule.scheduler.core import ScheduleError
from tests.contract.conftest import (
    JSON_HEADERS,
    config_payload,
    patch_holidays_holidays,
    patch_schedule_holidays,
)

ERROR_FIELDS = {"error", "detail"}


class TestErrorContract:
    @pytest.mark.asyncio
    async def test_400_format(self, client) -> None:
        with (
            patch_schedule_holidays(),
            patch(
                "duty_schedule.api.routes.schedule.generate_schedule",
                side_effect=ScheduleError("test error"),
            ),
        ):
            resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400
        assert set(resp.json().keys()) == ERROR_FIELDS

    @pytest.mark.asyncio
    async def test_401_format(self, app_with_auth, client_with_auth) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 401
        assert set(resp.json().keys()) == ERROR_FIELDS

    @pytest.mark.asyncio
    async def test_403_format(self, app_with_auth) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-API-Key": "wrong-key"},
        ) as c:
            resp = await c.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 403
        assert set(resp.json().keys()) == ERROR_FIELDS

    @pytest.mark.asyncio
    async def test_429_format(self, app_with_auth, client_with_auth) -> None:
        with patch_holidays_holidays():
            await client_with_auth.get("/api/v1/holidays/2025/3")
            await client_with_auth.get("/api/v1/holidays/2025/3")
            resp = await client_with_auth.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 429
        assert set(resp.json().keys()) == ERROR_FIELDS
        assert "Retry-After" in resp.headers

    @pytest.mark.asyncio
    async def test_502_format(self, client) -> None:
        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            side_effect=CalendarError("service down"),
        ):
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 502
        assert set(resp.json().keys()) == ERROR_FIELDS

    @pytest.mark.asyncio
    async def test_422_is_fastapi_native(self, client) -> None:
        resp = await client.post(
            "/api/v1/config/validate",
            content=b"not json",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        assert "loc" in body["detail"][0]
        assert "msg" in body["detail"][0]
        assert "type" in body["detail"][0]
