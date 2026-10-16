from __future__ import annotations

import pytest

from duty_schedule.models import (
    OptimizationPriority,
    PinnedAssignment,
    RuleApproval,
    Schedule,
    ShiftType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.core import EmployeeState, generate_schedule
from duty_schedule.scheduler.postprocess.pipeline import PipelineContext, build_default_pipeline
from duty_schedule.scheduler.postprocess.quality import quality_key
from duty_schedule.scheduler.rules import assignment_for
from duty_schedule.scheduler.validation import validate_schedule_result
from duty_schedule.workload import assignment_hours


@pytest.mark.parametrize("priority", [None, *OptimizationPriority])
@pytest.mark.parametrize("missing_workdays", [0, 3])
def test_legacy_passes_preserve_hours_pins_and_fixed_quality_order(
    planning_config, priority, missing_workdays, capsys, caplog
):
    original = generate_schedule(planning_config)
    assert original.status == "ready"
    candidate = original.model_copy(deep=True)
    employee = candidate.config.employees[0]
    removed = 0
    for day in candidate.days:
        if employee.name in day.workday and removed < missing_workdays:
            day.workday.remove(employee.name)
            day.day_off.append(employee.name)
            removed += 1
    assert removed == missing_workdays
    pinned_day = candidate.days[-1]
    pinned_shift = assignment_for(pinned_day, employee.name)
    assert pinned_shift is not None
    candidate.config.pins = [
        PinnedAssignment(date=pinned_day.date, employee_name=employee.name, shift=pinned_shift)
    ]
    candidate = validate_schedule_result(candidate)
    calendar = candidate.config.production_calendar
    before_hours = {
        name: sum(assignment_hours(day, name, calendar) for day in candidate.days)
        for name in candidate.monthly_targets
    }
    before_deficit = sum(
        abs(before_hours[name] - target.selected_hours)
        for name, target in candidate.monthly_targets.items()
    )
    before_key = (before_deficit, *quality_key(candidate))
    original_diagnostics = {(d.code, d.employee_name, d.date) for d in candidate.diagnostics}
    context = PipelineContext(
        days=candidate.days,
        employees=candidate.config.employees,
        holidays=calendar.off_dates(),
        pinned_on={(pinned_day.date, employee.name)},
        carry_over_cw={
            carry.employee_name: carry.consecutive_working for carry in candidate.config.carry_over
        },
        carry_over_last_shift={
            carry.employee_name: carry.last_shift
            for carry in candidate.config.carry_over
            if carry.last_shift is not None
        },
        states={
            name: EmployeeState(target_working_days=target.selected_hours // 8)
            for name, target in candidate.monthly_targets.items()
        },
        changelog=ChangeLog(),
        config=candidate.config,
    )
    before_config = candidate.config.model_dump(mode="json")
    result = build_default_pipeline(priority, small_team=True).run(context)
    captured = capsys.readouterr()
    assert "postprocess_stage_failed" not in captured.out + captured.err + caplog.text
    checked = validate_schedule_result(Schedule(config=candidate.config, days=result))
    after_hours = {
        name: sum(assignment_hours(day, name, calendar) for day in checked.days)
        for name in checked.monthly_targets
    }
    after_deficit = sum(
        abs(after_hours[name] - target.selected_hours)
        for name, target in checked.monthly_targets.items()
    )
    assert (after_deficit, *quality_key(checked)) <= before_key
    assert {(d.code, d.employee_name, d.date) for d in checked.diagnostics} <= original_diagnostics
    assert candidate.config.model_dump(mode="json") == before_config
    assert assignment_for(checked.days[-1], employee.name) == pinned_shift
    if not missing_workdays:
        assert after_hours == before_hours
        assert checked.status == "ready"


def test_legacy_pipeline_preserves_short_day_and_confirmed_individual_hours(
    planning_config, capsys, caplog
):
    planning_config.production_calendar.days[0].kind = "short"
    original = generate_schedule(planning_config)
    assert original.status == "ready"
    employee = original.config.employees[0]
    calendar = original.config.production_calendar
    workdays = [
        day
        for day in original.days
        if employee.name in day.workday and calendar.hours(day.date) == 8
    ]
    offdays = [
        day
        for day in original.days
        if employee.name in day.day_off and calendar.hours(day.date) == 8
    ]
    candidate = None
    for first in workdays:
        for second in offdays:
            trial = original.model_copy(deep=True)
            trial_first = next(day for day in trial.days if day.date == first.date)
            trial_second = next(day for day in trial.days if day.date == second.date)
            trial_first.workday_hours[employee.name] = 3
            trial_second.day_off.remove(employee.name)
            trial_second.workday.append(employee.name)
            trial_second.workday_hours[employee.name] = 5
            for day, hours in ((first.date, 3), (second.date, 5)):
                trial.config.pins.append(
                    PinnedAssignment(
                        date=day,
                        employee_name=employee.name,
                        shift=ShiftType.WORKDAY,
                        working_hours=hours,
                    )
                )
                trial.config.approvals.append(
                    RuleApproval(
                        date=day,
                        employee_name=employee.name,
                        employee_id=employee.employee_id,
                        rule="individual_workday",
                        purpose="monthly_norm",
                        value=hours,
                    )
                )
            checked = validate_schedule_result(trial)
            if checked.status == "ready":
                candidate = checked
                break
        if candidate is not None:
            break
    assert candidate is not None
    assert all(target.selected_hours == 175 for target in candidate.monthly_targets.values())
    context = PipelineContext(
        days=candidate.days,
        employees=candidate.config.employees,
        holidays=calendar.off_dates(),
        pinned_on={(pin.date, pin.employee_name) for pin in candidate.config.pins},
        carry_over_cw={
            carry.employee_name: carry.consecutive_working for carry in candidate.config.carry_over
        },
        carry_over_last_shift={},
        states={
            name: EmployeeState(target_working_days=target.selected_hours // 8)
            for name, target in candidate.monthly_targets.items()
        },
        changelog=ChangeLog(),
        config=candidate.config,
    )
    result = build_default_pipeline(OptimizationPriority.CONSECUTIVE_DAYS, small_team=True).run(
        context
    )
    captured = capsys.readouterr()
    assert "postprocess_stage_failed" not in captured.out + captured.err + caplog.text
    checked = validate_schedule_result(Schedule(config=candidate.config, days=result))
    assert checked.status == "ready"
    assert quality_key(checked) <= quality_key(candidate)
    assert all(
        sum(assignment_hours(day, name, calendar) for day in checked.days) == 175
        for name in checked.monthly_targets
    )
    for pin in checked.config.pins:
        day = next(day for day in checked.days if day.date == pin.date)
        assert assignment_for(day, pin.employee_name) == ShiftType.WORKDAY
        assert day.workday_hours[pin.employee_name] == pin.working_hours
