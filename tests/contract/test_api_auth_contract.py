from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.contract.conftest import (
    JSON_HEADERS,
    config_payload,
    patch_holidays_holidays,
)


class TestAuthContract:
    @pytest.mark.asyncio
    async def test_401_body_exact(self, app_with_auth) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 401
        assert resp.json() == {"error": "auth_required", "detail": "API key is required"}

    @pytest.mark.asyncio
    async def test_403_body_exact(self, app_with_auth) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"X-API-Key": "wrong-key"},
        ) as c:
            resp = await c.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 403
        assert resp.json() == {"error": "auth_invalid", "detail": "Invalid API key"}

    @pytest.mark.asyncio
    async def test_401_content_type_json(self, app_with_auth) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 401
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method,path,needs_body",
        [
            ("POST", "/api/v1/config/validate", True),
            ("GET", "/api/v1/holidays/2025/3", False),
            ("POST", "/api/v1/schedule/generate", True),
            ("POST", "/api/v1/schedule/stats", True),
            ("POST", "/api/v1/export/xls", True),
            ("POST", "/api/v1/export/ics", True),
            ("POST", "/api/v1/whatif/compare", True),
        ],
    )
    async def test_all_endpoints_require_auth(
        self, app_with_auth, method, path, needs_body
    ) -> None:
        transport = ASGITransport(app=app_with_auth)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            kwargs: dict = {}
            if needs_body:
                kwargs["json"] = config_payload()
                kwargs["headers"] = JSON_HEADERS
            resp = await c.request(method, path, **kwargs)
        assert resp.status_code == 401, f"{method} {path} should require auth"

    @pytest.mark.asyncio
    async def test_valid_key_passes(self, client_with_auth) -> None:
        with patch_holidays_holidays():
            resp = await client_with_auth.get("/api/v1/holidays/2025/3")
        assert resp.status_code not in (401, 403)
