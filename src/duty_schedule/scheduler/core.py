from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import date

import structlog

from duty_schedule.constants import (
    MAX_BACKTRACK_ATTEMPTS,
)
from duty_schedule.logging import get_logger
from duty_schedule.models import (
    Config,
    Schedule,
    ShiftType,
)

logger = get_logger(__name__)


class ScheduleError(Exception):
    pass


@dataclass
class EmployeeState:
    consecutive_working: int = 0
    consecutive_off: int = 0
    last_shift: ShiftType | None = None
    night_count: int = 0
    morning_count: int = 0
    evening_count: int = 0
    workday_count: int = 0
    total_working: int = 0
    target_working_days: int = 0
    vacation_days: int = 0
    consecutive_morning: int = 0
    consecutive_evening: int = 0
    consecutive_workday: int = 0

    def shift_count(self, shift: ShiftType) -> int:
        return {
            ShiftType.NIGHT: self.night_count,
            ShiftType.MORNING: self.morning_count,
            ShiftType.EVENING: self.evening_count,
            ShiftType.WORKDAY: self.workday_count,
        }.get(shift, 0)

    def record(self, shift: ShiftType) -> None:
        if shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY):
            self.consecutive_working += 1
            self.consecutive_off = 0
            self.total_working += 1
        else:
            self.consecutive_off += 1
            self.consecutive_working = 0
        self.last_shift = shift
        if shift == ShiftType.MORNING:
            self.morning_count += 1
            self.consecutive_morning += 1
            self.consecutive_evening = 0
            self.consecutive_workday = 0
        elif shift == ShiftType.EVENING:
            self.evening_count += 1
            self.consecutive_evening += 1
            self.consecutive_morning = 0
            self.consecutive_workday = 0
        elif shift == ShiftType.NIGHT:
            self.night_count += 1
            self.consecutive_morning = 0
            self.consecutive_evening = 0
            self.consecutive_workday = 0
        elif shift == ShiftType.WORKDAY:
            self.workday_count += 1
            self.consecutive_workday += 1
            self.consecutive_morning = 0
            self.consecutive_evening = 0
        else:
            self.consecutive_morning = 0
            self.consecutive_evening = 0
            self.consecutive_workday = 0

    @property
    def effective_target(self) -> int:
        return max(0, self.target_working_days - self.vacation_days)

    def needs_more_work(self, remaining_days: int) -> bool:
        if remaining_days <= 0:
            return False
        deficit = self.effective_target - self.total_working
        return deficit > 0


def generate_schedule(
    config: Config,
    holidays: set[date] | None = None,
    baseline: Schedule | None = None,
) -> Schedule:
    ctx_vars = structlog.contextvars.get_contextvars()
    owns_context = "request_id" not in ctx_vars and "operation_id" not in ctx_vars
    if owns_context:
        structlog.contextvars.bind_contextvars(operation_id=uuid.uuid4().hex[:8])

    try:
        if baseline is not None:
            from duty_schedule.scheduler.postprocess.quality import changed_cells, repair_metadata
            from duty_schedule.scheduler.validation import validate_schedule_result

            names = {e.employee_id: e.name for e in config.employees}
            rename = {e.name: names.get(e.employee_id, e.name) for e in baseline.config.employees}
            preserved = baseline.model_copy(deep=True)
            preserved.config = config.model_copy(deep=True)
            for day in preserved.days:
                for shift in ShiftType:
                    setattr(
                        day,
                        shift.value,
                        [rename.get(name, name) for name in getattr(day, shift.value)],
                    )
                day.workday_hours = {
                    rename.get(name, name): hours for name, hours in day.workday_hours.items()
                }
            preserved = validate_schedule_result(preserved)
            if preserved.status == "ready" and not changed_cells(baseline, preserved):
                from duty_schedule.scheduler.postprocess.quality import optimization_provenance

                preserved.search_status = "preserved_baseline"
                preserved.metadata["repair"] = repair_metadata(baseline, preserved, "proven_zero")
                preserved.metadata["optimization"] = optimization_provenance(
                    baseline, preserved, "preserved_baseline"
                )
                from duty_schedule.quality_history import quality_report

                preserved.metadata["quality"] = quality_report(preserved)
                return preserved
        result = _generate_schedule_impl(config, holidays, baseline)
        if baseline is not None:
            from duty_schedule.scheduler.postprocess.quality import repair_metadata

            result.metadata["repair"] = repair_metadata(
                baseline, result, result.metadata.get("repair_optimality", "heuristic")
            )
        from duty_schedule.quality_history import quality_report

        result.metadata["quality"] = quality_report(result)
        return result
    finally:
        if owns_context:
            structlog.contextvars.unbind_contextvars("operation_id")


def _generate_schedule_impl(
    config: Config,
    holidays: set[date] | None = None,
    baseline: Schedule | None = None,
) -> Schedule:
    from duty_schedule.calendar import calendar_for_config
    from duty_schedule.scheduler.greedy import build_candidate
    from duty_schedule.scheduler.validation import validate_schedule_result
    from duty_schedule.workload import assignment_hours

    calendar = calendar_for_config(config, holidays)
    working_config = config.model_copy(deep=True, update={"production_calendar": calendar})
    logger.info(
        "schedule_generation_start",
        year=config.year,
        month=config.month,
        employees=len(config.employees),
        solver=config.solver,
    )
    logger.debug(
        "scheduler_config", seed=config.seed, max_backtrack_attempts=MAX_BACKTRACK_ATTEMPTS
    )
    started = time.monotonic()
    candidates: list[Schedule] = []
    context_codes = {
        "calendar_unverified",
        "history_missing",
        "history_stale",
        "history_unverified",
        "history_invalid",
        "history_duplicate",
    }

    def acceptable(schedule: Schedule, pending: bool = False) -> bool:
        allowed = context_codes | ({"approval_required"} if pending else set())
        return all(item.code in allowed for item in schedule.diagnostics)

    def rank(schedule: Schedule) -> tuple[int, int, int]:
        errors = sum(
            item.code not in context_codes | {"monthly_hours", "approval_required"}
            for item in schedule.diagnostics
        )
        deficit = sum(
            abs(
                sum(assignment_hours(day, name, calendar) for day in schedule.days)
                - target.selected_hours
            )
            for name, target in schedule.monthly_targets.items()
        )
        pending = sum(item.code == "approval_required" for item in schedule.diagnostics)
        return errors, deficit, pending

    if config.solver == "cpsat" or baseline is not None:
        from duty_schedule.scheduler.solver import SolverUnavailableError, solve_schedule

        try:
            result = solve_schedule(working_config, baseline=baseline)
            candidates.append(result)
            if not acceptable(result) and result.search_status == "infeasible":
                pending = solve_schedule(working_config, allow_pending=True, baseline=baseline)
                candidates.append(pending)
                if acceptable(pending, pending=True):
                    result = pending
        except SolverUnavailableError:
            logger.warning("cpsat_unavailable_greedy_fallback")
            result = None
        if result is not None:
            logger.info(
                "schedule_generated", status=result.status, days=len(result.days), solver="cpsat"
            )
            return result

    best: Schedule | None = None
    for allow_pending in (False, True):
        for attempt in range(4):
            days, successful = build_candidate(
                working_config,
                calendar,
                config.seed + attempt * 1009,
                allow_pending,
                baseline,
            )
            candidate = validate_schedule_result(
                Schedule(
                    config=working_config,
                    days=days,
                    search_status="candidate" if successful else "heuristic_exhausted",
                    metadata={"solver": "greedy", "attempts": attempt + 1},
                )
            )
            candidates.append(candidate)
            best = min(candidates, key=rank)
            if successful and acceptable(candidate, pending=allow_pending):
                candidate.search_status = (
                    "pending_approval"
                    if any(item.code == "approval_required" for item in candidate.diagnostics)
                    else "heuristic_solution"
                )
                best = candidate
                break
        if best is not None and acceptable(best, pending=allow_pending):
            break
        if not allow_pending:
            from duty_schedule.scheduler.solver import SolverUnavailableError, solve_schedule

            try:
                repaired = solve_schedule(working_config, timeout=3, allow_pending=False)
                repaired.metadata["solver"] = "greedy"
                repaired.metadata["repair_solver"] = "cpsat"
                candidates.append(repaired)
                if acceptable(repaired):
                    best = repaired
                    break
            except SolverUnavailableError:
                pass
    if best is None:
        best = min(candidates, key=rank)
    if acceptable(best):
        from duty_schedule.scheduler.postprocess.quality import optimize_candidate

        best = optimize_candidate(best, baseline=baseline)
    logger.info(
        "greedy_phase_done",
        duration_ms=round((time.monotonic() - started) * 1000, 1),
        attempts=len(candidates),
    )
    logger.info("schedule_generated", status=best.status, days=len(best.days), solver="greedy")
    return validate_schedule_result(best)
