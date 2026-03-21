from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

from duty_schedule.logging import get_logger
from duty_schedule.models import (
    DaySchedule,
    Employee,
    OptimizationPriority,
    ShiftType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.constraints import _is_working_on_day

logger = get_logger(__name__)


@dataclass
class PipelineContext:
    days: list[DaySchedule]
    employees: list[Employee]
    holidays: set[date]
    pinned_on: set[tuple[date, str]]
    carry_over_cw: dict[str, int]
    carry_over_last_shift: dict[str, ShiftType]
    states: dict[str, Any]
    changelog: ChangeLog


@runtime_checkable
class PostProcessStage(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> list[DaySchedule]: ...


def _recalc_total_working(ctx: PipelineContext) -> None:
    for emp in ctx.employees:
        ctx.states[emp.name].total_working = sum(
            1 for d in ctx.days if _is_working_on_day(emp.name, d)
        )


@dataclass
class BalanceWeekendWork:
    name: str = "balance_weekend_work"
    strict: bool = False

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .balance import _balance_weekend_work

        return _balance_weekend_work(
            ctx.days,
            ctx.employees,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            changelog=ctx.changelog,
            strict=self.strict,
        )


@dataclass
class BalanceDutyShifts:
    name: str = "balance_duty_shifts"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .balance import _balance_duty_shifts

        return _balance_duty_shifts(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            changelog=ctx.changelog,
        )


@dataclass
class BalanceEveningShifts:
    name: str = "balance_evening"
    strict: bool = False

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .balance import _balance_evening_shifts

        return _balance_evening_shifts(
            ctx.days,
            ctx.employees,
            pinned_on=ctx.pinned_on,
            changelog=ctx.changelog,
            strict=self.strict,
        )


@dataclass
class TargetAdjustment:
    name: str = "target_adjustment"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .target import _target_adjustment_pass

        _recalc_total_working(ctx)
        return _target_adjustment_pass(
            ctx.days,
            ctx.employees,
            ctx.states,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            carry_over_last_shift=ctx.carry_over_last_shift,
            changelog=ctx.changelog,
        )


@dataclass
class TrimLongOffBlocks:
    name: str = "trim_long_off_blocks"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .target import _trim_long_off_blocks

        return _trim_long_off_blocks(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            carry_over_last_shift=ctx.carry_over_last_shift,
            changelog=ctx.changelog,
        )


@dataclass
class MinimizeIsolatedOff:
    name: str = "minimize_isolated_off"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .isolation import _minimize_isolated_off

        return _minimize_isolated_off(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            carry_over_last_shift=ctx.carry_over_last_shift,
            changelog=ctx.changelog,
        )


@dataclass
class BreakEveningIsolatedPattern:
    name: str = "break_evening_isolated_pattern"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .isolation import _break_evening_isolated_pattern

        return _break_evening_isolated_pattern(
            ctx.days,
            ctx.employees,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            changelog=ctx.changelog,
        )


@dataclass
class EqualizeIsolatedOff:
    name: str = "equalize_isolated_off"
    strict: bool = False

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .isolation import _equalize_isolated_off

        return _equalize_isolated_off(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            changelog=ctx.changelog,
            strict=self.strict,
        )


@dataclass
class MultiEmployeeSwapPass:
    name: str = "multi_employee_swap"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .isolation import _multi_employee_swap_pass

        return _multi_employee_swap_pass(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            changelog=ctx.changelog,
        )


@dataclass
class MinimizeMaxStreak:
    name: str = "minimize_max_streak"
    strict: bool = False

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .balance import _minimize_max_streak

        return _minimize_max_streak(
            ctx.days,
            ctx.employees,
            ctx.holidays,
            pinned_on=ctx.pinned_on,
            carry_over_cw=ctx.carry_over_cw,
            carry_over_last_shift=ctx.carry_over_last_shift,
            changelog=ctx.changelog,
            strict=self.strict,
        )


@dataclass
class RecalcTotalWorking:
    name: str = "recalc_total_working"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        _recalc_total_working(ctx)
        return ctx.days


@dataclass
class TrimExcessWorkdays:
    name: str = "trim_excess_workdays"

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from duty_schedule.scheduler.core import ScheduleError

        _recalc_total_working(ctx)
        for emp in ctx.employees:
            actual = sum(1 for d in ctx.days if _is_working_on_day(emp.name, d))
            target = ctx.states[emp.name].effective_target
            if actual > target:
                for i in range(len(ctx.days) - 1, -1, -1):
                    if actual <= target:
                        break
                    ds = ctx.days[i]
                    if emp.name in ds.workday and (ds.date, emp.name) not in ctx.pinned_on:
                        ds.workday.remove(emp.name)
                        ds.day_off.append(emp.name)
                        actual -= 1

        for emp in ctx.employees:
            actual = sum(1 for d in ctx.days if _is_working_on_day(emp.name, d))
            target = ctx.states[emp.name].effective_target
            if actual > target:
                removable = sum(
                    1
                    for d in ctx.days
                    if emp.name in d.workday and (d.date, emp.name) not in ctx.pinned_on
                )
                if removable > 0:
                    raise ScheduleError(
                        f"Нарушена норма для {emp.name}: "
                        f"факт={actual}, норма={target}, "
                        f"осталось {removable} снимаемых WORKDAY"
                    )

        return ctx.days


class Pipeline:
    def __init__(self, stages: list[PostProcessStage]) -> None:
        self.stages = stages

    def run(self, ctx: PipelineContext) -> list[DaySchedule]:
        from .metrics import compute_snapshot

        for stage in self.stages:
            before = compute_snapshot(ctx.days, ctx.employees, ctx.holidays)
            pre_changes = len(ctx.changelog.entries)
            ctx.days = stage.run(ctx)
            after = compute_snapshot(ctx.days, ctx.employees, ctx.holidays)
            logger.debug(
                "postprocess_stage_done",
                stage=stage.name,
                changes=len(ctx.changelog.entries) - pre_changes,
                score_before=round(before.score(), 1),
                score_after=round(after.score(), 1),
                iso_off_delta=(after.isolated_off_total - before.isolated_off_total),
                evening_bal_delta=(after.evening_balance - before.evening_balance),
            )
        return ctx.days


def build_default_pipeline(
    priority: OptimizationPriority | None = None,
    *,
    small_team: bool = False,
) -> Pipeline:
    stages: list[PostProcessStage] = [
        BalanceWeekendWork(),
        RecalcTotalWorking(),
        BalanceDutyShifts(),
        BalanceEveningShifts(name="balance_evening_1"),
        TargetAdjustment(name="target_adjustment_1"),
        TrimLongOffBlocks(),
        RecalcTotalWorking(),
        TargetAdjustment(name="target_adjustment_2"),
        MinimizeIsolatedOff(name="minimize_isolated_off_1"),
        BreakEveningIsolatedPattern(),
        MinimizeIsolatedOff(name="minimize_isolated_off_2"),
        EqualizeIsolatedOff(),
        MinimizeIsolatedOff(name="minimize_isolated_off_3"),
        MultiEmployeeSwapPass(),
        BalanceEveningShifts(name="balance_evening_2"),
        RecalcTotalWorking(),
        TargetAdjustment(name="target_adjustment_3"),
    ]

    if small_team:
        stages.extend(
            [
                MinimizeIsolatedOff(name="small_team_iso_1"),
                MultiEmployeeSwapPass(name="small_team_swap"),
                EqualizeIsolatedOff(name="small_team_equalize"),
                BalanceEveningShifts(name="small_team_evening", strict=True),
                RecalcTotalWorking(),
                TargetAdjustment(name="small_team_norm_fix"),
            ]
        )

    if priority == OptimizationPriority.ISOLATED_WEEKENDS:
        for i in range(5):
            stages.append(MinimizeIsolatedOff(name=f"priority_minimize_iso_{i}"))
        stages.append(EqualizeIsolatedOff(name="priority_equalize_iso", strict=True))
    elif priority == OptimizationPriority.EVENING_SHIFTS:
        stages.append(BalanceEveningShifts(name="priority_evening", strict=True))
    elif priority == OptimizationPriority.CONSECUTIVE_DAYS:
        stages.append(MinimizeMaxStreak(name="priority_streak", strict=True))
    elif priority == OptimizationPriority.WEEKEND_DAYS:
        stages.append(BalanceWeekendWork(name="priority_weekend", strict=True))

    if priority is not None:
        stages.append(RecalcTotalWorking())
        stages.append(TargetAdjustment(name="priority_norm_fix"))

    stages.append(TrimExcessWorkdays())
    stages.append(BalanceEveningShifts(name="balance_evening_final"))

    return Pipeline(stages)
