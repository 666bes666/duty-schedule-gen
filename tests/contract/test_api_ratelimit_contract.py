from __future__ import annotations

import pytest

from tests.contract.conftest import patch_holidays_holidays

RATE_LIMIT_HEADERS = {"X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"}


class TestRateLimitContract:
    @pytest.mark.asyncio
    async def test_headers_present(self, client_with_auth) -> None:
        with patch_holidays_holidays():
            resp = await client_with_auth.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200
        for header in RATE_LIMIT_HEADERS:
            assert header in resp.headers, f"Missing header: {header}"

    @pytest.mark.asyncio
    async def test_header_values_are_integers(self, client_with_auth) -> None:
        with patch_holidays_holidays():
            resp = await client_with_auth.get("/api/v1/holidays/2025/3")
        for header in RATE_LIMIT_HEADERS:
            int(resp.headers[header])

    @pytest.mark.asyncio
    async def test_remaining_decrements(self, client_with_auth) -> None:
        with patch_holidays_holidays():
            r1 = await client_with_auth.get("/api/v1/holidays/2025/3")
            r2 = await client_with_auth.get("/api/v1/holidays/2025/3")
        remaining1 = int(r1.headers["X-RateLimit-Remaining"])
        remaining2 = int(r2.headers["X-RateLimit-Remaining"])
        assert remaining2 < remaining1

    @pytest.mark.asyncio
    async def test_429_has_retry_after(self, client_with_auth) -> None:
        with patch_holidays_holidays():
            await client_with_auth.get("/api/v1/holidays/2025/3")
            await client_with_auth.get("/api/v1/holidays/2025/3")
            resp = await client_with_auth.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        int(resp.headers["Retry-After"])

    @pytest.mark.asyncio
    async def test_no_headers_when_auth_disabled(self, client) -> None:
        with patch_holidays_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200
        for header in RATE_LIMIT_HEADERS:
            assert header not in resp.headers
