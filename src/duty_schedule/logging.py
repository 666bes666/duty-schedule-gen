"""Настройка структурированного логирования."""

from __future__ import annotations

import logging
import sys

import structlog


class _LazyStderrFactory:
    """Фабрика логгеров, которая использует актуальный sys.stderr при каждом вызове."""

    def __call__(self, *args: object, **kwargs: object) -> structlog.PrintLogger:
        return structlog.PrintLogger(sys.stderr)


def setup_logging(level: str = "INFO") -> None:
    """Инициализировать structlog с JSON-выводом."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=_LazyStderrFactory(),
    )


def get_logger() -> structlog.BoundLogger:
    return structlog.get_logger()
