from datetime import UTC, date, datetime, timedelta

import pytest

from duty_schedule.models import (
    CalendarDay,
    CarryOverState,
    Config,
    DaySchedule,
    Employee,
    PinnedAssignment,
    ProductionCalendar,
    RuleApproval,
    Schedule,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)
from duty_schedule.scheduler.core import generate_schedule
from duty_schedule.scheduler.validation import validate_schedule_result


def context(employees):
    calendar = ProductionCalendar(
        year=2026,
        month=4,
        days=[
            CalendarDay(
                date=date(2026, 4, d),
                kind="off" if date(2026, 4, d).weekday() >= 5 else "working",
            )
            for d in range(1, 31)
        ],
        source="fixture",
        fetched_at=datetime.now(UTC),
    )
    return Config(
        year=2026,
        month=4,
        employees=employees,
        production_calendar=calendar,
        carry_over=[
            CarryOverState(
                employee_name=e.name,
                employee_id=e.employee_id,
                as_of=date(2026, 3, 31),
                source="new_employee",
                no_previous_shifts=True,
            )
            for e in employees
        ],
    )


def draft(config):
    return Schedule(
        config=config,
        days=[
            DaySchedule(date=date(2026, 4, d), day_off=[e.name for e in config.employees])
            for d in range(1, 31)
        ],
    )


def assign(schedule, employee, day_index, shift):
    day = schedule.days[day_index]
    day.day_off.remove(employee.name)
    getattr(day, shift.value).append(employee.name)


def test_validator_rejects_forged_ready_and_missing_calendar_history(minimal_employees):
    schedule = draft(context(minimal_employees))
    schedule.config.production_calendar = None
    schedule.config.carry_over = []
    schedule.status = "ready"
    result = validate_schedule_result(schedule)
    assert result.status == "diagnostic"
    assert {"calendar_unverified", "history_missing", "coverage", "monthly_hours"} <= {
        d.code for d in result.diagnostics
    }
    assert schedule.status == "ready"


def test_all_states_checked_and_absences_not_fabricated(minimal_employees):
    schedule = draft(context(minimal_employees))
    employee = minimal_employees[0]
    schedule.days[0].morning.append(employee.name)
    schedule.days[1].vacation.append(employee.name)
    codes = {d.code for d in validate_schedule_result(schedule).diagnostics}
    assert "multiple_assignments" in codes
    assert "unexpected_absence" in codes


def test_unavailable_sick_leave_and_workday_on_off_are_hard(minimal_employees):
    employee = minimal_employees[0]
    employee.unavailable_dates = [date(2026, 4, 1)]
    employee.sick_leaves = [VacationPeriod(start=date(2026, 4, 2), end=date(2026, 4, 2))]
    schedule = draft(context(minimal_employees))
    assign(schedule, employee, 0, ShiftType.MORNING)
    assign(schedule, employee, 1, ShiftType.MORNING)
    assign(schedule, employee, 3, ShiftType.WORKDAY)
    codes = {d.code for d in validate_schedule_result(schedule).diagnostics}
    assert {"unavailable_date", "absence_conflict", "workday_nonworking"} <= codes


def test_streak_approval_is_date_employee_value_specific_and_never_allows_eight(minimal_employees):
    employee = minimal_employees[0]
    schedule = draft(context(minimal_employees))
    for i in range(8):
        assign(schedule, employee, i, ShiftType.MORNING)
    first = validate_schedule_result(schedule)
    assert any(d.code == "approval_required" and d.value == 7 for d in first.diagnostics)
    schedule.config.approvals = [
        RuleApproval(
            employee_name=employee.name,
            date=date(2026, 4, 7),
            rule="working_streak",
            purpose="coverage",
            value=7,
        )
    ]
    result = validate_schedule_result(schedule)
    assert not any(
        d.code == "approval_required" and d.date == date(2026, 4, 7) for d in result.diagnostics
    )
    assert any(
        d.code == "absolute_streak" and d.date == date(2026, 4, 8) for d in result.diagnostics
    )


def test_previous_month_evening_and_stale_history(minimal_employees):
    employee = minimal_employees[0]
    config = context(minimal_employees)
    config.carry_over[0] = CarryOverState(
        employee_name=employee.name,
        last_shift=ShiftType.EVENING,
        consecutive_working=2,
        consecutive_same_shift=1,
        as_of=date(2026, 3, 31),
        source="manual",
    )
    schedule = draft(config)
    assign(schedule, employee, 0, ShiftType.MORNING)
    assert any(d.code == "evening_rest" for d in validate_schedule_result(schedule).diagnostics)
    config.carry_over[0].as_of -= timedelta(days=1)
    assert any(d.code == "history_stale" for d in validate_schedule_result(schedule).diagnostics)


def test_individual_workday_requires_exact_confirmation(minimal_employees):
    employee = minimal_employees[0]
    schedule = draft(context(minimal_employees))
    assign(schedule, employee, 0, ShiftType.WORKDAY)
    schedule.days[0].workday_hours[employee.name] = 3
    result = validate_schedule_result(schedule)
    assert any(d.approval_rule == "individual_workday" and d.value == 3 for d in result.diagnostics)
    schedule.config.approvals = [
        RuleApproval(
            employee_name=employee.name,
            date=date(2026, 4, 1),
            rule="individual_workday",
            purpose="monthly_norm",
            value=3,
        )
    ]
    assert not any(
        d.approval_rule == "individual_workday"
        for d in validate_schedule_result(schedule).diagnostics
    )


@pytest.mark.parametrize("solver", ["greedy", "cpsat"])
def test_engines_return_ready_only_with_exact_hours_and_shared_rules(minimal_employees, solver):
    if solver == "cpsat":
        pytest.importorskip("ortools")
    config = context(minimal_employees)
    config.solver = solver
    schedule = generate_schedule(config)
    assert schedule.status == "ready", [(d.code, d.detail) for d in schedule.diagnostics]
    assert all(day.is_covered() for day in schedule.days)
    assert all(not day.vacation and not day.sick_leave for day in schedule.days)
    assert validate_schedule_result(schedule).status == "ready"


@pytest.mark.parametrize("solver", ["greedy", "cpsat"])
def test_empty_night_pool_returns_diagnostic_not_false_success(minimal_employees, solver):
    if solver == "cpsat":
        pytest.importorskip("ortools")
    for employee in minimal_employees[-2:]:
        employee.unavailable_dates = [date(2026, 4, 1)]
    config = context(minimal_employees)
    config.solver = solver
    schedule = generate_schedule(config)
    assert schedule.status == "diagnostic"
    assert any(d.code == "coverage" and d.date == date(2026, 4, 1) for d in schedule.diagnostics)
    assert not any(employee.name in schedule.days[0].night for employee in minimal_employees[-2:])


def test_greedy_can_reach_duty_only_norm_without_optional_solver(planning_config):
    from unittest.mock import patch

    planning_config.employees[0].morning_only = True
    with patch("duty_schedule.scheduler.solver._HAS_ORTOOLS", False):
        result = generate_schedule(planning_config)
    assert result.status == "ready", [(d.code, d.detail) for d in result.diagnostics]
    name = planning_config.employees[0].name
    assert sum(name in day.morning for day in result.days) == 22
    assert all(name not in day.workday for day in result.days)


def test_full_norm_after_short_absence_proposes_individual_r_confirmation(planning_config):
    from duty_schedule.models import NormChoice

    employee = planning_config.employees[0]
    planning_config.production_calendar.days[-1].kind = "short"
    employee.sick_leaves = [VacationPeriod(start=date(2026, 4, 30), end=date(2026, 4, 30))]
    planning_config.norm_choices = [
        NormChoice(employee_name=employee.name, year=2026, month=4, mode="full")
    ]
    result = generate_schedule(planning_config)
    assert result.status == "diagnostic"
    requests = [d for d in result.diagnostics if d.approval_rule == "individual_workday"]
    assert requests
    assert not any(d.code == "monthly_hours" for d in result.diagnostics)
    for request in result.diagnostics:
        if request.approval_rule:
            result.config.approvals.append(
                RuleApproval(
                    employee_name=request.employee_name,
                    date=request.date,
                    rule=request.approval_rule,
                    value=request.value,
                    purpose="monthly_norm",
                )
            )
    assert validate_schedule_result(result).status == "ready"


def test_typed_config_rejects_shared_employee_id(minimal_employees):
    from pydantic import ValidationError

    minimal_employees[1].employee_id = minimal_employees[0].employee_id
    with pytest.raises(ValidationError, match="идентификатор"):
        Config(year=2026, month=4, employees=minimal_employees)


@pytest.mark.parametrize("solver", ["greedy", "cpsat"])
def test_role_limits_are_preserved_by_both_engines(planning_config, solver):
    planning_config.solver = solver
    planning_config.employees[0].morning_only = True
    planning_config.employees[0].always_on_duty = True
    planning_config.employees[1].evening_only = True
    planning_config.employees[2].on_duty = False
    result = generate_schedule(planning_config)
    assert result.status == "ready", [(d.code, d.detail) for d in result.diagnostics]
    for day in result.days:
        assert "M0" not in day.evening + day.workday + day.night
        assert "M1" not in day.morning + day.workday + day.night
        assert "M2" not in day.morning + day.evening + day.night


def test_legacy_priority_does_not_change_agreed_greedy_quality_order(planning_config):
    from duty_schedule.models import OptimizationPriority

    baseline = generate_schedule(planning_config)
    planning_config.optimization_priority = OptimizationPriority.EVENING_SHIFTS
    result = generate_schedule(planning_config)
    assert [day.model_dump() for day in result.days] == [day.model_dump() for day in baseline.days]


def _streak_boundary_config(config: Config) -> Config:
    result = config.model_copy(deep=True)
    employee = result.employees[0]
    result.carry_over[0] = CarryOverState(
        employee_name=employee.name,
        employee_id=employee.employee_id,
        as_of=date(2026, 3, 31),
        source="manual",
        last_shift=ShiftType.WORKDAY,
        consecutive_working=6,
        consecutive_same_shift=1,
    )
    result.pins = [
        PinnedAssignment(
            date=date(2026, 4, 1), employee_name=employee.name, shift=ShiftType.MORNING
        )
    ]
    return result


@pytest.mark.parametrize("lower_name", ["M0", "M1"])
@pytest.mark.parametrize("reverse", [False, True])
def test_solver_streak_approvals_are_order_independent(
    planning_config: Config, lower_name: str, reverse: bool
) -> None:
    pytest.importorskip("ortools")
    from duty_schedule.scheduler.solver import solve_schedule

    config = _streak_boundary_config(planning_config)
    config.approvals = [
        RuleApproval(
            employee_name=lower_name,
            date=date(2026, 4, 1),
            rule="working_streak",
            purpose="coverage",
            value=6,
        ),
        RuleApproval(
            employee_name="M0",
            date=date(2026, 4, 1),
            rule="working_streak",
            purpose="monthly_norm",
            value=7,
        ),
    ]
    if reverse:
        config.approvals.reverse()
    result = solve_schedule(config, timeout=5)
    assert result.status == "ready", [(d.code, d.detail) for d in result.diagnostics]
    assert "M0" in result.days[0].morning


@pytest.mark.parametrize("mismatch", ["name", "employee_id", "date"])
def test_solver_cannot_apply_unmatched_streak_approval(
    planning_config: Config, mismatch: str
) -> None:
    pytest.importorskip("ortools")
    from duty_schedule.scheduler.solver import solve_schedule

    config = _streak_boundary_config(planning_config)
    config.approvals = [
        RuleApproval(
            employee_name="M1" if mismatch == "name" else "M0",
            employee_id=config.employees[1].employee_id if mismatch == "employee_id" else None,
            date=date(2026, 4, 2) if mismatch == "date" else date(2026, 4, 1),
            rule="working_streak",
            purpose="coverage",
            value=7,
        )
    ]
    result = solve_schedule(config, timeout=5)
    assert result.search_status == "infeasible"
    assert result.status == "diagnostic"


def test_solver_streak_approval_cannot_reduce_normal_limit(planning_config: Config) -> None:
    pytest.importorskip("ortools")
    from duty_schedule.scheduler.solver import solve_schedule

    config = _streak_boundary_config(planning_config)
    config.carry_over[0].consecutive_working = 5
    config.approvals = [
        RuleApproval(
            employee_name="M0",
            date=date(2026, 4, 1),
            rule="working_streak",
            purpose="coverage",
            value=5,
        )
    ]
    result = solve_schedule(config, timeout=5)
    assert result.status == "ready", [(d.code, d.detail) for d in result.diagnostics]


@pytest.mark.parametrize("restriction", ["five_two", "unavailable", "weekly_off", "pinned_off"])
def test_off_duty_quality_balances_only_available_employees(
    minimal_employees: list[Employee], restriction: str
) -> None:
    from duty_schedule.scheduler.postprocess.quality import quality_key

    config = context(minimal_employees)
    assert config.production_calendar is not None
    employee = config.employees[0]
    off_dates = sorted(config.production_calendar.off_dates())
    if restriction == "five_two":
        employee.schedule_type = ScheduleType.FIVE_TWO
    elif restriction == "unavailable":
        employee.unavailable_dates = off_dates
    elif restriction == "weekly_off":
        employee.days_off_weekly = [5, 6]
    else:
        config.pins = [
            PinnedAssignment(date=day, employee_name=employee.name, shift=ShiftType.DAY_OFF)
            for day in off_dates
        ]
    names = [employee.name for employee in config.employees[1:4]]
    balanced_pairs = [(0, 1), (0, 2), (1, 2), (0, 1), (0, 2), (1, 2), (0, 2), (1, 2)]
    uneven_pairs = [(0, 2)] * 4 + [(1, 2)] * 4

    def candidate(pairs: list[tuple[int, int]]) -> Schedule:
        return Schedule(
            config=config,
            days=[
                DaySchedule(date=day, morning=[names[a]], evening=[names[b]])
                for day, (a, b) in zip(off_dates, pairs, strict=True)
            ],
        )

    assert quality_key(candidate(balanced_pairs))[-1] < quality_key(candidate(uneven_pairs))[-1]


def test_solver_off_duty_balance_ignores_weekday_only_duty_role(planning_config: Config) -> None:
    pytest.importorskip("ortools")
    from duty_schedule.scheduler.rules import assignment_for
    from duty_schedule.scheduler.solver import solve_schedule

    config = planning_config.model_copy(deep=True)
    config.employees[0].schedule_type = ScheduleType.FIVE_TWO
    config.employees[0].on_duty = False
    baseline = generate_schedule(config)
    assert baseline.status == "ready"
    config.pins = [
        PinnedAssignment(
            date=day.date, employee_name=employee.name, shift=assignment_for(day, employee.name)
        )
        for day in baseline.days
        for employee in config.employees
    ]
    weekday_worker = solve_schedule(config, timeout=5)
    config.employees[0].on_duty = True
    weekday_duty_worker = solve_schedule(config, timeout=5)
    assert weekday_worker.status == weekday_duty_worker.status == "ready"
    assert weekday_worker.search_status == weekday_duty_worker.search_status == "optimal"
    assert (
        weekday_worker.metadata["objective_values"][-1]
        == weekday_duty_worker.metadata["objective_values"][-1]
    )
