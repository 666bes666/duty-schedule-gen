from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.api.ratelimit import SlidingWindowRateLimiter, get_limiter
from duty_schedule.api.settings import ApiSettings, get_settings


def _make_settings(**kwargs: object) -> ApiSettings:
    defaults = {"auth_enabled": True, "keys": "test-key", "rate_limit": "60/minute"}
    defaults.update(kwargs)
    return ApiSettings(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def app():
    application = create_app()
    settings = _make_settings()
    application.dependency_overrides[get_settings] = lambda: settings
    limiter = SlidingWindowRateLimiter()
    application.dependency_overrides[get_limiter] = lambda: limiter
    return application


@pytest.fixture
def app_auth_disabled():
    application = create_app()
    settings = _make_settings(auth_enabled=False)
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_no_auth(app_auth_disabled):
    transport = ASGITransport(app=app_auth_disabled)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestAuthIntegration:
    @pytest.mark.asyncio
    async def test_no_key_returns_401(self, client) -> None:
        resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 401
        assert resp.json()["error"] == "auth_required"

    @pytest.mark.asyncio
    async def test_invalid_key_returns_403(self, client) -> None:
        resp = await client.get("/api/v1/holidays/2025/3", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "auth_invalid"

    @pytest.mark.asyncio
    async def test_valid_key_passes(self, client) -> None:
        from unittest.mock import patch

        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            return_value=(set(), set()),
        ):
            resp = await client.get("/api/v1/holidays/2025/3", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bearer_token_works(self, client) -> None:
        from unittest.mock import patch

        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            return_value=(set(), set()),
        ):
            resp = await client.get(
                "/api/v1/holidays/2025/3",
                headers={"Authorization": "Bearer test-key"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_disabled_skips_check(self, client_no_auth) -> None:
        from unittest.mock import patch

        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            return_value=(set(), set()),
        ):
            resp = await client_no_auth.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_open_without_key(self, client) -> None:
        resp = await client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_openapi_open_without_key(self, client) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200


class TestRateLimitIntegration:
    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self, client) -> None:
        from unittest.mock import patch

        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            return_value=(set(), set()),
        ):
            resp = await client.get("/api/v1/holidays/2025/3", headers={"X-API-Key": "test-key"})
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers
        assert "X-RateLimit-Reset" in resp.headers

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_returns_429(self) -> None:
        application = create_app()
        settings = _make_settings(rate_limit="3/minute")
        application.dependency_overrides[get_settings] = lambda: settings
        limiter = SlidingWindowRateLimiter()
        application.dependency_overrides[get_limiter] = lambda: limiter

        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            from unittest.mock import patch

            with patch(
                "duty_schedule.api.routes.holidays.fetch_holidays",
                return_value=(set(), set()),
            ):
                for _ in range(3):
                    resp = await c.get("/api/v1/holidays/2025/3", headers={"X-API-Key": "test-key"})
                    assert resp.status_code == 200

                resp = await c.get("/api/v1/holidays/2025/3", headers={"X-API-Key": "test-key"})
            assert resp.status_code == 429
            assert resp.json()["error"] == "rate_limited"
            assert "Retry-After" in resp.headers
