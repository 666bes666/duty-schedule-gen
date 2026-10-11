from __future__ import annotations

from fractions import Fraction
from typing import Any

from duty_schedule.calendar import calendar_for_config
from duty_schedule.models import City, Config, Schedule, ShiftType
from duty_schedule.workload import calculate_monthly_targets


def previous_quality_schedule(config: Config) -> tuple[Schedule | None, str]:
    from duty_schedule.scheduler.validation import validate_schedule_result

    if config._quality_state == "stale":
        return None, "stale"
    previous = config.previous_schedule
    if previous is None:
        return None, "missing"
    year, month = (config.year - 1, 12) if config.month == 1 else (config.year, config.month - 1)
    if (previous.config.year, previous.config.month) != (year, month):
        return None, "stale"
    checked = validate_schedule_result(previous)
    if (
        previous.status != "ready"
        or checked.status != "ready"
        or any(item.code == "previous_revision_changed" for item in previous.diagnostics)
    ):
        return None, "unverified"
    return checked, "verified"


def weighted_imbalance(counts: dict[str, int], weights: dict[str, int]) -> Fraction:
    names = [name for name, weight in weights.items() if weight > 0]
    denominator = sum(weights[name] for name in names)
    total = sum(counts.get(name, 0) for name in names)
    return sum(
        (
            abs(Fraction(counts.get(name, 0)) - Fraction(total * weights[name], denominator))
            for name in names
        ),
        start=Fraction(0),
    )


def balance_pools(config: Config, allow_pending: bool = False) -> dict[str, dict[str, Any]]:
    from duty_schedule.scheduler.postprocess.quality import eligible_duty_names

    previous, _ = previous_quality_schedule(config)
    pools: dict[str, dict[str, Any]] = {}
    for kind, shifts, city, off_only in (
        ("evening", (ShiftType.EVENING,), City.MOSCOW, False),
        ("night", (ShiftType.NIGHT,), City.KHABAROVSK, False),
        ("off_moscow", (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT), City.MOSCOW, True),
        (
            "off_khabarovsk",
            (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT),
            City.KHABAROVSK,
            True,
        ),
    ):
        weights: dict[str, int] = {}
        past_counts: dict[str, int] = {}
        current_ids = []
        for source in ([previous.config] if previous else []) + [config]:
            calendar = calendar_for_config(source)
            dates = (
                sorted(calendar.off_dates()) if off_only else [day.date for day in calendar.days]
            )
            eligible = eligible_duty_names(
                source, calendar, dates, shifts, allow_pending=allow_pending
            )
            targets = calculate_monthly_targets(source, calendar)
            for employee in source.employees:
                if employee.name not in eligible or employee.city != city:
                    continue
                hours = targets[employee.name].selected_hours
                if hours <= 0:
                    continue
                identity = employee.employee_id
                weights[identity] = weights.get(identity, 0) + hours
                if source is config:
                    current_ids.append(identity)
                elif previous:
                    past_counts[identity] = sum(
                        employee.name in getattr(day, shift.value)
                        for day in previous.days
                        if day.date in dates
                        for shift in shifts
                    )
        pools[kind] = {
            "weights": weights,
            "previous_counts": past_counts,
            "current_ids": current_ids,
            "shifts": shifts,
            "off_only": off_only,
        }
    return pools


def balance_counts(schedule: Schedule, pool: dict) -> dict[str, int]:
    calendar = calendar_for_config(schedule.config)
    counts = dict(pool["previous_counts"])
    for employee in schedule.config.employees:
        identity = employee.employee_id
        if identity not in pool["current_ids"]:
            continue
        counts[identity] = counts.get(identity, 0) + sum(
            employee.name in getattr(day, shift.value)
            for day in schedule.days
            if not pool["off_only"] or not calendar.is_working(day.date)
            for shift in pool["shifts"]
        )
    return counts


def quality_report(schedule: Schedule) -> dict[str, Any]:
    if any(item.code == "previous_revision_changed" for item in schedule.diagnostics):
        schedule = schedule.model_copy(deep=True)
        schedule.config._quality_state = "stale"
    previous, history = previous_quality_schedule(schedule.config)
    pools = balance_pools(schedule.config)
    values = {
        name: weighted_imbalance(balance_counts(schedule, pool), pool["weights"])
        for name, pool in pools.items()
    }
    return {
        "window": "two_months" if previous else "month_only",
        "history": history,
        "periods": ([f"{previous.config.year:04d}-{previous.config.month:02d}"] if previous else [])
        + [f"{schedule.config.year:04d}-{schedule.config.month:02d}"],
        "source": schedule.config._quality_origin if previous else "unavailable",
        "source_revision_id": previous.revision_id or None if previous else None,
        "fairness": float(values["evening"] + values["night"]),
        "off_balance": float(values["off_moscow"] + values["off_khabarovsk"]),
        "pools": {
            name: {
                "weights": pool["weights"],
                "counts": balance_counts(schedule, pool),
                "imbalance": str(values[name]),
            }
            for name, pool in pools.items()
        },
    }
