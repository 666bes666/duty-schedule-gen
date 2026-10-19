from __future__ import annotations

from typing import Any

import pytest

from duty_schedule.models import City, Config, Employee, ScheduleType
from tests.conftest import complete_config

cp_model = pytest.importorskip("ortools.sat.python.cp_model")


def _config() -> Config:
    employees = [
        Employee(name=f"M{i}", city=City.MOSCOW, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(5)
    ] + [
        Employee(name=f"K{i}", city=City.KHABAROVSK, schedule_type=ScheduleType.FLEXIBLE)
        for i in range(3)
    ]
    return complete_config(Config(year=2026, month=4, seed=7, employees=employees))


def _recording_solver(unknown_calls: set[int]) -> tuple[type, list[float]]:
    real_solver_class = cp_model.CpSolver
    limits: list[float] = []

    class RecordingSolver:
        def __init__(self) -> None:
            self._real = real_solver_class()
            self.parameters = self._real.parameters
            self._simulated = False

        def solve(self, model: Any) -> Any:
            limits.append(self.parameters.max_time_in_seconds)
            if len(limits) - 1 in unknown_calls:
                self._simulated = True
                return cp_model.UNKNOWN
            self._simulated = False
            return self._real.solve(model)

        @property
        def wall_time(self) -> float:
            return limits[-1] if self._simulated else self._real.wall_time

        @property
        def objective_value(self) -> float:
            return self._real.objective_value

        def value(self, variable: Any) -> Any:
            return self._real.value(variable)

    return RecordingSolver, limits


def test_first_layer_timeout_retries_with_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duty_schedule.scheduler import solver as solver_module

    recording, limits = _recording_solver({0})
    monkeypatch.setattr(solver_module.cp_model, "CpSolver", recording)

    schedule = solver_module.solve_schedule(_config(), timeout=6)

    slice_limit = limits[0]
    assert slice_limit < 6
    assert limits[1] == pytest.approx(6 - slice_limit)
    assert all(limit == pytest.approx(slice_limit) for limit in limits[2:])
    assert schedule.metadata["first_solution_retry"] is True
    assert schedule.search_status in {"optimal", "feasible"}
    assert schedule.status == "ready"


def test_budget_exhausted_by_first_layer_keeps_timeout_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duty_schedule.scheduler import solver as solver_module

    recording, limits = _recording_solver({0, 1})
    monkeypatch.setattr(solver_module.cp_model, "CpSolver", recording)

    schedule = solver_module.solve_schedule(_config(), timeout=6)

    assert len(limits) == 2
    assert sum(limits) == pytest.approx(6)
    assert schedule.search_status == "timeout"
    assert schedule.status == "diagnostic"
    assert schedule.metadata["first_solution_retry"] is True


def test_found_first_solution_keeps_layer_slices(monkeypatch: pytest.MonkeyPatch) -> None:
    from duty_schedule.scheduler import solver as solver_module

    recording, limits = _recording_solver(set())
    monkeypatch.setattr(solver_module.cp_model, "CpSolver", recording)

    schedule = solver_module.solve_schedule(_config(), timeout=6)

    assert limits
    assert all(limit == pytest.approx(limits[0]) for limit in limits)
    assert schedule.metadata["first_solution_retry"] is False


def test_later_layer_timeout_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from duty_schedule.scheduler import solver as solver_module

    recording, limits = _recording_solver({1})
    monkeypatch.setattr(solver_module.cp_model, "CpSolver", recording)

    schedule = solver_module.solve_schedule(_config(), timeout=6)

    assert len(limits) == 2
    assert limits[0] == pytest.approx(limits[1])
    assert schedule.metadata["first_solution_retry"] is False
    assert schedule.status == "ready"
