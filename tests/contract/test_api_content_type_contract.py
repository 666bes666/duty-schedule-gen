from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from duty_schedule.calendar import CalendarError
from tests.contract.conftest import (
    JSON_HEADERS,
    config_payload,
    patch_export_holidays,
    patch_holidays_holidays,
    patch_schedule_holidays,
    patch_whatif_holidays,
)

XLS_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class TestContentTypeContract:
    @pytest.mark.asyncio
    async def test_config_validate_json(self, client) -> None:
        resp = await client.post(
            "/api/v1/config/validate",
            json=config_payload(),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_holidays_json(self, client) -> None:
        with patch_holidays_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_schedule_generate_json(self, client) -> None:
        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_schedule_stats_json(self, client) -> None:
        with patch_schedule_holidays():
            gen_resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        resp = await client.post(
            "/api/v1/schedule/stats",
            json=gen_resp.json(),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_whatif_json(self, client) -> None:
        body = {
            "baseline": config_payload(),
            "variants": [{"name": "seed=99", "patch": {"seed": 99}}],
        }
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_xls_spreadsheet(self, client) -> None:
        with patch_export_holidays():
            resp = await client.post(
                "/api/v1/export/xls",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert XLS_MEDIA_TYPE in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_ics_single_calendar(self, client) -> None:
        with patch_export_holidays():
            resp = await client.post(
                "/api/v1/export/ics?employee_name=Иванов Иван",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_ics_all_zip(self, client) -> None:
        with patch_export_holidays():
            resp = await client.post(
                "/api/v1/export/ics",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "application/zip" in resp.headers["content-type"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,setup",
        [
            ("401", "auth_missing"),
            ("403", "auth_invalid"),
            ("502", "calendar_error"),
        ],
        ids=["401", "403", "502"],
    )
    async def test_error_responses_json(self, app_with_auth, client, status, setup) -> None:
        if setup == "auth_missing":
            transport = ASGITransport(app=app_with_auth)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                resp = await c.get("/api/v1/holidays/2025/3")
        elif setup == "auth_invalid":
            transport = ASGITransport(app=app_with_auth)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers={"X-API-Key": "wrong"},
            ) as c:
                resp = await c.get("/api/v1/holidays/2025/3")
        else:
            with patch(
                "duty_schedule.api.routes.holidays.fetch_holidays",
                side_effect=CalendarError("fail"),
            ):
                resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == int(status)
        assert "application/json" in resp.headers["content-type"]
