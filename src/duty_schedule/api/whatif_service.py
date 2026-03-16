from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pydantic import ValidationError

from duty_schedule.api.schemas import (
    EmployeeDelta,
    EmployeeStatsSchema,
    MetricDelta,
    ScenarioResult,
    SummaryMetrics,
    VariantResult,
    WhatIfResponse,
)
from duty_schedule.models import Config, Schedule
from duty_schedule.scheduler.constraints import _calc_production_days
from duty_schedule.scheduler.core import ScheduleError, generate_schedule
from duty_schedule.stats import EmployeeStats, build_assignments, compute_stats

NEUTRAL_METRICS = {
    "morning",
    "evening",
    "night",
    "workday",
    "day_off",
    "vacation",
    "weekend_work",
    "holiday_work",
    "total_hours",
    "max_streak_rest",
}

LOWER_IS_BETTER = {"isolated_off", "max_streak_work"}
HIGHER_IS_BETTER = {"paired_off"}


def apply_patch(baseline: Config, patch: dict[str, Any]) -> Config:
    merged = {**baseline.model_dump(), **patch}
    return Config.model_validate(merged)


def _stats_to_schema(s: EmployeeStats) -> EmployeeStatsSchema:
    return EmployeeStatsSchema(
        name=s.name,
        city=s.city,
        total_working=s.total_working,
        target=s.target,
        morning=s.morning,
        evening=s.evening,
        night=s.night,
        workday=s.workday,
        day_off=s.day_off,
        vacation=s.vacation,
        weekend_work=s.weekend_work,
        holiday_work=s.holiday_work,
        max_streak_work=s.max_streak_work,
        max_streak_rest=s.max_streak_rest,
        isolated_off=s.isolated_off,
        paired_off=s.paired_off,
        total_hours=s.total_hours,
    )


def generate_scenario(
    config: Config,
    holidays: set,
    short_days: set,
) -> tuple[list[EmployeeStatsSchema], SummaryMetrics, Schedule]:
    schedule = generate_schedule(config, holidays)
    assignments = build_assignments(schedule)
    production_days = _calc_production_days(config.year, config.month, holidays)
    raw_stats = compute_stats(schedule, assignments, production_days, short_days=short_days)
    stats_schemas = [_stats_to_schema(s) for s in raw_stats]
    summary = compute_summary(raw_stats, schedule)
    return stats_schemas, summary, schedule


def compute_summary(stats: list[EmployeeStats], schedule: Schedule) -> SummaryMetrics:
    duty_stats = [s for s in stats if s.total_working > 0 or s.target > 0]

    if not duty_stats:
        return SummaryMetrics(
            fairness_score=0.0,
            workload_stddev=0.0,
            coverage_gaps=0,
            isolated_off_total=0,
            weekend_balance_stddev=0.0,
        )

    deviations = [s.total_working - s.target for s in duty_stats]
    fairness_score = statistics.pstdev(deviations) if len(deviations) > 1 else 0.0

    workloads = [s.total_working for s in duty_stats]
    workload_stddev = statistics.pstdev(workloads) if len(workloads) > 1 else 0.0

    coverage_gaps = sum(1 for day in schedule.days if not day.is_covered())

    isolated_off_total = sum(s.isolated_off for s in duty_stats)

    weekends = [s.weekend_work for s in duty_stats]
    weekend_balance_stddev = statistics.pstdev(weekends) if len(weekends) > 1 else 0.0

    return SummaryMetrics(
        fairness_score=round(fairness_score, 4),
        workload_stddev=round(workload_stddev, 4),
        coverage_gaps=coverage_gaps,
        isolated_off_total=isolated_off_total,
        weekend_balance_stddev=round(weekend_balance_stddev, 4),
    )


def _direction_for(metric: str, delta: int, baseline_val: int, variant_val: int) -> str:
    if delta == 0:
        return "unchanged"

    if metric == "total_working":
        return "improved" if abs(variant_val) < abs(baseline_val) else "worsened"

    if metric in LOWER_IS_BETTER:
        return "improved" if delta < 0 else "worsened"

    if metric in HIGHER_IS_BETTER:
        return "improved" if delta > 0 else "worsened"

    return "changed"


def compute_deltas(
    baseline_stats: list[EmployeeStatsSchema],
    variant_stats: list[EmployeeStatsSchema],
    baseline_targets: dict[str, int] | None = None,
    variant_targets: dict[str, int] | None = None,
) -> list[EmployeeDelta]:
    baseline_map = {s.name: s for s in baseline_stats}
    variant_map = {s.name: s for s in variant_stats}
    common = sorted(set(baseline_map) & set(variant_map))

    _b_targets = baseline_targets or {}
    _v_targets = variant_targets or {}

    metric_fields = [
        "total_working",
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
    ]

    result = []
    for name in common:
        b = baseline_map[name]
        v = variant_map[name]
        metrics: dict[str, MetricDelta] = {}
        for field in metric_fields:
            b_val = getattr(b, field)
            v_val = getattr(v, field)
            delta = v_val - b_val

            if field == "total_working":
                b_target = _b_targets.get(name, b.target)
                v_target = _v_targets.get(name, v.target)
                b_dev = abs(b_val - b_target)
                v_dev = abs(v_val - v_target)
                if v_dev < b_dev:
                    direction = "improved"
                elif v_dev > b_dev:
                    direction = "worsened"
                else:
                    direction = "unchanged"
            else:
                direction = _direction_for(field, delta, b_val, v_val)

            metrics[field] = MetricDelta(
                baseline=b_val,
                variant=v_val,
                delta=delta,
                direction=direction,
            )
        result.append(EmployeeDelta(name=name, metrics=metrics))
    return result


def run_whatif(
    baseline_config: Config,
    variant_patches: list[tuple[str, dict[str, Any]]],
    holidays: set,
    short_days: set,
) -> WhatIfResponse:
    baseline_stats, baseline_summary, baseline_schedule = generate_scenario(
        baseline_config, holidays, short_days
    )
    baseline_result = ScenarioResult(stats=baseline_stats, summary=baseline_summary)
    baseline_targets = {s.name: s.target for s in baseline_stats}

    variant_results: list[VariantResult] = []

    def _run_variant(name: str, patch: dict[str, Any]) -> VariantResult:
        try:
            variant_config = apply_patch(baseline_config, patch)
        except (ValidationError, ValueError) as exc:
            return VariantResult(name=name, status="error", error=str(exc))

        try:
            v_stats, v_summary, _ = generate_scenario(variant_config, holidays, short_days)
        except (ScheduleError, Exception) as exc:
            return VariantResult(name=name, status="error", error=str(exc))

        variant_targets = {s.name: s.target for s in v_stats}
        deltas = compute_deltas(baseline_stats, v_stats, baseline_targets, variant_targets)
        return VariantResult(
            name=name,
            status="success",
            stats=v_stats,
            summary=v_summary,
            deltas=deltas,
        )

    with ThreadPoolExecutor(max_workers=min(len(variant_patches), 5)) as executor:
        futures = {
            executor.submit(_run_variant, name, patch): idx
            for idx, (name, patch) in enumerate(variant_patches)
        }
        indexed_results: dict[int, VariantResult] = {}
        for future in as_completed(futures):
            idx = futures[future]
            indexed_results[idx] = future.result()

    variant_results = [indexed_results[i] for i in range(len(variant_patches))]

    return WhatIfResponse(baseline=baseline_result, variants=variant_results)
