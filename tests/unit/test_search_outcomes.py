from __future__ import annotations

import pytest

from duty_schedule.models import DaySchedule
from duty_schedule.project import ExportBlockedError, ensure_exportable
from duty_schedule.scheduler import generate_schedule, greedy, solver


@pytest.mark.skipif(not solver._HAS_ORTOOLS, reason="OR-Tools not installed")
def test_solver_timeout_is_not_reported_as_proven_infeasible(planning_config, monkeypatch) -> None:
    original_solve = solver.cp_model.CpSolver.solve

    def zero_time_solve(cpsat, model):
        cpsat.parameters.max_time_in_seconds = 0.0
        return original_solve(cpsat, model)

    monkeypatch.setattr(solver.cp_model.CpSolver, "solve", zero_time_solve)
    result = solver.solve_schedule(planning_config, timeout=0)
    assert result.status == "diagnostic"
    assert result.search_status == "timeout"
    assert any(d.code == "search_timeout" for d in result.diagnostics)
    assert not any(d.code == "search_infeasible" for d in result.diagnostics)
    assert {"coverage", "monthly_hours"} <= {d.code for d in result.diagnostics}
    with pytest.raises(ExportBlockedError):
        ensure_exportable(result)


def test_greedy_exhaustion_without_solver_does_not_claim_infeasibility(
    planning_config, monkeypatch
):
    days = [
        DaySchedule(date=record.date, day_off=[e.name for e in planning_config.employees])
        for record in planning_config.production_calendar.days
    ]
    monkeypatch.setattr(greedy, "build_candidate", lambda *args: (days, False))
    monkeypatch.setattr(solver, "_HAS_ORTOOLS", False)
    result = generate_schedule(planning_config)
    assert result.status == "diagnostic"
    assert result.search_status == "heuristic_exhausted"
    assert any(d.code == "search_heuristic_exhausted" for d in result.diagnostics)
    assert not any(d.code == "search_infeasible" for d in result.diagnostics)
    assert {"coverage", "monthly_hours"} <= {d.code for d in result.diagnostics}
    with pytest.raises(ExportBlockedError):
        ensure_exportable(result)
