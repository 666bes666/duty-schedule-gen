from __future__ import annotations

import logging
import warnings

import duty_schedule.logging as log_mod
from duty_schedule.logging import _filter_sensitive, get_logger, setup_logging


class TestSetupLogging:
    def test_valid_level_no_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging("DEBUG", force=True)
            log_warnings = [x for x in w if "log level" in str(x.message).lower()]
            assert len(log_warnings) == 0

    def test_invalid_level_emits_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            setup_logging("BOGUS", force=True)
            log_warnings = [x for x in w if "BOGUS" in str(x.message)]
            assert len(log_warnings) == 1


class TestGetLogger:
    def test_get_logger_binds_name(self):
        logger = get_logger("my.module")
        assert "my.module" in str(logger)


class TestSensitiveFilter:
    def test_sensitive_data_filtered(self):
        event_dict = {
            "event": "test",
            "api_key": "super-secret-123",
            "token": "tok_abc",
            "username": "admin",
        }
        result = _filter_sensitive(None, "info", event_dict)
        assert result["api_key"] == "[REDACTED]"
        assert result["token"] == "[REDACTED]"
        assert result["username"] == "admin"

    def test_case_insensitive_keys(self):
        event_dict = {"Authorization": "Bearer xxx", "event": "test"}
        result = _filter_sensitive(None, "info", event_dict)
        assert result["Authorization"] == "[REDACTED]"


class TestEnvConfig:
    def test_env_var_overrides_level(self, monkeypatch):
        monkeypatch.setenv("DUTY_LOG_LEVEL", "DEBUG")
        monkeypatch.setattr(log_mod, "_configured", False)
        setup_logging("WARNING", force=True)
        root_level = logging.getLogger().level
        assert root_level == logging.DEBUG

    def test_setup_idempotent(self, monkeypatch):
        monkeypatch.setattr(log_mod, "_configured", False)
        setup_logging(force=True)
        setup_logging()
        setup_logging()
