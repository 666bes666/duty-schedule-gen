from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.api.settings import ApiSettings, get_settings
from duty_schedule.models import City, Employee, ScheduleType

JSON_HEADERS = {"Content-Type": "application/json"}

SAMPLE_HOLIDAYS: set[date] = {date(2025, 3, 8), date(2025, 3, 10)}
SAMPLE_SHORT_DAYS: set[date] = {date(2025, 3, 7)}


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
) -> dict:
    return Employee(name=name, city=city, schedule_type=schedule_type).model_dump()


def _baseline() -> dict:
    return {
        "month": 3,
        "year": 2025,
        "seed": 42,
        "employees": [
            _emp("Иванов Иван"),
            _emp("Петров Пётр"),
            _emp("Сидоров Сидор"),
            _emp("Козлов Коля"),
            _emp("Дальнев Дмитрий", City.KHABAROVSK),
            _emp("Востоков Виктор", City.KHABAROVSK),
        ],
    }


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
        "duty_schedule.api.routes.whatif.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


class TestWhatIfCompare:
    @pytest.mark.asyncio
    async def test_success_one_variant(self, client) -> None:
        body = {
            "baseline": _baseline(),
            "variants": [{"name": "seed=99", "patch": {"seed": 99}}],
        }
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "baseline" in data
        assert len(data["baseline"]["stats"]) == 6
        assert data["baseline"]["summary"]["coverage_gaps"] >= 0
        assert len(data["variants"]) == 1
        v = data["variants"][0]
        assert v["status"] == "success"
        assert v["stats"] is not None
        assert v["deltas"] is not None
        assert v["summary"] is not None

    @pytest.mark.asyncio
    async def test_too_many_variants_422(self, client) -> None:
        body = {
            "baseline": _baseline(),
            "variants": [{"name": f"v{i}", "patch": {"seed": i}} for i in range(6)],
        }
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_zero_variants_422(self, client) -> None:
        body = {
            "baseline": _baseline(),
            "variants": [],
        }
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_baseline_400(self, client) -> None:
        body = {
            "baseline": {"month": 3, "year": 2025, "employees": []},
            "variants": [{"name": "x", "patch": {"seed": 1}}],
        }
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_partial_failure_variant(self, client) -> None:
        bad_employees = [_emp("Один Один")]
        body = {
            "baseline": _baseline(),
            "variants": [
                {"name": "good", "patch": {"seed": 99}},
                {"name": "bad", "patch": {"employees": bad_employees}},
            ],
        }
        with _patch_fetch():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        statuses = {v["name"]: v["status"] for v in data["variants"]}
        assert statuses["good"] == "success"
        assert statuses["bad"] == "error"

    @pytest.mark.asyncio
    async def test_calendar_error_502(self, client) -> None:
        from duty_schedule.calendar import CalendarError

        body = {
            "baseline": _baseline(),
            "variants": [{"name": "x", "patch": {"seed": 1}}],
        }
        with patch(
            "duty_schedule.api.routes.whatif.fetch_holidays",
            side_effect=CalendarError("service down"),
        ):
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=body,
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 502
        assert resp.json()["error"] == "calendar_error"
