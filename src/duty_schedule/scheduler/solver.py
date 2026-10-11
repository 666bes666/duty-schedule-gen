from __future__ import annotations

from datetime import date
from typing import Any

from duty_schedule.calendar import calendar_for_config
from duty_schedule.constants import MAX_CONSECUTIVE_WORKING_DEFAULT
from duty_schedule.logging import get_logger
from duty_schedule.models import Config, DaySchedule, Schedule, ShiftType
from duty_schedule.scheduler.postprocess.quality import eligible_duty_names
from duty_schedule.scheduler.rules import (
    ALL_SHIFTS,
    WORKING_SHIFTS,
    approval_for,
    can_assign_work,
    carry_for_employee,
    matches_employee,
    normal_streak_limit,
)
from duty_schedule.workload import calculate_monthly_targets

logger = get_logger(__name__)

try:
    from ortools.sat.python import cp_model

    _HAS_ORTOOLS = True
except ImportError:
    _HAS_ORTOOLS = False

SOLVER_TIMEOUT_S = 10


class SolverUnavailableError(Exception):
    pass


def solve_schedule(
    config: Config,
    holidays: set[date] | None = None,
    timeout: int = SOLVER_TIMEOUT_S,
    allow_pending: bool = False,
) -> Schedule:
    if not _HAS_ORTOOLS:
        raise SolverUnavailableError("OR-Tools не установлен. Установите: uv sync --extra solver")
    from duty_schedule.scheduler.validation import validate_schedule_result

    calendar = calendar_for_config(config, holidays)
    config = config.model_copy(deep=True, update={"production_calendar": calendar})
    dates = sorted(record.date for record in calendar.days)
    employees = config.employees
    targets = calculate_monthly_targets(config, calendar)
    model = cp_model.CpModel()
    variables: dict[tuple[int, int, ShiftType], Any] = {}
    work: dict[tuple[int, int], Any] = {}
    r_hours: dict[tuple[int, int], Any] = {}
    streaks: dict[tuple[int, int], Any] = {}
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    pending_terms: list[Any] = []
    isolated_terms: list[Any] = []
    streak_terms: list[Any] = []
    fairness_terms: list[Any] = []
    weekend_terms: list[Any] = []
    logger.info("solver_start", employees=len(employees), days=len(dates), timeout=timeout)

    for employee_index, employee in enumerate(employees):
        carry = carry_for_employee(config, employee)
        previous_streak: Any = carry.consecutive_working if carry else 0
        previous_evening: Any = int(carry is not None and carry.last_shift == ShiftType.EVENING)
        employee_hours = []
        for day_index, day in enumerate(dates):
            for shift in ALL_SHIFTS:
                variables[day_index, employee_index, shift] = model.new_bool_var(
                    f"assignment_{day_index}_{employee_index}_{shift.value}"
                )
            model.add_exactly_one(variables[day_index, employee_index, s] for s in ALL_SHIFTS)
            w = model.new_bool_var(f"working_{day_index}_{employee_index}")
            work[day_index, employee_index] = w
            model.add(w == sum(variables[day_index, employee_index, s] for s in WORKING_SHIFTS))
            absent = None
            if employee.is_on_sick_leave(day):
                absent = ShiftType.SICK_LEAVE
            elif employee.is_on_vacation(day):
                absent = ShiftType.VACATION
            for shift in (ShiftType.VACATION, ShiftType.SICK_LEAVE):
                model.add(variables[day_index, employee_index, shift] == int(shift == absent))
            for shift in WORKING_SHIFTS:
                if not can_assign_work(
                    config, calendar, employee, day, shift, None, 0, allow_pending=True
                ):
                    model.add(variables[day_index, employee_index, shift] == 0)
            if employee.is_day_off_weekly(day) and not approval_for(
                config, employee, day, "weekly_day_off"
            ):
                if allow_pending:
                    pending_terms.append(w)
                else:
                    model.add(w == 0)
            current_streak = model.new_int_var(0, 7, f"streak_{day_index}_{employee_index}")
            streaks[day_index, employee_index] = current_streak
            model.add(current_streak == previous_streak + 1).only_enforce_if(w)
            model.add(current_streak == 0).only_enforce_if(w.negated())
            normal = min(normal_streak_limit(employee), MAX_CONSECUTIVE_WORKING_DEFAULT)
            approved_limit = max(
                (
                    item.value
                    for item in config.approvals
                    if item.rule == "working_streak"
                    and item.date == day
                    and item.value is not None
                    and matches_employee(item.employee_name, item.employee_id, employee)
                ),
                default=normal,
            )
            limit = max(normal, approved_limit)
            if allow_pending:
                violation = model.new_bool_var(f"streak_confirmation_{day_index}_{employee_index}")
                model.add(current_streak > limit).only_enforce_if(violation)
                model.add(current_streak <= limit).only_enforce_if(violation.negated())
                pending_terms.append(violation)
            else:
                model.add(current_streak <= limit)
            model.add(
                previous_evening + variables[day_index, employee_index, ShiftType.MORNING] <= 1
            )
            model.add(
                previous_evening + variables[day_index, employee_index, ShiftType.WORKDAY] <= 1
            )
            previous_streak = current_streak
            previous_evening = variables[day_index, employee_index, ShiftType.EVENING]
            squared = model.new_int_var(0, 49, f"streak_cost_{day_index}_{employee_index}")
            model.add_multiplication_equality(squared, [current_streak, current_streak])
            streak_terms.append(squared)
            base_hours = calendar.hours(day) or 8
            pin = pins.get((day, employee.name))
            if pin:
                model.add(variables[day_index, employee_index, pin.shift] == 1)
            allowed_hours = {0, base_hours}
            allowed_hours.update(
                item.value
                for item in config.approvals
                if item.rule == "individual_workday"
                and item.date == day
                and item.value is not None
                and item.value <= base_hours
                and approval_for(config, employee, day, "individual_workday", item.value)
            )
            if pin and pin.working_hours is not None:
                allowed_hours.add(pin.working_hours)
            if allow_pending:
                allowed_hours.update(range(1, base_hours + 1))
            hours = model.new_int_var_from_domain(
                cp_model.Domain.from_values(sorted(allowed_hours)),
                f"workday_hours_{day_index}_{employee_index}",
            )
            r_hours[day_index, employee_index] = hours
            r = variables[day_index, employee_index, ShiftType.WORKDAY]
            model.add(hours == 0).only_enforce_if(r.negated())
            model.add(hours >= 1).only_enforce_if(r)
            model.add(hours <= base_hours)
            if pin and pin.working_hours is not None:
                model.add(hours == pin.working_hours)
            if allow_pending:
                individual = model.new_bool_var(f"individual_{day_index}_{employee_index}")
                explicit = pin is not None and pin.working_hours is not None
                model.add_allowed_assignments(
                    [hours, individual],
                    [
                        (
                            value,
                            int(
                                value > 0
                                and (value != base_hours or explicit)
                                and approval_for(config, employee, day, "individual_workday", value)
                                is None
                            ),
                        )
                        for value in allowed_hours
                    ],
                )
                pending_terms.append(individual)
            employee_hours.append(
                hours
                + base_hours
                * sum(
                    variables[day_index, employee_index, s]
                    for s in (
                        ShiftType.MORNING,
                        ShiftType.EVENING,
                        ShiftType.NIGHT,
                    )
                )
            )
        model.add(sum(employee_hours) == targets[employee.name].selected_hours)
        for day_index in range(len(dates)):
            current_off = 1 - work[day_index, employee_index]
            previous_work = (
                work[day_index - 1, employee_index]
                if day_index
                else int(carry is not None and carry.last_shift in WORKING_SHIFTS)
            )
            next_work = work[day_index + 1, employee_index] if day_index + 1 < len(dates) else 0
            isolated = model.new_bool_var(f"isolated_{day_index}_{employee_index}")
            model.add(isolated <= current_off)
            model.add(isolated <= previous_work)
            model.add(isolated <= next_work)
            model.add(isolated >= current_off + previous_work + next_work - 2)
            isolated_terms.append(isolated)

    for day_index, _day in enumerate(dates):
        for shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT):
            model.add(sum(variables[day_index, e, shift] for e in range(len(employees))) >= 1)
    for shift in (ShiftType.EVENING, ShiftType.NIGHT):
        eligible_names = eligible_duty_names(
            config, calendar, dates, (shift,), allow_pending=allow_pending
        )
        eligible = [
            e
            for e, employee in enumerate(employees)
            if targets[employee.name].selected_hours > 0 and employee.name in eligible_names
        ]
        total_target = sum(targets[employees[e].name].selected_hours for e in eligible)
        total_count = sum(variables[d, e, shift] for d in range(len(dates)) for e in eligible)
        for e in eligible:
            count = sum(variables[d, e, shift] for d in range(len(dates)))
            deviation = model.new_int_var(
                0, len(dates) * max(total_target, 1) * len(employees), f"balance_{shift.value}_{e}"
            )
            model.add_abs_equality(
                deviation,
                count * total_target - total_count * targets[employees[e].name].selected_hours,
            )
            fairness_terms.append(deviation)
    off_duty_names = eligible_duty_names(
        config,
        calendar,
        sorted(calendar.off_dates()),
        (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT),
        allow_pending=allow_pending,
    )
    for city in {employee.city for employee in employees}:
        eligible = [
            e
            for e, employee in enumerate(employees)
            if employee.city == city
            and employee.name in off_duty_names
            and targets[employee.name].selected_hours > 0
        ]
        total_target = sum(targets[employees[e].name].selected_hours for e in eligible)
        counts = {
            e: sum(
                variables[d, e, shift]
                for d, day in enumerate(dates)
                if not calendar.is_working(day)
                for shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT)
            )
            for e in eligible
        }
        total_count = sum(counts.values())
        for e in eligible:
            deviation = model.new_int_var(
                0,
                len(dates) * max(total_target, 1) * len(employees),
                f"weekend_balance_{city.value}_{e}",
            )
            model.add_abs_equality(
                deviation,
                counts[e] * total_target - total_count * targets[employees[e].name].selected_hours,
            )
            weekend_terms.append(deviation)

    longest = model.new_int_var(0, 7, "longest_working_streak")
    model.add_max_equality(longest, list(streaks.values()))
    layers = [
        sum(pending_terms),
        sum(isolated_terms),
        longest * 100000 + sum(streak_terms),
        sum(fairness_terms),
        sum(weekend_terms),
    ]
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(timeout / 5, 0.01)
    solver.parameters.random_seed = config.seed
    solver.parameters.num_search_workers = 1
    best_days: list[DaySchedule] | None = None
    final_status = "timeout"
    objective_values: list[int] = []
    elapsed = 0.0
    for layer in layers:
        model.minimize(layer)
        status = solver.solve(model)
        elapsed += solver.wall_time
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if best_days is None:
                final_status = (
                    "infeasible"
                    if status == cp_model.INFEASIBLE
                    else "model_invalid"
                    if status == cp_model.MODEL_INVALID
                    else "timeout"
                )
            break
        best_days = []
        for d, day in enumerate(dates):
            schedule_day = DaySchedule(date=day, is_holiday=not calendar.is_working(day))
            for e, employee in enumerate(employees):
                for shift in ALL_SHIFTS:
                    if solver.value(variables[d, e, shift]):
                        getattr(schedule_day, shift.value).append(employee.name)
                        if shift == ShiftType.WORKDAY:
                            calculated_hours = solver.value(r_hours[d, e])
                            pin = pins.get((day, employee.name))
                            if (
                                calculated_hours != (calendar.hours(day) or 8)
                                or pin
                                and pin.working_hours is not None
                            ):
                                schedule_day.workday_hours[employee.name] = calculated_hours
            best_days.append(schedule_day)
        final_status = "optimal" if status == cp_model.OPTIMAL else "feasible"
        objective_values.append(round(solver.objective_value))
        if status != cp_model.OPTIMAL:
            break
        model.add(layer == round(solver.objective_value))
    if best_days is not None and len(objective_values) < len(layers):
        final_status = "feasible"
    if best_days is None:
        best_days = []
        for day in dates:
            schedule_day = DaySchedule(date=day, is_holiday=not calendar.is_working(day))
            for employee in employees:
                shift = (
                    ShiftType.SICK_LEAVE
                    if employee.is_on_sick_leave(day)
                    else ShiftType.VACATION
                    if employee.is_on_vacation(day)
                    else ShiftType.DAY_OFF
                )
                pin = pins.get((day, employee.name))
                if pin:
                    shift = pin.shift
                    if pin.working_hours is not None:
                        schedule_day.workday_hours[employee.name] = pin.working_hours
                getattr(schedule_day, shift.value).append(employee.name)
            best_days.append(schedule_day)
    result = validate_schedule_result(
        Schedule(
            config=config,
            days=best_days,
            search_status=final_status,
            metadata={
                "solver": "cpsat",
                "solver_status": final_status.upper(),
                "objective_values": objective_values,
                "duration_ms": round(elapsed * 1000, 1),
            },
        )
    )
    if allow_pending and any(d.code == "approval_required" for d in result.diagnostics):
        result.search_status = "pending_approval"
    logger.info(
        "solver_finished",
        status=final_status,
        duration_ms=round(elapsed * 1000, 1),
        ready=result.status == "ready",
    )
    return result
