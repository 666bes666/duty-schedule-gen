from __future__ import annotations

import random
from datetime import date, timedelta

from duty_schedule.models import (
    Config,
    DaySchedule,
    Employee,
    ProductionCalendar,
    Schedule,
    ShiftType,
)
from duty_schedule.scheduler.constraints import (
    _duty_only,
)
from duty_schedule.scheduler.core import EmployeeState


def build_candidate(
    config: Config,
    calendar: ProductionCalendar,
    seed: int,
    allow_pending: bool = False,
    baseline: Schedule | None = None,
) -> tuple[list[DaySchedule], bool]:
    from duty_schedule.quality_history import balance_pools
    from duty_schedule.scheduler.rules import (
        WORKING_SHIFTS,
        assignment_for,
        can_assign_work,
        carry_for_employee,
    )

    pools = balance_pools(config, allow_pending)
    from duty_schedule.scheduler.postprocess.quality import schedule_cells

    baseline_cells = schedule_cells(baseline) if baseline is not None else {}
    from duty_schedule.workload import calculate_monthly_targets

    rng = random.Random(seed)
    targets = calculate_monthly_targets(config, calendar)
    employees = {employee.name: employee for employee in config.employees}
    states = {employee.name: EmployeeState() for employee in config.employees}
    actual = dict.fromkeys(employees, 0)
    for employee in config.employees:
        carry = carry_for_employee(config, employee)
        if carry:
            states[employee.name].last_shift = carry.last_shift
            states[employee.name].consecutive_working = carry.consecutive_working
            states[employee.name].consecutive_off = carry.consecutive_off
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    days: list[DaySchedule] = []
    for record in sorted(calendar.days, key=lambda record: record.date):
        day = DaySchedule(date=record.date, is_holiday=not calendar.is_working(record.date))
        for employee in config.employees:
            shift = ShiftType.DAY_OFF
            if employee.is_on_sick_leave(day.date):
                shift = ShiftType.SICK_LEAVE
            elif employee.is_on_vacation(day.date):
                shift = ShiftType.VACATION
            pin = pins.get((day.date, employee.name))
            if pin:
                shift = pin.shift
                if pin.working_hours is not None:
                    day.workday_hours[employee.name] = pin.working_hours
            getattr(day, shift.value).append(employee.name)
        days.append(day)

    def select(day: DaySchedule, shift: ShiftType) -> bool:
        if getattr(day, shift.value):
            return True
        candidates = []
        for name, employee in employees.items():
            state = states[name]
            if name not in day.day_off or (day.date, name) in pins:
                continue
            if actual[name] + (calendar.hours(day.date) or 8) > targets[name].selected_hours:
                continue
            if not can_assign_work(
                config,
                calendar,
                employee,
                day.date,
                shift,
                state.last_shift,
                state.consecutive_working,
                allow_pending,
            ):
                continue
            next_pin = (
                pins.get((day.date + timedelta(days=1), name)) if day.date < date.max else None
            )
            if (
                shift == ShiftType.EVENING
                and next_pin
                and next_pin.shift
                in (
                    ShiftType.MORNING,
                    ShiftType.WORKDAY,
                )
            ):
                continue
            candidates.append(employee)
        if not candidates:
            return False
        if shift == ShiftType.MORNING:
            evening_possible = [
                employee
                for employee in employees.values()
                if employee.name in day.day_off
                and (day.date, employee.name) not in pins
                and can_assign_work(
                    config,
                    calendar,
                    employee,
                    day.date,
                    ShiftType.EVENING,
                    states[employee.name].last_shift,
                    states[employee.name].consecutive_working,
                    allow_pending,
                )
            ]
            if not day.evening and len(evening_possible) == 1:
                candidates = [e for e in candidates if e.name != evening_possible[0].name]
                if not candidates:
                    return False

        def rank(employee: Employee) -> tuple[float, ...]:
            state = states[employee.name]
            return (
                float(state.consecutive_off == 1),
                (
                    state.shift_count(shift)
                    + pools[shift.value]["previous_counts"].get(employee.employee_id, 0)
                )
                / max(pools[shift.value]["weights"].get(employee.employee_id, 0), 1)
                if shift.value in pools
                else state.shift_count(shift) / max(targets[employee.name].selected_hours, 1),
                actual[employee.name] / max(targets[employee.name].selected_hours, 1),
                float(state.consecutive_working),
                float(employee.preferred_shift not in (None, shift)),
                rng.random(),
            )

        chosen = min(candidates, key=rank)
        day.day_off.remove(chosen.name)
        getattr(day, shift.value).append(chosen.name)
        return True

    for day in days:
        for employee in config.employees:
            old = baseline_cells.get((day.date, employee.employee_id))
            state = states[employee.name]
            if (
                old is None
                or old[0] not in WORKING_SHIFTS
                or employee.name not in day.day_off
                or (day.date, employee.name) in pins
            ):
                continue
            if old[0] in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT) and getattr(
                day, old[0].value
            ):
                continue
            hours = old[1] if old[0] == ShiftType.WORKDAY else calendar.hours(day.date) or 8
            if actual[employee.name] + hours > targets[
                employee.name
            ].selected_hours or not can_assign_work(
                config,
                calendar,
                employee,
                day.date,
                old[0],
                state.last_shift,
                state.consecutive_working,
                allow_pending,
            ):
                continue
            day.day_off.remove(employee.name)
            getattr(day, old[0].value).append(employee.name)
            if old[0] == ShiftType.WORKDAY:
                day.workday_hours[employee.name] = hours
        for shift in (ShiftType.NIGHT, ShiftType.MORNING, ShiftType.EVENING):
            select(day, shift)
        for name in employees:
            shift = assignment_for(day, name) or ShiftType.DAY_OFF
            states[name].record(shift)
            if shift in WORKING_SHIFTS:
                actual[name] += day.workday_hours.get(name, calendar.hours(day.date) or 8)

    successful = True
    for employee in config.employees:
        if not repair_employee_hours(
            config, calendar, days, employee, allow_pending, baseline=baseline
        ):
            successful = False
    return days, successful and all(day.is_covered() for day in days)


def repair_employee_hours(
    config: Config,
    calendar: ProductionCalendar,
    days: list[DaySchedule],
    employee: Employee,
    allow_pending: bool = False,
    allow_extra_duty: bool = False,
    baseline: Schedule | None = None,
) -> bool:
    from duty_schedule.scheduler.postprocess.quality import schedule_cells
    from duty_schedule.scheduler.rules import (
        WORKING_SHIFTS,
        approval_for,
        assignment_for,
        can_assign_work,
        carry_for_employee,
        normal_streak_limit,
    )
    from duty_schedule.workload import calculate_monthly_targets

    baseline_cells = schedule_cells(baseline) if baseline is not None else {}
    name = employee.name
    target = calculate_monthly_targets(config, calendar)[name].selected_hours
    carry = carry_for_employee(config, employee)
    initial_cw = carry.consecutive_working if carry else 0
    initial_shift = carry.last_shift if carry else None
    initial_off = min(carry.consecutive_off, 2) if carry and not carry.no_previous_shifts else 2
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    states: dict[
        tuple[int, int, bool, int],
        tuple[tuple[int, int, int, int], tuple[tuple[ShiftType, int], ...]],
    ] = {(0, initial_cw, initial_shift == ShiftType.EVENING, initial_off): ((0, 0, 0, 0), ())}
    suffix_capacity = [0] * (len(days) + 1)
    for index in range(len(days) - 1, -1, -1):
        day = days[index]
        fixed = assignment_for(day, name)
        capacity = 0
        if fixed in WORKING_SHIFTS:
            capacity = day.workday_hours.get(name, calendar.hours(day.date) or 8)
        elif (
            fixed == ShiftType.DAY_OFF
            and (day.date, name) not in pins
            and calendar.is_working(day.date)
            and not employee.is_blocked(day.date)
        ):
            capacity = calendar.hours(day.date)
        if (
            fixed == ShiftType.DAY_OFF
            and (day.date, name) not in pins
            and (_duty_only(employee) or allow_extra_duty)
            and any(
                can_assign_work(config, calendar, employee, day.date, shift, None, 0, allow_pending)
                for shift in (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT)
            )
        ):
            capacity = calendar.hours(day.date) or 8
        suffix_capacity[index] = suffix_capacity[index + 1] + capacity
    for index, day in enumerate(days):
        fixed = assignment_for(day, name) or ShiftType.DAY_OFF
        pin = pins.get((day.date, name))
        base = calendar.hours(day.date) or 8
        options: list[tuple[ShiftType, int]] = [
            (fixed, day.workday_hours.get(name, base) if fixed in WORKING_SHIFTS else 0)
        ]
        if fixed == ShiftType.DAY_OFF and pin is None and calendar.is_working(day.date):
            options.append((ShiftType.WORKDAY, base))
            approved_hours = {
                approval.value
                for approval in config.approvals
                if approval.rule == "individual_workday"
                and approval.date == day.date
                and approval_for(config, employee, day.date, "individual_workday", approval.value)
                and approval.value is not None
                and 1 <= approval.value < base
            }
            for hours in range(1, base) if allow_pending else sorted(approved_hours):
                options.append((ShiftType.WORKDAY, hours))
        if (
            fixed == ShiftType.DAY_OFF
            and pin is None
            and (_duty_only(employee) or allow_extra_duty)
        ):
            options.extend(
                (shift, base)
                for shift in (
                    ShiftType.MORNING,
                    ShiftType.EVENING,
                    ShiftType.NIGHT,
                )
            )
        next_states: dict[
            tuple[int, int, bool, int],
            tuple[tuple[int, int, int, int], tuple[tuple[ShiftType, int], ...]],
        ] = {}
        for (total, streak, previous_evening, off_count), (score, path) in states.items():
            for shift, hours in options:
                working = shift in WORKING_SHIFTS
                new_total = total + hours
                if new_total > target or new_total + suffix_capacity[index + 1] < target:
                    continue
                previous_shift = ShiftType.EVENING if previous_evening else None
                if working and not can_assign_work(
                    config,
                    calendar,
                    employee,
                    day.date,
                    shift,
                    previous_shift,
                    streak,
                    allow_pending,
                ):
                    continue
                new_streak = streak + 1 if working else 0
                new_off = 0 if working else min(off_count + 1, 2)
                pending = 0
                if (
                    working
                    and new_streak > normal_streak_limit(employee)
                    and not approval_for(config, employee, day.date, "working_streak", new_streak)
                ):
                    pending += 1
                if (
                    working
                    and employee.is_day_off_weekly(day.date)
                    and not approval_for(config, employee, day.date, "weekly_day_off")
                ):
                    pending += 1
                if (
                    shift == ShiftType.WORKDAY
                    and hours != base
                    and not approval_for(config, employee, day.date, "individual_workday", hours)
                ):
                    pending += 1
                new_score = (
                    score[0] + pending,
                    score[1]
                    + int(
                        baseline is not None
                        and baseline_cells.get((day.date, employee.employee_id)) != (shift, hours)
                    ),
                    score[2] + int(working and off_count == 1),
                    score[3] + max(0, new_streak - 5) + new_streak * new_streak,
                )
                key = (new_total, new_streak, shift == ShiftType.EVENING, new_off)
                prior = next_states.get(key)
                if prior is None or new_score < prior[0]:
                    next_states[key] = (new_score, (*path, (shift, hours)))
        states = next_states
        if not states:
            if not allow_extra_duty and employee.on_duty:
                return repair_employee_hours(
                    config, calendar, days, employee, allow_pending, True, baseline
                )
            return False
    choices = [
        (score, path) for (total, _, _, _), (score, path) in states.items() if total == target
    ]
    if not choices:
        return False
    _, best = min(choices, key=lambda choice: choice[0])
    for day, (shift, hours) in zip(days, best, strict=True):
        old_shift = assignment_for(day, name)
        if old_shift != shift:
            if old_shift:
                getattr(day, old_shift.value).remove(name)
            getattr(day, shift.value).append(name)
        if shift == ShiftType.WORKDAY and (
            hours != (calendar.hours(day.date) or 8)
            or pins.get((day.date, name))
            and pins[(day.date, name)].working_hours is not None
        ):
            day.workday_hours[name] = hours
        else:
            day.workday_hours.pop(name, None)
    return True
