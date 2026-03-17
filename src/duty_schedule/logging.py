from __future__ import annotations

import logging
import os
import sys
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from typing import Any

import structlog

_configured = False

_SENSITIVE_KEYS = frozenset({"api_key", "key", "token", "secret", "password", "authorization"})


def _filter_sensitive(
    logger: Any, method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for k in event_dict:
        if k.lower() in _SENSITIVE_KEYS:
            event_dict[k] = "[REDACTED]"
    return event_dict


class _LazyStderrFactory:
    def __call__(self, *args: object, **kwargs: object) -> structlog.PrintLogger:
        return structlog.PrintLogger(sys.stderr)


def setup_logging(level: str = "INFO", *, force: bool = False) -> None:
    global _configured  # noqa: PLW0603
    if _configured and not force:
        return

    env_level = os.environ.get("DUTY_LOG_LEVEL")
    if env_level:
        level = env_level

    resolved = getattr(logging, level.upper(), None)
    if resolved is None:
        import warnings

        warnings.warn(f"Unknown log level {level!r}, falling back to INFO", stacklevel=2)
        resolved = logging.INFO

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=resolved,
        force=True,
    )

    log_file = os.environ.get("DUTY_LOG_FILE")
    if log_file:
        file_handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=3)
        file_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                _filter_sensitive,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
            ],
        )
        file_handler.setFormatter(file_formatter)
        logging.getLogger().addHandler(file_handler)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _filter_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(resolved),
        logger_factory=_LazyStderrFactory(),
    )

    _configured = True


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
