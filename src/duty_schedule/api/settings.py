from __future__ import annotations

import re
from functools import lru_cache

from pydantic_settings import BaseSettings


class ApiSettings(BaseSettings):
    model_config = {"env_prefix": "DUTY_API_"}

    auth_enabled: bool = True
    keys: str = ""
    rate_limit: str = "60/minute"

    @property
    def parsed_keys(self) -> list[str]:
        if not self.keys:
            return []
        return [k.strip() for k in self.keys.split(",") if k.strip()]

    @property
    def rate_limit_max(self) -> int:
        m = re.match(r"^(\d+)/", self.rate_limit)
        if not m:
            return 60
        return int(m.group(1))

    @property
    def rate_limit_window(self) -> int:
        windows = {"second": 1, "minute": 60, "hour": 3600}
        m = re.match(r"^\d+/(\w+)$", self.rate_limit)
        if not m:
            return 60
        return windows.get(m.group(1), 60)


@lru_cache
def get_settings() -> ApiSettings:
    return ApiSettings()
