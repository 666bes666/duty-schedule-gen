from __future__ import annotations

import pytest

from duty_schedule.api.ratelimit import RateLimitExceeded, SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    def test_allows_within_limit(self) -> None:
        limiter = SlidingWindowRateLimiter()
        for _ in range(5):
            limit, remaining, reset = limiter.check("key1", 5, 60)
        assert limit == 5
        assert remaining == 0

    def test_blocks_over_limit(self) -> None:
        limiter = SlidingWindowRateLimiter()
        for _ in range(5):
            limiter.check("key1", 5, 60)
        with pytest.raises(RateLimitExceeded):
            limiter.check("key1", 5, 60)

    def test_different_keys_independent(self) -> None:
        limiter = SlidingWindowRateLimiter()
        for _ in range(5):
            limiter.check("key1", 5, 60)
        limit, remaining, reset = limiter.check("key2", 5, 60)
        assert remaining == 4

    def test_returns_correct_remaining(self) -> None:
        limiter = SlidingWindowRateLimiter()
        limit, remaining, reset = limiter.check("key1", 10, 60)
        assert limit == 10
        assert remaining == 9

    def test_retry_after_on_exceeded(self) -> None:
        limiter = SlidingWindowRateLimiter()
        for _ in range(3):
            limiter.check("key1", 3, 60)
        with pytest.raises(RateLimitExceeded) as exc_info:
            limiter.check("key1", 3, 60)
        assert exc_info.value.retry_after > 0
