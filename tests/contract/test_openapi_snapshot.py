from __future__ import annotations

import json
from pathlib import Path

from duty_schedule.api import create_app
from duty_schedule.api.settings import ApiSettings, get_settings

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2] / "specs" / "000-baseline" / "contracts" / "openapi.json"
)


def test_openapi_matches_baseline() -> None:
    application = create_app()
    settings = ApiSettings(auth_enabled=True, keys="", rate_limit="60/minute")
    application.dependency_overrides[get_settings] = lambda: settings
    expected = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert application.openapi() == expected, (
        "OpenAPI differs from the SDD baseline. Review the API specification and intended "
        "contract change, then regenerate with: uv run python scripts/export_openapi.py"
    )
