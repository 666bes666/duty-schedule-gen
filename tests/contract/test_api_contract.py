from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app


class TestOpenAPIContract:
    @pytest.mark.asyncio
    async def test_openapi_schema_available(self, client) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Duty Schedule API"
        assert schema["info"]["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_all_endpoints_present(self, client) -> None:
        resp = await client.get("/openapi.json")
        paths = resp.json()["paths"]
        expected = [
            "/api/v1/schedule/generate",
            "/api/v1/schedule/stats",
            "/api/v1/config/validate",
            "/api/v1/holidays/{year}/{month}",
            "/api/v1/export/xls",
            "/api/v1/export/ics",
            "/api/v1/whatif/compare",
        ]
        for path in expected:
            assert path in paths, f"Missing endpoint: {path}"

    @pytest.mark.asyncio
    async def test_schedule_generate_accepts_post(self, client) -> None:
        resp = await client.get("/openapi.json")
        paths = resp.json()["paths"]
        assert "post" in paths["/api/v1/schedule/generate"]

    @pytest.mark.asyncio
    async def test_holidays_accepts_get(self, client) -> None:
        resp = await client.get("/openapi.json")
        paths = resp.json()["paths"]
        assert "get" in paths["/api/v1/holidays/{year}/{month}"]

    @pytest.mark.asyncio
    async def test_docs_page_available(self, client) -> None:
        resp = await client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_security_scheme_api_key(self) -> None:
        application = create_app()
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/openapi.json")
        schema = resp.json()
        security_schemes = schema.get("components", {}).get("securitySchemes", {})
        assert "APIKeyHeader" in security_schemes
        assert security_schemes["APIKeyHeader"]["type"] == "apiKey"
        assert security_schemes["APIKeyHeader"]["in"] == "header"

    @pytest.mark.asyncio
    async def test_whatif_accepts_post(self, client) -> None:
        resp = await client.get("/openapi.json")
        paths = resp.json()["paths"]
        assert "post" in paths["/api/v1/whatif/compare"]

    @pytest.mark.asyncio
    async def test_openapi_version_semver(self, client) -> None:
        resp = await client.get("/openapi.json")
        version = resp.json()["info"]["version"]
        assert re.match(r"^\d+\.\d+\.\d+$", version)
