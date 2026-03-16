from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, field_validator


class ConfigValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class HolidaysResponse(BaseModel):
    year: int
    month: int
    holidays: list[date]
    short_days: list[date]


class EmployeeStatsSchema(BaseModel):
    name: str
    city: str
    total_working: int
    target: int
    morning: int
    evening: int
    night: int
    workday: int
    day_off: int
    vacation: int
    weekend_work: int
    holiday_work: int
    max_streak_work: int
    max_streak_rest: int
    isolated_off: int
    paired_off: int
    total_hours: int


class ErrorResponse(BaseModel):
    error: str
    detail: str


class VariantPatch(BaseModel):
    name: str
    patch: dict[str, Any]

    @field_validator("patch")
    @classmethod
    def forbid_month_year(cls, v: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"month", "year"} & v.keys()
        if forbidden:
            raise ValueError(f"Изменение {', '.join(sorted(forbidden))} в варианте запрещено")
        return v


class WhatIfRequest(BaseModel):
    baseline: dict[str, Any]
    variants: list[VariantPatch]

    @field_validator("variants")
    @classmethod
    def check_variants_count(cls, v: list[VariantPatch]) -> list[VariantPatch]:
        if len(v) < 1:
            raise ValueError("Необходим хотя бы один вариант")
        if len(v) > 5:
            raise ValueError("Максимум 5 вариантов")
        return v


class MetricDelta(BaseModel):
    baseline: int
    variant: int
    delta: int
    direction: str


class EmployeeDelta(BaseModel):
    name: str
    metrics: dict[str, MetricDelta]


class SummaryMetrics(BaseModel):
    fairness_score: float
    workload_stddev: float
    coverage_gaps: int
    isolated_off_total: int
    weekend_balance_stddev: float


class ScenarioResult(BaseModel):
    stats: list[EmployeeStatsSchema]
    summary: SummaryMetrics


class VariantResult(BaseModel):
    name: str
    status: str
    error: str | None = None
    stats: list[EmployeeStatsSchema] | None = None
    summary: SummaryMetrics | None = None
    deltas: list[EmployeeDelta] | None = None


class WhatIfResponse(BaseModel):
    baseline: ScenarioResult
    variants: list[VariantResult]
