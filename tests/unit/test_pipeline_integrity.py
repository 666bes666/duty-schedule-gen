from datetime import date

from duty_schedule.models import DaySchedule
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.core import EmployeeState
from duty_schedule.scheduler.postprocess.pipeline import Pipeline, PipelineContext


def pipeline_context(employees):
    return PipelineContext(
        days=[DaySchedule(date=date(2026, 4, 1), day_off=[e.name for e in employees])],
        employees=employees,
        holidays=set(),
        pinned_on=set(),
        carry_over_cw={},
        carry_over_last_shift={},
        states={e.name: EmployeeState() for e in employees},
        changelog=ChangeLog(),
    )


def test_failed_pass_rolls_back_days_states_and_changelog(minimal_employees):
    ctx = pipeline_context(minimal_employees)
    name = minimal_employees[0].name

    class Broken:
        name = "broken_stage"

        def run(self, candidate):
            candidate.days[0].morning.append(name)
            candidate.states[name].total_working = 99
            candidate.changelog.add("broken_stage", "added", name, candidate.days[0].date)
            raise RuntimeError("injected failure")

    original = ctx.days[0].model_dump()
    Pipeline([Broken()]).run(ctx)
    assert ctx.days[0].model_dump() == original
    assert ctx.states[name].total_working == 0
    assert not ctx.changelog.entries


def test_pass_cannot_hide_blocked_work_by_modifying_employee_input(minimal_employees):
    employee = minimal_employees[0]
    employee.unavailable_dates = [date(2026, 4, 1)]
    ctx = pipeline_context(minimal_employees)

    class Invalid:
        name = "invalid_stage"

        def run(self, candidate):
            candidate.employees[0].unavailable_dates.clear()
            candidate.days[0].day_off.remove(employee.name)
            candidate.days[0].morning.append(employee.name)
            return candidate.days

    Pipeline([Invalid()]).run(ctx)
    assert employee.name in ctx.days[0].day_off
    assert employee.name not in ctx.days[0].morning
    assert employee.unavailable_dates == [date(2026, 4, 1)]
