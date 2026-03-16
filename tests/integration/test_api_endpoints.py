from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.api.settings import ApiSettings, get_settings
from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler import generate_schedule

JSON_HEADERS = {"Content-Type": "application/json"}


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
) -> Employee:
    return Employee(name=name, city=city, schedule_type=schedule_type)


def _make_config(month: int = 3, year: int = 2025) -> Config:
    return Config(
        month=month,
        year=year,
        seed=42,
        employees=[
            _emp("Иванов Иван"),
            _emp("Петров Пётр"),
            _emp("Сидоров Сидор"),
            _emp("Козлов Коля"),
            _emp("Дальнев Дмитрий", City.KHABAROVSK),
            _emp("Востоков Виктор", City.KHABAROVSK),
        ],
    )


SAMPLE_HOLIDAYS: set[date] = {date(2025, 3, 8), date(2025, 3, 10)}
SAMPLE_SHORT_DAYS: set[date] = {date(2025, 3, 7)}


@pytest.fixture
def app():
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: ApiSettings(auth_enabled=False)
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _patch_fetch():
    return patch(
        "duty_schedule.api.routes.schedule.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


def _patch_fetch_holidays():
    return patch(
        "duty_schedule.api.routes.holidays.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


def _patch_export_fetch():
    return patch(
        "duty_schedule.api.routes.export.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


class TestConfigValidate:
    @pytest.mark.asyncio
    async def test_valid_config(self, client) -> None:
        config = _make_config()
        resp = await client.post(
            "/api/v1/config/validate",
            content=config.model_dump_json(),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["errors"] == []

    @pytest.mark.asyncio
    async def test_invalid_json_returns_422(self, client) -> None:
        resp = await client.post(
            "/api/v1/config/validate",
            json={"month": 13, "year": 2025, "employees": []},
        )
        assert resp.status_code == 422


class TestHolidays:
    @pytest.mark.asyncio
    async def test_get_holidays(self, client) -> None:
        with _patch_fetch_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["year"] == 2025
        assert body["month"] == 3
        assert len(body["holidays"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_month_returns_422(self, client) -> None:
        resp = await client.get("/api/v1/holidays/2025/13")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_calendar_error_returns_502(self, client) -> None:
        from duty_schedule.calendar import CalendarError

        with patch(
            "duty_schedule.api.routes.holidays.fetch_holidays",
            side_effect=CalendarError("service down"),
        ):
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 502
        assert resp.json()["error"] == "calendar_error"


class TestScheduleGenerate:
    @pytest.mark.asyncio
    async def test_generate_schedule(self, client) -> None:
        config = _make_config()
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/schedule/generate",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "days" in body
        assert len(body["days"]) == 31

    @pytest.mark.asyncio
    async def test_generate_invalid_config_returns_422(self, client) -> None:
        resp = await client.post(
            "/api/v1/schedule/generate",
            json={"month": 3, "year": 2025, "employees": []},
        )
        assert resp.status_code == 422


class TestScheduleStats:
    @pytest.mark.asyncio
    async def test_stats(self, client) -> None:
        config = _make_config()
        schedule = generate_schedule(config, SAMPLE_HOLIDAYS)
        resp = await client.post(
            "/api/v1/schedule/stats",
            content=schedule.model_dump_json(),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 6
        assert all("name" in s for s in body)
        assert all("total_hours" in s for s in body)


class TestExportXls:
    @pytest.mark.asyncio
    async def test_export_xls(self, client) -> None:
        config = _make_config()
        with _patch_export_fetch():
            resp = await client.post(
                "/api/v1/export/xls",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert ".xlsx" in resp.headers["content-disposition"]
        assert len(resp.content) > 0


class TestExportIcs:
    @pytest.mark.asyncio
    async def test_export_ics_single_employee(self, client) -> None:
        config = _make_config()
        with _patch_export_fetch():
            resp = await client.post(
                "/api/v1/export/ics?employee_name=Иванов Иван",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert "text/calendar" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_export_ics_all_employees_zip(self, client) -> None:
        config = _make_config()
        with _patch_export_fetch():
            resp = await client.post(
                "/api/v1/export/ics",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    @pytest.mark.asyncio
    async def test_export_ics_unknown_employee(self, client) -> None:
        config = _make_config()
        with _patch_export_fetch():
            resp = await client.post(
                "/api/v1/export/ics?employee_name=Неизвестный",
                content=config.model_dump_json(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400
