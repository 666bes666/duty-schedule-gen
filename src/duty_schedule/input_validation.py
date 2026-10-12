from __future__ import annotations

import copy
import warnings
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from duty_schedule.models import Config


def validate_patch(patch: dict[str, Any]) -> dict[str, Any]:
    def check(value: Any, annotation: Any, path: str) -> None:
        if get_origin(annotation) is list and isinstance(value, list):
            for index, item in enumerate(value):
                check(item, get_args(annotation)[0], f"{path}.{index}")
        elif get_origin(annotation) is dict and isinstance(value, dict):
            for key, item in value.items():
                check(item, get_args(annotation)[1], f"{path}.{key}")
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if isinstance(value, dict):
                for key, item in value.items():
                    full = f"{path}.{key}" if path else key
                    if key not in annotation.model_fields:
                        raise ValueError(f"Неизвестный путь: {full}")
                    check(item, annotation.model_fields[key].annotation, full)
        else:
            for candidate in get_args(annotation):
                check(value, candidate, path)

    forbidden = {"year", "month"} & patch.keys()
    if forbidden:
        raise ValueError(f"Изменение {', '.join(sorted(forbidden))} в варианте запрещено")
    check(patch, Config, "")
    return patch


def migrate_legacy_config(raw: Any) -> Any:
    data = copy.deepcopy(raw)
    if isinstance(data, dict):
        for index, employee in enumerate(data.get("employees", [])):
            if isinstance(employee, dict) and "team_lead" in employee:
                value = employee.pop("team_lead")
                warnings.warn(
                    f"employees.{index}.team_lead={value!r}: устаревшее поле не поддерживается",
                    UserWarning,
                    stacklevel=2,
                )
    return data
