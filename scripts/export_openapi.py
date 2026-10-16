from __future__ import annotations

import json
from pathlib import Path

from duty_schedule.api import create_app
from duty_schedule.api.settings import ApiSettings, get_settings

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "specs" / "000-baseline" / "contracts" / "openapi.json"
)


def main() -> None:
    application = create_app()
    settings = ApiSettings(auth_enabled=True, keys="", rate_limit="60/minute")
    application.dependency_overrides[get_settings] = lambda: settings
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(application.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
