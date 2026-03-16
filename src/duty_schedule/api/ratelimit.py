from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Depends, Request

from duty_schedule.api.auth import verify_api_key
from duty_schedule.api.settings import ApiSettings, get_settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window: int) -> tuple[int, int, int]:
        now = time.monotonic()
        cutoff = now - window
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[key]

        remaining = max(0, max_requests - len(timestamps))
        reset = int(window - (now - timestamps[0])) if timestamps else window

        if len(timestamps) >= max_requests:
            raise RateLimitExceeded(retry_after=reset)

        timestamps.append(now)
        remaining = max(0, max_requests - len(timestamps))
        return max_requests, remaining, reset


_limiter = SlidingWindowRateLimiter()


def get_limiter() -> SlidingWindowRateLimiter:
    return _limiter


async def check_rate_limit(
    request: Request,
    api_key: str | None = Depends(verify_api_key),
    settings: ApiSettings = Depends(get_settings),
    limiter: SlidingWindowRateLimiter = Depends(get_limiter),
) -> None:
    if not settings.auth_enabled:
        return

    rate_key = api_key or request.client.host if request.client else "unknown"
    limit, remaining, reset = limiter.check(
        rate_key, settings.rate_limit_max, settings.rate_limit_window
    )
    request.state.rate_limit = limit
    request.state.rate_remaining = remaining
    request.state.rate_reset = reset
