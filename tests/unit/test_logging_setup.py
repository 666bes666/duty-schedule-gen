from __future__ import annotations

import ast
import logging
import re
import warnings
from pathlib import Path

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


_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "critical", "exception"})


def _extract_event_names() -> list[tuple[str, int, str]]:
    src_root = Path(__file__).resolve().parents[2] / "src" / "duty_schedule"
    results: list[tuple[str, int, str]] = []
    for py_file in src_root.rglob("*.py"):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr in _LOG_METHODS
                and isinstance(func.value, ast.Name)
                and func.value.id == "logger"
            ):
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                rel = py_file.relative_to(src_root)
                results.append((str(rel), first_arg.end_lineno or 0, first_arg.value))
    return results


class TestEventNameConventions:
    def test_no_cyrillic_in_event_names(self):
        violations = []
        for file, line, event in _extract_event_names():
            if _CYRILLIC_RE.search(event):
                violations.append(f"{file}:{line} -> {event!r}")
        assert violations == [], "Cyrillic found in event names:\n" + "\n".join(violations)

    def test_event_names_snake_case(self):
        violations = []
        for file, line, event in _extract_event_names():
            if not _EVENT_NAME_RE.match(event):
                violations.append(f"{file}:{line} -> {event!r}")
        assert violations == [], "Non-snake_case event names:\n" + "\n".join(violations)
