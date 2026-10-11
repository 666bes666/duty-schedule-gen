from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
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
from duty_schedule.calendar import calendar_for_config
from duty_schedule.logging import get_logger
from duty_schedule.models import City, Config, Schedule, ShiftType
from duty_schedule.scheduler.core import generate_schedule
from duty_schedule.scheduler.postprocess.quality import eligible_duty_names
from duty_schedule.stats import EmployeeStats, build_assignments, compute_stats

logger = get_logger(__name__)

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
    return EmployeeStatsSchema(**asdict(s))


def generate_scenario(
    config: Config,
    holidays: set,
    short_days: set,
) -> tuple[list[EmployeeStatsSchema], SummaryMetrics, Schedule]:
    schedule = generate_schedule(config, holidays)
    assignments = build_assignments(schedule)
    calendar = calendar_for_config(schedule.config, holidays)
    production_days = sum(calendar.is_working(day.date) for day in calendar.days)
    raw_stats = compute_stats(schedule, assignments, production_days, short_days=short_days)
    stats_schemas = [_stats_to_schema(s) for s in raw_stats]
    summary = compute_summary(raw_stats, schedule)
    return stats_schemas, summary, schedule


def _target_hours(stat: EmployeeStats | EmployeeStatsSchema) -> int:
    if stat.calendar_hours > 0 or stat.selected_hours > 0:
        return stat.selected_hours
    return stat.target * 8


def compute_summary(stats: list[EmployeeStats], schedule: Schedule) -> SummaryMetrics:
    employees = {employee.name: employee for employee in schedule.config.employees}
    duty_stats = [
        stat
        for stat in stats
        if stat.name in employees and employees[stat.name].on_duty and _target_hours(stat) > 0
    ]
    fairness = 0.0
    calendar = calendar_for_config(schedule.config)
    dates = [record.date for record in calendar.days]
    for city, field, shift in (
        (City.MOSCOW, "evening", ShiftType.EVENING),
        (City.KHABAROVSK, "night", ShiftType.NIGHT),
    ):
        eligible = eligible_duty_names(schedule.config, calendar, dates, (shift,))
        pool = [
            stat
            for stat in duty_stats
            if employees[stat.name].city == city and stat.name in eligible
        ]
        rates = [getattr(stat, field) / _target_hours(stat) for stat in pool]
        if len(rates) > 1:
            fairness += statistics.pstdev(rates)
    weekend_balance = 0.0
    off_eligible = eligible_duty_names(
        schedule.config,
        calendar,
        sorted(calendar.off_dates()),
        (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT),
    )
    for city in City:
        rates = [
            stat.weekend_work / _target_hours(stat)
            for stat in duty_stats
            if employees[stat.name].city == city and stat.name in off_eligible
        ]
        if len(rates) > 1:
            weekend_balance += statistics.pstdev(rates)
    deviations = [stat.total_hours - _target_hours(stat) for stat in stats]
    return SummaryMetrics(
        fairness_score=round(fairness, 4),
        workload_stddev=round(statistics.pstdev(deviations), 4) if len(deviations) > 1 else 0.0,
        coverage_gaps=sum(1 for day in schedule.days if not day.is_covered()),
        isolated_off_total=sum(stat.isolated_off for stat in stats),
        weekend_balance_stddev=round(weekend_balance, 4),
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
        "sick_leave",
        "calendar_hours",
        "adjusted_hours",
        "selected_hours",
        "hours_delta",
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

            if field == "total_hours":
                b_dev = abs(b_val - _target_hours(b))
                v_dev = abs(v_val - _target_hours(v))
                direction = (
                    "improved" if v_dev < b_dev else "worsened" if v_dev > b_dev else "unchanged"
                )
            elif field == "total_working":
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
    baseline_result = ScenarioResult(
        stats=baseline_stats,
        summary=baseline_summary,
        status=baseline_schedule.status,
        diagnostics=baseline_schedule.diagnostics,
        schedule=baseline_schedule,
    )
    baseline_targets = {s.name: s.target for s in baseline_stats}

    variant_results: list[VariantResult] = []

    def _run_variant(name: str, patch: dict[str, Any]) -> VariantResult:
        try:
            variant_config = apply_patch(baseline_config, patch)
        except (ValidationError, ValueError) as exc:
            logger.warning("whatif_variant_patch_error", variant=name, error=str(exc))
            return VariantResult(name=name, status="error", error=str(exc))

        try:
            v_stats, v_summary, v_schedule = generate_scenario(variant_config, holidays, short_days)
        except Exception as exc:
            logger.warning("whatif_variant_generation_error", variant=name, error=str(exc))
            return VariantResult(name=name, status="error", error="Не удалось построить вариант")

        variant_targets = {s.name: s.target for s in v_stats}
        deltas = compute_deltas(baseline_stats, v_stats, baseline_targets, variant_targets)
        return VariantResult(
            name=name,
            status="success" if v_schedule.status == "ready" else "diagnostic",
            diagnostics=v_schedule.diagnostics,
            schedule=v_schedule,
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
