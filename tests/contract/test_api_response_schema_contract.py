from __future__ import annotations

import re

import pytest

from tests.contract.conftest import (
    JSON_HEADERS,
    config_payload,
    patch_holidays_holidays,
    patch_schedule_holidays,
    patch_whatif_holidays,
)

CONFIG_VALIDATE_FIELDS = {"valid", "errors", "warnings"}
HOLIDAYS_FIELDS = {"year", "month", "holidays", "short_days"}
SCHEDULE_TOP_FIELDS = {"config", "days", "metadata"}
DAY_SCHEDULE_FIELDS = {
    "date",
    "is_holiday",
    "morning",
    "evening",
    "night",
    "workday",
    "day_off",
    "vacation",
}
EMPLOYEE_STATS_FIELDS = {
    "name",
    "city",
    "total_working",
    "target",
    "morning",
    "evening",
    "night",
    "workday",
    "day_off",
    "vacation",
    "weekend_work",
    "holiday_work",
    "max_streak_work",
    "max_streak_rest",
    "isolated_off",
    "paired_off",
    "total_hours",
}
SUMMARY_FIELDS = {
    "fairness_score",
    "workload_stddev",
    "coverage_gaps",
    "isolated_off_total",
    "weekend_balance_stddev",
}
VARIANT_FIELDS = {"name", "status", "error", "stats", "summary", "deltas"}
EMPLOYEE_DELTA_FIELDS = {"name", "metrics"}
METRIC_DELTA_FIELDS = {"baseline", "variant", "delta", "direction"}
WHATIF_TOP_FIELDS = {"baseline", "variants"}
SCENARIO_RESULT_FIELDS = {"stats", "summary"}

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TestConfigValidateSchema:
    @pytest.mark.asyncio
    async def test_field_set(self, client) -> None:
        resp = await client.post(
            "/api/v1/config/validate",
            json=config_payload(),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        assert set(resp.json().keys()) == CONFIG_VALIDATE_FIELDS

    @pytest.mark.asyncio
    async def test_types(self, client) -> None:
        resp = await client.post(
            "/api/v1/config/validate",
            json=config_payload(),
            headers=JSON_HEADERS,
        )
        body = resp.json()
        assert isinstance(body["valid"], bool)
        assert isinstance(body["errors"], list)
        assert isinstance(body["warnings"], list)


class TestHolidaysSchema:
    @pytest.mark.asyncio
    async def test_field_set(self, client) -> None:
        with patch_holidays_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        assert resp.status_code == 200
        assert set(resp.json().keys()) == HOLIDAYS_FIELDS

    @pytest.mark.asyncio
    async def test_types(self, client) -> None:
        with patch_holidays_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        body = resp.json()
        assert isinstance(body["year"], int)
        assert isinstance(body["month"], int)
        assert isinstance(body["holidays"], list)
        assert isinstance(body["short_days"], list)

    @pytest.mark.asyncio
    async def test_date_iso_format(self, client) -> None:
        with patch_holidays_holidays():
            resp = await client.get("/api/v1/holidays/2025/3")
        body = resp.json()
        for d in body["holidays"]:
            assert ISO_DATE_RE.match(d), f"Not ISO date: {d}"
        for d in body["short_days"]:
            assert ISO_DATE_RE.match(d), f"Not ISO date: {d}"


class TestScheduleGenerateSchema:
    @pytest.mark.asyncio
    async def test_top_level_fields(self, client) -> None:
        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert set(resp.json().keys()) == SCHEDULE_TOP_FIELDS

    @pytest.mark.asyncio
    async def test_day_fields(self, client) -> None:
        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        body = resp.json()
        assert len(body["days"]) > 0
        for day in body["days"]:
            assert set(day.keys()) == DAY_SCHEDULE_FIELDS

    @pytest.mark.asyncio
    async def test_day_field_types(self, client) -> None:
        with patch_schedule_holidays():
            resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        day = resp.json()["days"][0]
        assert isinstance(day["date"], str)
        assert ISO_DATE_RE.match(day["date"])
        assert isinstance(day["is_holiday"], bool)
        for shift in ("morning", "evening", "night", "workday", "day_off", "vacation"):
            assert isinstance(day[shift], list)


class TestScheduleStatsSchema:
    @pytest.mark.asyncio
    async def test_is_list(self, client) -> None:
        with patch_schedule_holidays():
            gen_resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        schedule = gen_resp.json()
        resp = await client.post(
            "/api/v1/schedule/stats",
            json=schedule,
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_employee_fields(self, client) -> None:
        with patch_schedule_holidays():
            gen_resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        schedule = gen_resp.json()
        resp = await client.post(
            "/api/v1/schedule/stats",
            json=schedule,
            headers=JSON_HEADERS,
        )
        body = resp.json()
        assert len(body) == 6
        for stat in body:
            assert set(stat.keys()) == EMPLOYEE_STATS_FIELDS

    @pytest.mark.asyncio
    async def test_employee_field_types(self, client) -> None:
        with patch_schedule_holidays():
            gen_resp = await client.post(
                "/api/v1/schedule/generate",
                json=config_payload(),
                headers=JSON_HEADERS,
            )
        schedule = gen_resp.json()
        resp = await client.post(
            "/api/v1/schedule/stats",
            json=schedule,
            headers=JSON_HEADERS,
        )
        stat = resp.json()[0]
        assert isinstance(stat["name"], str)
        assert isinstance(stat["city"], str)
        for field in EMPLOYEE_STATS_FIELDS - {"name", "city"}:
            assert isinstance(stat[field], int), f"{field} should be int"


class TestWhatIfSchema:
    def _whatif_body(self) -> dict:
        return {
            "baseline": config_payload(),
            "variants": [{"name": "seed=99", "patch": {"seed": 99}}],
        }

    @pytest.mark.asyncio
    async def test_top_level_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 200
        assert set(resp.json().keys()) == WHATIF_TOP_FIELDS

    @pytest.mark.asyncio
    async def test_baseline_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        baseline = resp.json()["baseline"]
        assert set(baseline.keys()) == SCENARIO_RESULT_FIELDS

    @pytest.mark.asyncio
    async def test_summary_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        summary = resp.json()["baseline"]["summary"]
        assert set(summary.keys()) == SUMMARY_FIELDS

    @pytest.mark.asyncio
    async def test_summary_types(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        summary = resp.json()["baseline"]["summary"]
        assert isinstance(summary["fairness_score"], (int, float))
        assert isinstance(summary["workload_stddev"], (int, float))
        assert isinstance(summary["coverage_gaps"], int)
        assert isinstance(summary["isolated_off_total"], int)
        assert isinstance(summary["weekend_balance_stddev"], (int, float))

    @pytest.mark.asyncio
    async def test_variant_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        variant = resp.json()["variants"][0]
        assert set(variant.keys()) == VARIANT_FIELDS

    @pytest.mark.asyncio
    async def test_variant_success_has_deltas(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        variant = resp.json()["variants"][0]
        assert variant["status"] == "success"
        assert isinstance(variant["deltas"], list)
        assert len(variant["deltas"]) > 0

    @pytest.mark.asyncio
    async def test_delta_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        delta = resp.json()["variants"][0]["deltas"][0]
        assert set(delta.keys()) == EMPLOYEE_DELTA_FIELDS
        assert isinstance(delta["name"], str)
        assert isinstance(delta["metrics"], dict)

    @pytest.mark.asyncio
    async def test_metric_delta_fields(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        delta = resp.json()["variants"][0]["deltas"][0]
        metric = next(iter(delta["metrics"].values()))
        assert set(metric.keys()) == METRIC_DELTA_FIELDS
        assert isinstance(metric["baseline"], int)
        assert isinstance(metric["variant"], int)
        assert isinstance(metric["delta"], int)
        assert isinstance(metric["direction"], str)

    @pytest.mark.asyncio
    async def test_baseline_stats_match_employee_schema(self, client) -> None:
        with patch_whatif_holidays():
            resp = await client.post(
                "/api/v1/whatif/compare",
                json=self._whatif_body(),
                headers=JSON_HEADERS,
            )
        stats = resp.json()["baseline"]["stats"]
        assert len(stats) == 6
        for stat in stats:
            assert set(stat.keys()) == EMPLOYEE_STATS_FIELDS
