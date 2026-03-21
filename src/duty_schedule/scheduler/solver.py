from __future__ import annotations

import calendar
from datetime import date

from duty_schedule.logging import get_logger
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Schedule,
    ScheduleType,
)

logger = get_logger(__name__)

try:
    from ortools.sat.python import cp_model

    _HAS_ORTOOLS = True
except ImportError:
    _HAS_ORTOOLS = False


SOLVER_TIMEOUT_S = 30


class SolverUnavailableError(Exception):
    pass


def solve_schedule(
    config: Config,
    holidays: set[date],
    timeout: int = SOLVER_TIMEOUT_S,
) -> Schedule:
    if not _HAS_ORTOOLS:
        raise SolverUnavailableError("OR-Tools не установлен. Установите: pip install ortools")

    _, ndays = calendar.monthrange(config.year, config.month)
    dates = [date(config.year, config.month, d) for d in range(1, ndays + 1)]

    employees = config.employees
    emp_idx = {e.name: i for i, e in enumerate(employees)}

    moscow_duty = [e for e in employees if e.city == City.MOSCOW and e.on_duty]
    khab_duty = [e for e in employees if e.city == City.KHABAROVSK and e.on_duty]

    shifts = ["morning", "evening", "night", "workday", "day_off", "vacation"]

    logger.info("solver_start", employees=len(employees), days=ndays, timeout=timeout)

    model = cp_model.CpModel()

    x = {}
    for d_idx in range(len(dates)):
        for e_idx in range(len(employees)):
            for s in shifts:
                x[(d_idx, e_idx, s)] = model.new_bool_var(f"x_{d_idx}_{e_idx}_{s}")

    for d_idx in range(len(dates)):
        for e_idx in range(len(employees)):
            model.add_exactly_one(x[(d_idx, e_idx, s)] for s in shifts)

    for d_idx, d in enumerate(dates):
        for e_idx, emp in enumerate(employees):
            if emp.is_on_vacation(d):
                model.add(x[(d_idx, e_idx, "vacation")] == 1)
            elif emp.is_blocked(d) or emp.is_day_off_weekly(d):
                model.add(x[(d_idx, e_idx, "day_off")] == 1)

    for d_idx, d in enumerate(dates):
        is_weekend = d.weekday() >= 5 or d in holidays
        for e_idx, emp in enumerate(employees):
            if emp.schedule_type == ScheduleType.FIVE_TWO and is_weekend:
                model.add(x[(d_idx, e_idx, "day_off")] == 1)

    for d_idx in range(len(dates)):
        for e_idx, emp in enumerate(employees):
            if emp.city == City.MOSCOW:
                model.add(x[(d_idx, e_idx, "night")] == 0)
            if emp.city == City.KHABAROVSK:
                model.add(x[(d_idx, e_idx, "morning")] == 0)
                model.add(x[(d_idx, e_idx, "evening")] == 0)

    for d_idx in range(len(dates)):
        for e_idx, emp in enumerate(employees):
            if not emp.on_duty:
                model.add(x[(d_idx, e_idx, "morning")] == 0)
                model.add(x[(d_idx, e_idx, "evening")] == 0)
                model.add(x[(d_idx, e_idx, "night")] == 0)
            if emp.morning_only:
                model.add(x[(d_idx, e_idx, "evening")] == 0)
            if emp.evening_only:
                model.add(x[(d_idx, e_idx, "morning")] == 0)

    for d_idx, d in enumerate(dates):
        morning_vars = [
            x[(d_idx, emp_idx[e.name], "morning")]
            for e in moscow_duty
            if not employees[emp_idx[e.name]].is_blocked(d)
            and not employees[emp_idx[e.name]].is_on_vacation(d)
        ]
        evening_vars = [
            x[(d_idx, emp_idx[e.name], "evening")]
            for e in moscow_duty
            if not employees[emp_idx[e.name]].is_blocked(d)
            and not employees[emp_idx[e.name]].is_on_vacation(d)
        ]
        night_vars = [
            x[(d_idx, emp_idx[e.name], "night")]
            for e in khab_duty
            if not employees[emp_idx[e.name]].is_blocked(d)
            and not employees[emp_idx[e.name]].is_on_vacation(d)
        ]

        if morning_vars:
            model.add(sum(morning_vars) >= 1)
        if evening_vars:
            model.add(sum(evening_vars) >= 1)
        if night_vars:
            model.add(sum(night_vars) >= 1)

    for d_idx in range(len(dates) - 1):
        for e_idx in range(len(employees)):
            model.add(
                x[(d_idx, e_idx, "evening")]
                + x[(d_idx + 1, e_idx, "morning")]
                + x[(d_idx + 1, e_idx, "workday")]
                <= 1
            )

    for e_idx, emp in enumerate(employees):
        max_cw = emp.max_consecutive_working or 5
        for start in range(len(dates) - max_cw):
            window = range(start, start + max_cw + 1)
            if start + max_cw >= len(dates):
                break
            work_vars = []
            for d_idx in window:
                for s in ["morning", "evening", "night", "workday"]:
                    work_vars.append(x[(d_idx, e_idx, s)])
            model.add(sum(work_vars) <= max_cw)

    for pin in config.pins:
        d_idx_pin = (pin.date - dates[0]).days
        if 0 <= d_idx_pin < len(dates):
            e_idx_pin = emp_idx.get(pin.employee_name)
            if e_idx_pin is not None:
                model.add(x[(d_idx_pin, e_idx_pin, pin.shift.value)] == 1)

    production_days = sum(1 for d in dates if d.weekday() < 5 and d not in holidays)

    objective_terms = []

    for e_idx, _emp in enumerate(employees):
        target = production_days
        work_total = sum(
            x[(d, e_idx, s)]
            for d in range(len(dates))
            for s in ["morning", "evening", "night", "workday"]
        )
        dev = model.new_int_var(0, len(dates), f"dev_{e_idx}")
        model.add(work_total - target <= dev)
        model.add(target - work_total <= dev)
        objective_terms.append(dev * 10)

    for e_idx in range(len(employees)):
        for d_idx in range(1, len(dates) - 1):
            is_off = x[(d_idx, e_idx, "day_off")]
            prev_work = sum(
                x[(d_idx - 1, e_idx, s)] for s in ["morning", "evening", "night", "workday"]
            )
            next_work = sum(
                x[(d_idx + 1, e_idx, s)] for s in ["morning", "evening", "night", "workday"]
            )
            isolated = model.new_bool_var(f"iso_{e_idx}_{d_idx}")
            model.add(is_off >= 1).only_enforce_if(isolated)
            model.add(prev_work >= 1).only_enforce_if(isolated)
            model.add(next_work >= 1).only_enforce_if(isolated)
            model.add(is_off == 0).only_enforce_if(isolated.negated())
            objective_terms.append(isolated * 5)

    for e_idx, emp in enumerate(employees):
        if emp.preferred_shift is None:
            continue
        pref = emp.preferred_shift.value
        if pref not in ("morning", "evening", "night"):
            continue
        for d_idx in range(len(dates)):
            for s in ("morning", "evening", "night"):
                if s != pref:
                    objective_terms.append(x[(d_idx, e_idx, s)] * 3)

    model.minimize(sum(objective_terms))

    proto = model.Proto()
    logger.debug(
        "solver_model_built",
        num_variables=len(proto.variables),
        num_constraints=len(proto.constraints),
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        from duty_schedule.scheduler.core import ScheduleError

        logger.error("solver_no_solution", status=solver.status_name(status))
        raise ScheduleError(
            f"CP-SAT solver не нашёл решения (статус: {solver.status_name(status)})"
        )

    duration_ms = round(solver.wall_time * 1000, 1)
    timed_out = status == cp_model.FEASIBLE and solver.wall_time >= timeout * 0.95
    logger.info(
        "solver_finished",
        status=solver.status_name(status),
        objective=solver.objective_value,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )

    days: list[DaySchedule] = []
    for d_idx, d in enumerate(dates):
        morning_names: list[str] = []
        evening_names: list[str] = []
        night_names: list[str] = []
        workday_names: list[str] = []
        day_off_names: list[str] = []
        vacation_names: list[str] = []

        for e_idx, emp in enumerate(employees):
            for s, lst in [
                ("morning", morning_names),
                ("evening", evening_names),
                ("night", night_names),
                ("workday", workday_names),
                ("day_off", day_off_names),
                ("vacation", vacation_names),
            ]:
                if solver.value(x[(d_idx, e_idx, s)]):
                    lst.append(emp.name)

        days.append(
            DaySchedule(
                date=d,
                is_holiday=d in holidays,
                morning=morning_names,
                evening=evening_names,
                night=night_names,
                workday=workday_names,
                day_off=day_off_names,
                vacation=vacation_names,
            )
        )

    metadata: dict = {
        "solver": "cpsat",
        "solver_status": solver.status_name(status),
        "objective_value": solver.objective_value,
        "production_working_days": production_days,
        "holidays_count": sum(1 for d in dates if d in holidays),
        "total_mornings": sum(len(d.morning) for d in days),
        "total_evenings": sum(len(d.evening) for d in days),
        "total_nights": sum(len(d.night) for d in days),
    }

    return Schedule(config=config, days=days, metadata=metadata)
