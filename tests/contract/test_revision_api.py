from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.api.settings import ApiSettings, get_settings
from duty_schedule.models import Config, Schedule
from tests.contract.conftest import config_payload


@pytest.mark.asyncio
async def test_control_characters_in_employee_name_export_as_escaped_calendar_text(client):
    from io import BytesIO
    from zipfile import ZipFile

    from icalendar import Calendar

    from duty_schedule.scheduler import generate_schedule

    payload = config_payload()
    config = Config.model_validate(payload)
    old_name = config.employees[0].name
    name = 'A"\r\nInjected: true,;'
    config.employees[0].name = name
    for carry in config.carry_over:
        if carry.employee_name == old_name:
            carry.employee_name = name
    schedule = generate_schedule(config)
    assert schedule.status == "ready"
    body = schedule.model_dump(mode="json")
    single = await client.post(
        "/api/v1/export/revision/ics", json=body, params={"employee_name": name}
    )
    assert single.status_code == 200
    cal = Calendar.from_ical(single.content)
    assert "Injected" not in cal
    assert str(cal["X-WR-CALNAME"]) == f"Расписание: {name.replace(chr(13), '')}"
    archive = await client.post("/api/v1/export/revision/ics", json=body)
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as zip_file:
        assert len(zip_file.namelist()) == len(config.employees)
        for path in zip_file.namelist():
            assert not any(ord(character) < 32 for character in path)
            Calendar.from_ical(zip_file.read(path))


@pytest.mark.asyncio
async def test_bad_range_is_native_422_before_generation() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: ApiSettings(auth_enabled=False)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        invalid_requests = [
            {
                "config": {},
                "start_month": 1,
                "start_year": 2026,
                "end_month": 2,
                "end_year": 2026,
            },
            {
                "config": config_payload(),
                "start_month": 2,
                "start_year": 2026,
                "end_month": 1,
                "end_year": 2026,
            },
        ]
        for body in invalid_requests:
            response = await client.post("/api/v1/schedule/generate-range", json=body)
            assert response.status_code == 422
            assert isinstance(response.json()["detail"], list)


@pytest.mark.asyncio
async def test_unknown_employee_quotes_and_newline_produce_json(client) -> None:
    response = await client.post(
        "/api/v1/export/ics",
        params={"employee_name": 'Unknown "quoted"\nname'},
        json=config_payload(),
    )
    assert response.status_code == 400
    assert response.json()["error"] == "schedule_error"
    assert 'Unknown "quoted"\nname' in response.json()["detail"]


@pytest.mark.asyncio
async def test_plan_returns_diagnostics_but_legacy_generate_rejects_them(client) -> None:
    payload = config_payload()
    schedule = Schedule(config=Config.model_validate(payload), days=[])
    with patch("duty_schedule.api.routes.schedule.generate_schedule", return_value=schedule):
        plan = await client.post("/api/v1/schedule/plan", json=payload)
        generated = await client.post("/api/v1/schedule/generate", json=payload)
    assert plan.status_code == 200
    assert plan.json()["status"] == "diagnostic"
    assert plan.json()["diagnostics"]
    assert generated.status_code == 409
    assert generated.json()["error"] == "schedule_not_ready"


@pytest.mark.asyncio
async def test_forged_ready_schedule_cannot_be_exported(client) -> None:
    schedule = Schedule(config=Config.model_validate(config_payload()), days=[])
    body = schedule.model_dump(mode="json")
    body["status"] = "ready"
    for export_format in ("xls", "pdf", "ics"):
        response = await client.post(f"/api/v1/export/revision/{export_format}", json=body)
        assert response.status_code == 409
        assert response.json()["error"] == "schedule_not_ready"


def test_binary_export_media_types_are_documented() -> None:
    schema = create_app().openapi()
    for endpoint, expected in (
        ("xls", {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
        ("pdf", {"application/pdf"}),
        ("ics", {"text/calendar", "application/zip"}),
    ):
        for prefix in ("/api/v1/export/", "/api/v1/export/revision/"):
            operation = schema["paths"][prefix + endpoint]["post"]
            assert set(operation["responses"]["200"]["content"]) == expected
            assert "Content-Disposition" in operation["responses"]["200"]["headers"]
            assert "409" in operation["responses"]
