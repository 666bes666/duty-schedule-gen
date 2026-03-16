from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from duty_schedule.api import create_app
from duty_schedule.api.ratelimit import SlidingWindowRateLimiter, get_limiter
from duty_schedule.api.settings import ApiSettings, get_settings
from duty_schedule.models import City, Config, Employee, ScheduleType

SAMPLE_HOLIDAYS: set[date] = {date(2025, 3, 8), date(2025, 3, 10)}
SAMPLE_SHORT_DAYS: set[date] = {date(2025, 3, 7)}
JSON_HEADERS = {"Content-Type": "application/json"}


def _emp(
    name: str,
    city: City = City.MOSCOW,
    schedule_type: ScheduleType = ScheduleType.FLEXIBLE,
) -> Employee:
    return Employee(name=name, city=city, schedule_type=schedule_type)


def config_payload() -> dict:
    cfg = Config(
        month=3,
        year=2025,
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
    return cfg.model_dump(mode="json")


def patch_schedule_holidays():
    return patch(
        "duty_schedule.api.routes.schedule.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


def patch_whatif_holidays():
    return patch(
        "duty_schedule.api.routes.whatif.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


def patch_holidays_holidays():
    return patch(
        "duty_schedule.api.routes.holidays.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


def patch_export_holidays():
    return patch(
        "duty_schedule.api.routes.export.fetch_holidays",
        return_value=(SAMPLE_HOLIDAYS, SAMPLE_SHORT_DAYS),
    )


@pytest.fixture
def app():
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: ApiSettings(auth_enabled=False)
    return application


@pytest.fixture
def app_with_auth():
    application = create_app()
    limiter = SlidingWindowRateLimiter()
    application.dependency_overrides[get_settings] = lambda: ApiSettings(
        auth_enabled=True, keys="test-key-123", rate_limit="2/minute"
    )
    application.dependency_overrides[get_limiter] = lambda: limiter
    return application


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def client_with_auth(app_with_auth):
    transport = ASGITransport(app=app_with_auth)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": "test-key-123"},
    ) as ac:
        yield ac
