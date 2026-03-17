from __future__ import annotations

import pytest
import structlog
from structlog.testing import capture_logs

from duty_schedule.logging import log_duration, setup_logging


@pytest.fixture(autouse=True)
def _ensure_debug_logging():
    setup_logging("DEBUG", force=True)


class TestLogDuration:
    def test_logs_elapsed(self):
        logger = structlog.get_logger("test")
        with capture_logs() as cap, log_duration(logger, "test_op"):
            pass
        assert len(cap) == 1
        assert cap[0]["event"] == "test_op"
        assert "duration_ms" in cap[0]
        assert isinstance(cap[0]["duration_ms"], float)

    def test_on_exception(self):
        logger = structlog.get_logger("test")
        with capture_logs() as cap:
            try:
                with log_duration(logger, "fail_op"):
                    raise ValueError("boom")
            except ValueError:
                pass
        assert len(cap) == 1
        assert cap[0]["event"] == "fail_op"
        assert "duration_ms" in cap[0]

    def test_bag_fields(self):
        logger = structlog.get_logger("test")
        with capture_logs() as cap, log_duration(logger, "bag_op") as bag:
            bag["status_code"] = 200
            bag["items"] = 42
        assert len(cap) == 1
        assert cap[0]["status_code"] == 200
        assert cap[0]["items"] == 42

    def test_extra_kwargs(self):
        logger = structlog.get_logger("test")
        with capture_logs() as cap, log_duration(logger, "extra_op", year=2025):
            pass
        assert cap[0]["year"] == 2025

    def test_level_parameter(self):
        logger = structlog.get_logger("test")
        with capture_logs() as cap, log_duration(logger, "debug_op", level="debug"):
            pass
        assert len(cap) == 1
        assert cap[0]["log_level"] == "debug"
