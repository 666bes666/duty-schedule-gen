from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from duty_schedule.api.auth import verify_api_key
from duty_schedule.api.settings import ApiSettings, get_settings


def _make_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI()

    def override_settings() -> ApiSettings:
        return settings

    app.dependency_overrides[get_settings] = override_settings

    @app.get("/protected")
    async def protected(key: str | None = Depends(verify_api_key)) -> dict[str, str | None]:
        return {"key": key}

    from duty_schedule.api.errors import register_exception_handlers

    register_exception_handlers(app)
    return app


class TestVerifyApiKey:
    @pytest.mark.asyncio
    async def test_auth_disabled_passes(self) -> None:
        app = _make_app(ApiSettings(auth_enabled=False))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected")
        assert resp.status_code == 200
        assert resp.json()["key"] is None

    @pytest.mark.asyncio
    async def test_valid_key_via_header(self) -> None:
        app = _make_app(ApiSettings(keys="valid-key"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected", headers={"X-API-Key": "valid-key"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "valid-key"

    @pytest.mark.asyncio
    async def test_valid_key_via_bearer(self) -> None:
        app = _make_app(ApiSettings(keys="valid-key"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected", headers={"Authorization": "Bearer valid-key"})
        assert resp.status_code == 200
        assert resp.json()["key"] == "valid-key"

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self) -> None:
        app = _make_app(ApiSettings(keys="valid-key"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected")
        assert resp.status_code == 401
        assert resp.json()["error"] == "auth_required"

    @pytest.mark.asyncio
    async def test_invalid_key_returns_403(self) -> None:
        app = _make_app(ApiSettings(keys="valid-key"))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "auth_invalid"

    @pytest.mark.asyncio
    async def test_no_keys_configured_returns_401(self) -> None:
        app = _make_app(ApiSettings(keys="", auth_enabled=True))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/protected", headers={"X-API-Key": "any-key"})
        assert resp.status_code == 401
