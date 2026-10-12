from __future__ import annotations

from collections.abc import Callable

from duty_schedule.calendar import CalendarError, fetch_production_calendar
from duty_schedule.models import Config, Schedule, ScheduleDiagnostic, collect_config_issues
from duty_schedule.scheduler.core import ScheduleError, generate_schedule
from duty_schedule.scheduler.validation import validate_schedule_result


def plan_schedule(
    config: Config, generator: Callable[[Config], Schedule] = generate_schedule
) -> Schedule:
    errors, _warnings = collect_config_issues(config)
    if errors:
        result = validate_schedule_result(
            Schedule(config=config, days=[], search_status="config_invalid")
        )
        result.diagnostics.insert(
            0, ScheduleDiagnostic(code="config_invalid", detail="; ".join(errors))
        )
        result.status = "diagnostic"
        return result
    if config.production_calendar is None:
        try:
            calendar = fetch_production_calendar(config.year, config.month)
        except CalendarError as exc:
            result = validate_schedule_result(
                Schedule(config=config, days=[], search_status="calendar_unavailable")
            )
            result.diagnostics.insert(
                0, ScheduleDiagnostic(code="calendar_unavailable", detail=str(exc))
            )
            result.status = "diagnostic"
            return result
        config = config.model_copy(update={"production_calendar": calendar})
    try:
        result = generator(config)
    except ScheduleError as exc:
        result = validate_schedule_result(
            Schedule(config=config, days=[], search_status="heuristic_exhausted")
        )
        result.diagnostics.insert(0, ScheduleDiagnostic(code="search_failed", detail=str(exc)))
        result.status = "diagnostic"
        return result
    return validate_schedule_result(result)
