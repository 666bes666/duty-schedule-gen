from datetime import date

from duty_schedule.models import DaySchedule, Schedule
from duty_schedule.project import add_revision, check_current, new_project
from tests.ui.fixtures import journey_config, journey_days


def test_noop_check_preserves_revision_id():
    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    checked = check_current(check_current(project))
    assert checked.active_revisions == project.active_revisions
    assert len(checked.revisions) == len(project.revisions)


def test_failed_repair_does_not_replace_current_version():
    from duty_schedule.ui.components import generate_project

    config = journey_config()
    project = add_revision(new_project(config), Schedule(config=config, days=journey_days(config)))
    project.config.employees[0].unavailable_dates = [date(2026, 4, 1)]
    repaired = generate_project(project)
    assert repaired.active_revisions == project.active_revisions
    assert repaired.repair_candidate.status == "diagnostic"


def test_small_repair_matches_independent_minimum_oracle():
    from duty_schedule.scheduler.core import generate_schedule
    from duty_schedule.scheduler.postprocess.quality import changed_cells

    config = journey_config()
    baseline = Schedule(config=config, days=journey_days(config))
    result = generate_schedule(config, baseline=baseline)
    assert changed_cells(baseline, result) == []
    assert result.metadata["repair"]["optimality"] == "proven_zero"


def test_hours_and_rename_count_by_identity():
    from duty_schedule.scheduler.postprocess.quality import changed_cells

    config = journey_config()
    original = Schedule(
        config=config,
        days=[DaySchedule(date=date(2026, 4, 1), workday=["M0"], workday_hours={"M0": 3})],
    )
    after = original.model_copy(deep=True)
    after.config.employees[0].name = "Renamed"
    after.days[0].workday = ["Renamed"]
    after.days[0].workday_hours = {"Renamed": 3}
    assert changed_cells(original, after) == []
    after.days[0].workday_hours = {"Renamed": 4}
    assert len(changed_cells(original, after)) == 1


def test_nonzero_repair_matches_exhaustive_oracle():
    from itertools import product

    from duty_schedule.models import PinnedAssignment, ShiftType
    from duty_schedule.scheduler.core import generate_schedule
    from duty_schedule.scheduler.rules import assignment_for
    from duty_schedule.scheduler.validation import validate_schedule_result

    config = journey_config()
    baseline = validate_schedule_result(Schedule(config=config, days=journey_days(config)))
    cells = {(date(2026, 4, n), name) for n in (13, 15) for name in ("M0", "M1")}
    config = config.model_copy(deep=True)
    config.pins = [pin for pin in config.pins if (pin.date, pin.employee_name) not in cells]
    config.pins.append(
        PinnedAssignment(date=date(2026, 4, 13), employee_name="M0", shift="evening")
    )
    candidates = []
    for values in product(("morning", "evening"), repeat=4):
        candidate = baseline.model_copy(deep=True)
        candidate.config = config
        for (day, name), value in zip(sorted(cells), values, strict=True):
            record = next(item for item in candidate.days if item.date == day)
            for shift in ShiftType:
                if name in getattr(record, shift.value):
                    getattr(record, shift.value).remove(name)
            getattr(record, value).append(name)
        if validate_schedule_result(candidate).status == "ready":
            candidates.append(
                sum(
                    assignment_for(old, name) != assignment_for(new, name)
                    for old, new in zip(baseline.days, candidate.days, strict=True)
                    for name in ("M0", "M1")
                )
            )
    assert min(candidates) == 2
    repaired = generate_schedule(config, baseline=baseline)
    assert repaired.status == "ready"
    assert repaired.metadata["repair"]["changed_cells"] == min(candidates)
    assert repaired.metadata["repair"]["optimality"] == "proven_minimum"


def test_nonzero_repair_without_optional_solver_preserves_cells(monkeypatch):
    from duty_schedule.models import PinnedAssignment
    from duty_schedule.scheduler.core import generate_schedule
    from duty_schedule.scheduler.validation import validate_schedule_result

    monkeypatch.setattr("duty_schedule.scheduler.solver._HAS_ORTOOLS", False)
    config = journey_config()
    baseline = validate_schedule_result(Schedule(config=config, days=journey_days(config)))
    config = config.model_copy(deep=True)
    freed = {(date(2026, 4, n), name) for n in (13, 15) for name in ("M0", "M1")}
    config.pins = [pin for pin in config.pins if (pin.date, pin.employee_name) not in freed]
    config.pins.append(
        PinnedAssignment(date=date(2026, 4, 13), employee_name="M0", shift="evening")
    )
    repaired = generate_schedule(config, baseline=baseline)
    assert repaired.status == "ready"
    assert repaired.metadata["repair"]["changed_cells"] == 2
    assert repaired.metadata["repair"]["optimality"] == "heuristic"


def test_feasible_change_layer_never_claims_proven_minimum(monkeypatch):
    from duty_schedule.models import PinnedAssignment
    from duty_schedule.scheduler import solver
    from duty_schedule.scheduler.core import generate_schedule
    from duty_schedule.scheduler.validation import validate_schedule_result

    if not solver._HAS_ORTOOLS:
        __import__("pytest").skip("OR-Tools unavailable")
    config = journey_config()
    baseline = validate_schedule_result(Schedule(config=config, days=journey_days(config)))
    config = config.model_copy(deep=True)
    freed = {(date(2026, 4, n), name) for n in (13, 15) for name in ("M0", "M1")}
    config.pins = [pin for pin in config.pins if (pin.date, pin.employee_name) not in freed]
    config.pins.append(
        PinnedAssignment(date=date(2026, 4, 13), employee_name="M0", shift="evening")
    )
    original = solver.cp_model.CpSolver.solve
    calls = 0

    def bounded_status(instance, model):
        nonlocal calls
        calls += 1
        status = original(instance, model)
        return (
            solver.cp_model.FEASIBLE if calls == 2 and status == solver.cp_model.OPTIMAL else status
        )

    monkeypatch.setattr(solver.cp_model.CpSolver, "solve", bounded_status)
    result = generate_schedule(config, baseline=baseline)
    assert result.status == "ready"
    assert result.metadata["repair"]["optimality"] == "bounded_search"


def test_calendar_hours_change_cannot_claim_zero_edits():
    from duty_schedule.models import VacationPeriod
    from duty_schedule.scheduler.core import generate_schedule
    from duty_schedule.scheduler.validation import validate_schedule_result

    config = journey_config()
    config.pins = []
    config.employees[1].vacations = [VacationPeriod(start=date(2026, 4, 2), end=date(2026, 4, 2))]
    days = journey_days(config)
    days[1].day_off.remove("M1")
    days[1].vacation.append("M1")
    days[3].workday.remove("M1")
    days[3].day_off.append("M1")
    baseline = validate_schedule_result(Schedule(config=config, days=days))
    assert baseline.status == "ready"
    changed = config.model_copy(deep=True)
    changed.production_calendar.days[1].kind = "short"
    repaired = generate_schedule(changed, baseline=baseline)
    assert repaired.metadata["repair"]["changed_cells"] > 0
    assert repaired.metadata["repair"]["optimality"] != "proven_zero"
