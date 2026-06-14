from __future__ import annotations

from pydantic import ValidationError

_VALUE_ERROR_PREFIX = "Value error, "


def format_validation_errors(exc: ValidationError) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        msg = str(err.get("msg", "")).strip()
        if msg.startswith(_VALUE_ERROR_PREFIX):
            msg = msg[len(_VALUE_ERROR_PREFIX) :]
        messages.append(msg)
    return messages
