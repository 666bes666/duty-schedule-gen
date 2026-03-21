from __future__ import annotations

import copy
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from duty_schedule.constants import (
    MAX_BACKTRACK_ATTEMPTS,
    MAX_BACKTRACK_DAYS,
)
from duty_schedule.logging import get_logger
from duty_schedule.models import (
    Config,
    DaySchedule,
    OptimizationPriority,
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
    holidays: set[date],
) -> Schedule:
    if config.solver == "cpsat":
        from duty_schedule.scheduler.solver import SolverUnavailableError, solve_schedule

        try:
            return solve_schedule(config, holidays)
        except SolverUnavailableError:
            logger.warning("cpsat_unavailable_greedy_fallback")

    from duty_schedule.calendar import get_all_days
    from duty_schedule.scheduler.changelog import ChangeLog
    from duty_schedule.scheduler.constraints import (
        _calc_blocked_working_days,
        _calc_production_days,
        _is_working_on_day,
    )
    from duty_schedule.scheduler.greedy import _build_day
    from duty_schedule.scheduler.postprocess import (
        _balance_duty_shifts,
        _balance_evening_shifts,
        _balance_weekend_work,
        _break_evening_isolated_pattern,
        _equalize_isolated_off,
        _minimize_isolated_off,
        _minimize_max_streak,
        _target_adjustment_pass,
        _trim_long_off_blocks,
    )

    rng = random.Random(config.seed)
    all_days = get_all_days(config.year, config.month)
    employees = config.employees

    pins_by_date: dict[date, dict[str, ShiftType]] = {}
    for pin in config.pins:
        pins_by_date.setdefault(pin.date, {})[pin.employee_name] = pin.shift
    pinned_on: set[tuple[date, str]] = {(p.date, p.employee_name) for p in config.pins}

    production_days = _calc_production_days(config.year, config.month, holidays)
    logger.info("production_days_calculated", production_days=production_days)
    logger.debug(
        "scheduler_config",
        solver=config.solver,
        seed=config.seed,
        employees=len(employees),
        max_backtrack_attempts=MAX_BACKTRACK_ATTEMPTS,
        max_backtrack_days=MAX_BACKTRACK_DAYS,
    )

    states: dict[str, EmployeeState] = {}
    for emp in employees:
        vac_days = _calc_blocked_working_days(emp, config.year, config.month)
        target = production_days
        states[emp.name] = EmployeeState(
            target_working_days=target,
            vacation_days=vac_days,
        )

    carry_over_by_name = {c.employee_name: c for c in config.carry_over}
    for emp in employees:
        if emp.name in carry_over_by_name:
            co = carry_over_by_name[emp.name]
            if co.last_shift is not None:
                states[emp.name].last_shift = co.last_shift
            states[emp.name].consecutive_working = co.consecutive_working
            states[emp.name].consecutive_off = co.consecutive_off
            if co.consecutive_same_shift > 0 and co.last_shift is not None:
                if co.last_shift == ShiftType.MORNING:
                    states[emp.name].consecutive_morning = co.consecutive_same_shift
                elif co.last_shift == ShiftType.EVENING:
                    states[emp.name].consecutive_evening = co.consecutive_same_shift
                elif co.last_shift == ShiftType.WORKDAY:
                    states[emp.name].consecutive_workday = co.consecutive_same_shift

    initial_cw: dict[str, int] = {
        emp.name: states[emp.name].consecutive_working for emp in employees
    }
    initial_last_shift: dict[str, ShiftType] = {
        emp.name: ls for emp in employees if (ls := states[emp.name].last_shift) is not None
    }

    days: list[DaySchedule] = []
    backtrack_stack: list[tuple[date, dict[str, EmployeeState]]] = []

    day_idx = 0
    total_backtracks = 0

    while day_idx < len(all_days):
        day = all_days[day_idx]
        saved_states = copy.deepcopy(states)
        remaining_days = len(all_days) - day_idx

        try:
            _next_day = day + timedelta(days=1)
            ds = _build_day(
                day,
                employees,
                states,
                holidays,
                rng,
                remaining_days,
                pins_today=pins_by_date.get(day),
                pins_tomorrow=pins_by_date.get(_next_day),
            )
            days.append(ds)
            backtrack_stack.append((day, saved_states))
            day_idx += 1

        except ScheduleError as exc:
            logger.warning(
                "shift_assignment_backtrack",
                day=str(day),
                reason=str(exc),
                backtrack_number=total_backtracks + 1,
                steps_back=min(MAX_BACKTRACK_DAYS, len(backtrack_stack)),
            )
            total_backtracks += 1

            if total_backtracks > MAX_BACKTRACK_ATTEMPTS or len(backtrack_stack) < 1:
                logger.error(
                    "schedule_build_failed",
                    total_backtracks=total_backtracks,
                    last_day=str(day),
                )
                raise ScheduleError(
                    f"Расписание не может быть построено: {exc}\n"
                    f"Откатов всего: {total_backtracks}. Проверьте параметры сотрудников."
                ) from exc

            steps_back = min(MAX_BACKTRACK_DAYS, len(backtrack_stack))
            for _ in range(steps_back):
                if backtrack_stack:
                    _, states = backtrack_stack.pop()
                    days.pop()
                    day_idx -= 1

            rng = random.Random(config.seed + total_backtracks * 1000 + day_idx)

    changelog = ChangeLog()

    from duty_schedule.scheduler.postprocess.metrics import compute_snapshot

    def _pp(stage: str, func: Any, *args: Any, **kwargs: Any) -> Any:
        pre = len(changelog.entries)
        before = compute_snapshot(days, employees, holidays)
        result = func(*args, **kwargs)
        after = compute_snapshot(result if isinstance(result, list) else days, employees, holidays)
        logger.debug(
            "postprocess_stage_done",
            stage=stage,
            changes=len(changelog.entries) - pre,
            score_before=round(before.score(), 1),
            score_after=round(after.score(), 1),
            iso_off_delta=after.isolated_off_total - before.isolated_off_total,
            evening_bal_delta=after.evening_balance - before.evening_balance,
        )
        return result

    days = _pp(
        "balance_weekend_work",
        _balance_weekend_work,
        days,
        employees,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        changelog=changelog,
    )
    for emp in employees:
        states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))

    days = _pp(
        "balance_duty_shifts",
        _balance_duty_shifts,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        changelog=changelog,
    )
    days = _pp(
        "balance_evening_1",
        _balance_evening_shifts,
        days,
        employees,
        pinned_on=pinned_on,
        changelog=changelog,
    )
    days = _pp(
        "target_adjustment_1",
        _target_adjustment_pass,
        days,
        employees,
        states,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    days = _pp(
        "trim_long_off_blocks",
        _trim_long_off_blocks,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    for emp in employees:
        states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))
    days = _pp(
        "target_adjustment_2",
        _target_adjustment_pass,
        days,
        employees,
        states,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    days = _pp(
        "minimize_isolated_off_1",
        _minimize_isolated_off,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    days = _pp(
        "break_evening_isolated_pattern",
        _break_evening_isolated_pattern,
        days,
        employees,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        changelog=changelog,
    )
    days = _pp(
        "minimize_isolated_off_2",
        _minimize_isolated_off,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    days = _pp(
        "equalize_isolated_off",
        _equalize_isolated_off,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        changelog=changelog,
    )
    days = _pp(
        "minimize_isolated_off_3",
        _minimize_isolated_off,
        days,
        employees,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )
    days = _pp(
        "balance_evening_2",
        _balance_evening_shifts,
        days,
        employees,
        pinned_on=pinned_on,
        changelog=changelog,
    )

    for emp in employees:
        states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))
    days = _pp(
        "target_adjustment_3",
        _target_adjustment_pass,
        days,
        employees,
        states,
        holidays,
        pinned_on=pinned_on,
        carry_over_cw=initial_cw,
        carry_over_last_shift=initial_last_shift,
        changelog=changelog,
    )

    prio = config.optimization_priority
    if prio == OptimizationPriority.ISOLATED_WEEKENDS:
        for _pass in range(5):
            days = _pp(
                f"priority_minimize_iso_{_pass}",
                _minimize_isolated_off,
                days,
                employees,
                holidays,
                pinned_on=pinned_on,
                carry_over_cw=initial_cw,
                carry_over_last_shift=initial_last_shift,
                changelog=changelog,
            )
        days = _pp(
            "priority_equalize_iso",
            _equalize_isolated_off,
            days,
            employees,
            holidays,
            pinned_on=pinned_on,
            carry_over_cw=initial_cw,
            changelog=changelog,
            strict=True,
        )
    elif prio == OptimizationPriority.EVENING_SHIFTS:
        days = _pp(
            "priority_evening",
            _balance_evening_shifts,
            days,
            employees,
            pinned_on=pinned_on,
            changelog=changelog,
            strict=True,
        )
    elif prio == OptimizationPriority.CONSECUTIVE_DAYS:
        days = _pp(
            "priority_streak",
            _minimize_max_streak,
            days,
            employees,
            holidays,
            pinned_on=pinned_on,
            carry_over_cw=initial_cw,
            carry_over_last_shift=initial_last_shift,
            changelog=changelog,
            strict=True,
        )
    elif prio == OptimizationPriority.WEEKEND_DAYS:
        days = _pp(
            "priority_weekend",
            _balance_weekend_work,
            days,
            employees,
            pinned_on=pinned_on,
            carry_over_cw=initial_cw,
            changelog=changelog,
            strict=True,
        )

    if prio is not None:
        for emp in employees:
            states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))
        days = _pp(
            "priority_norm_fix",
            _target_adjustment_pass,
            days,
            employees,
            states,
            holidays,
            pinned_on=pinned_on,
            carry_over_cw=initial_cw,
            carry_over_last_shift=initial_last_shift,
            changelog=changelog,
        )

    for emp in employees:
        actual = sum(1 for d in days if _is_working_on_day(emp.name, d))
        target = states[emp.name].effective_target
        if actual > target:
            for i in range(len(days) - 1, -1, -1):
                if actual <= target:
                    break
                ds = days[i]
                if emp.name in ds.workday and (ds.date, emp.name) not in pinned_on:
                    ds.workday.remove(emp.name)
                    ds.day_off.append(emp.name)
                    actual -= 1

    for emp in employees:
        actual = sum(1 for d in days if _is_working_on_day(emp.name, d))
        target = states[emp.name].effective_target
        if actual > target:
            removable = sum(
                1 for d in days if emp.name in d.workday and (d.date, emp.name) not in pinned_on
            )
            if removable > 0:
                raise ScheduleError(
                    f"Нарушена норма для {emp.name}: факт={actual}, норма={target}, "
                    f"осталось {removable} снимаемых WORKDAY"
                )

    days = _pp(
        "balance_evening_final",
        _balance_evening_shifts,
        days,
        employees,
        pinned_on=pinned_on,
        changelog=changelog,
    )

    for emp in employees:
        states[emp.name].total_working = sum(1 for d in days if _is_working_on_day(emp.name, d))

    from duty_schedule.scheduler.postprocess.validation import validate_schedule_or_raise

    soft_violations = validate_schedule_or_raise(
        days, employees, holidays, pins=config.pins, carry_over_cw=initial_cw
    )
    for v in soft_violations:
        logger.warning(
            "schedule_soft_violation",
            employee=v.employee,
            date=str(v.date),
            constraint=v.constraint,
            detail=v.detail,
        )

    duty_employees = [e for e in employees if e.on_duty]
    ev_counts = {e.name: sum(1 for d in days if e.name in d.evening) for e in duty_employees}
    if ev_counts:
        max_ev, min_ev = max(ev_counts.values()), min(ev_counts.values())
        logger.info("evening_shift_balance", max=max_ev, min=min_ev, diff=max_ev - min_ev)

    total_nights = sum(len(d.night) for d in days)
    total_mornings = sum(len(d.morning) for d in days)
    total_evenings = sum(len(d.evening) for d in days)

    working_days_report: dict[str, int] = {
        emp.name: states[emp.name].total_working for emp in employees
    }
    logger.info(
        "schedule_generated",
        days=len(days),
        nights=total_nights,
        mornings=total_mornings,
        evenings=total_evenings,
        production_days=production_days,
        working_days_per_employee=working_days_report,
    )

    from duty_schedule.scheduler.postprocess.carry_over_calc import compute_carry_over

    final_carry_over = compute_carry_over(days, employees)

    return Schedule(
        config=config,
        days=days,
        metadata={
            "total_nights": total_nights,
            "total_mornings": total_mornings,
            "total_evenings": total_evenings,
            "holidays_count": len(holidays),
            "production_working_days": production_days,
            "working_days_per_employee": working_days_report,
            "carry_over": final_carry_over,
            "changelog": changelog,
        },
    )
