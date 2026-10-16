import pytest

from tests.contract.conftest import config_payload


@pytest.mark.asyncio
async def test_standalone_api_reports_month_only_quality(client):
    response = await client.post("/api/v1/schedule/plan", json=config_payload())
    assert response.status_code == 200
    data = response.json()
    schedule = data.get("schedule", data)
    assert schedule["metadata"]["quality"]["window"] == "month_only"
    assert schedule["metadata"]["quality"]["history"] == "missing"
