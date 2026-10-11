from unittest.mock import patch

import pytest

from tests.contract.conftest import config_payload


@pytest.mark.asyncio
async def test_blank_employee_is_rejected_before_generation(client):
    data = config_payload()
    data["employees"][0]["name"] = " "
    with patch("duty_schedule.api.planning.generate_schedule") as search:
        response = await client.post("/api/v1/schedule/plan", json=data)
    assert response.status_code == 422
    search.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [{"solverr": "cpsat"}, {"employees": [{"name": "M", "typo": True}]}]
)
async def test_unknown_nested_patch_is_422_without_search(client, change):
    with patch("duty_schedule.api.routes.whatif.run_whatif") as search:
        response = await client.post(
            "/api/v1/whatif/compare",
            json={"baseline": config_payload(), "variants": [{"name": "typo", "patch": change}]},
        )
    assert response.status_code == 422
    assert ("solverr" if "solverr" in change else "employees.0.typo") in response.text
    search.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/config/validate", "/schedule/plan"])
async def test_mismatched_calendar_is_422_without_search_or_network(client, route):
    data = config_payload()
    data["month"] = 4
    with (
        patch("duty_schedule.api.planning.generate_schedule") as search,
        patch("duty_schedule.api.planning.fetch_production_calendar") as network,
    ):
        response = await client.post("/api/v1" + route, json=data)
    assert response.status_code == 422
    search.assert_not_called()
    network.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [{"employees": "wrong-type"}, {"production_calendar": {"year": 2025, "month": 4, "days": []}}],
)
async def test_invalid_merged_patch_is_422_before_baseline_search(client, change):
    with (
        patch("duty_schedule.api.routes.whatif.run_whatif") as search,
        patch("duty_schedule.api.routes.whatif.fetch_production_calendar") as network,
    ):
        response = await client.post(
            "/api/v1/whatif/compare",
            json={"baseline": config_payload(), "variants": [{"name": "invalid", "patch": change}]},
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:4] == ["body", "variants", 0, "patch"]
    search.assert_not_called()
    network.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["snapshot", "day", "target", "diagnostic"])
async def test_unknown_previous_snapshot_fields_are_422_before_search(client, location):
    from duty_schedule.models import Schedule
    from tests.ui.fixtures import journey_config, journey_days

    config = journey_config()
    previous = Schedule(config=config, days=journey_days(config)).model_dump(mode="json")
    if location == "snapshot":
        previous["typo"] = True
    elif location == "day":
        previous["days"][0]["typo"] = True
    elif location == "target":
        previous["monthly_targets"] = {
            "M0": {
                "calendar_hours": 1,
                "absence_reduction_hours": 0,
                "adjusted_hours": 1,
                "selected_hours": 1,
                "typo": True,
            }
        }
    else:
        previous["diagnostics"] = [{"code": "test", "detail": "test", "typo": True}]
    data = config_payload()
    data["previous_schedule"] = previous
    with patch("duty_schedule.api.planning.generate_schedule") as search:
        response = await client.post("/api/v1/schedule/plan", json=data)
    assert response.status_code == 422
    assert "typo" in response.text
    search.assert_not_called()
