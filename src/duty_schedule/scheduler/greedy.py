from __future__ import annotations

import random
from datetime import date, timedelta

from duty_schedule.constants import MIN_WORK_BETWEEN_OFFS
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    ProductionCalendar,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.constraints import (
    _can_work,
    _duty_only,
    _is_weekend_or_holiday,
    _max_co,
    _max_cw,
    _resting_after_evening,
    _resting_after_night,
    _shift_limit_reached,
)
from duty_schedule.scheduler.core import EmployeeState, ScheduleError


def _select_fair(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    shift: ShiftType,
    rng: random.Random,
    count: int = 1,
) -> list[Employee]:
    sorted_candidates = sorted(
        candidates,
        key=lambda e: (
            1
            if (e.schedule_type == ScheduleType.FLEXIBLE and states[e.name].consecutive_off == 1)
            else 0,
            states[e.name].shift_count(shift),
            0 if e.preferred_shift == shift else 1,
            states[e.name].consecutive_working if shift == ShiftType.NIGHT else 0,
            rng.random(),
        ),
    )
    return sorted_candidates[:count]


def _select_for_mandatory(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    shift: ShiftType,
    remaining_days: int,
    rng: random.Random,
    count: int = 1,
) -> list[Employee]:
    deficit_pool = [e for e in candidates if states[e.name].needs_more_work(remaining_days)]
    pool = deficit_pool if deficit_pool else candidates
    return _select_fair(pool, states, shift, rng, count)


def _select_by_urgency(
    candidates: list[Employee],
    states: dict[str, EmployeeState],
    remaining_days: int,
    rng: random.Random,
) -> list[Employee]:
    def urgency(emp: Employee) -> float:
        st = states[emp.name]
        deficit = st.effective_target - st.total_working
        if deficit <= 0:
            return -rng.random()
        return deficit / max(remaining_days, 1) + rng.random() * 0.001

    return sorted(candidates, key=urgency, reverse=True)


def _build_day(
    day: date,
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    rng: random.Random,
    remaining_days: int,
    pins_today: dict[str, ShiftType] | None = None,
    pins_tomorrow: dict[str, ShiftType] | None = None,
) -> DaySchedule:
    is_holiday = _is_weekend_or_holiday(day, holidays)
    _next_day = day + timedelta(days=1)
    ds = DaySchedule(date=day, is_holiday=is_holiday)

    moscow_duty = [e for e in employees if e.city == City.MOSCOW and e.on_duty]
    khabarovsk_duty = [e for e in employees if e.city == City.KHABAROVSK and e.on_duty]
    non_duty = [e for e in employees if not e.on_duty]
    assigned: dict[str, ShiftType] = dict(pins_today or {})

    for _aod_emp in moscow_duty:
        if not _aod_emp.always_on_duty:
            continue
        if _aod_emp.name in assigned:
            continue
        if _aod_emp.is_blocked(day):
            continue
        if _aod_emp.is_day_off_weekly(day):
            continue
        if _aod_emp.schedule_type == ScheduleType.FIVE_TWO and is_holiday:
            continue
        if _resting_after_night(states[_aod_emp.name]):
            continue
        if states[_aod_emp.name].consecutive_working >= _max_cw(_aod_emp):
            continue
        _aod_shift = ShiftType.MORNING if _aod_emp.morning_only else ShiftType.EVENING
        if _shift_limit_reached(_aod_emp, states[_aod_emp.name], _aod_shift):
            continue
        if _aod_shift == ShiftType.MORNING and _resting_after_evening(states[_aod_emp.name]):
            continue
        assigned[_aod_emp.name] = _aod_shift

    _night_pinned = any(s == ShiftType.NIGHT for s in assigned.values())
    if not _night_pinned:
        night_eligible = [
            e
            for e in khabarovsk_duty
            if e.name not in assigned
            and not e.is_blocked(day)
            and not e.is_day_off_weekly(day)
            and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
            and states[e.name].consecutive_working < _max_cw(e)
            and not _shift_limit_reached(e, states[e.name], ShiftType.NIGHT)
        ]

        if not night_eligible:
            raise ScheduleError(
                f"Невозможно покрыть ночную смену {day}: нет доступных дежурных в Хабаровске"
            )

        night_assigned = _select_for_mandatory(
            night_eligible, states, ShiftType.NIGHT, remaining_days, rng, 1
        )
        for emp in night_assigned:
            assigned[emp.name] = ShiftType.NIGHT

    moscow_available = [
        e
        for e in moscow_duty
        if e.name not in assigned
        and not e.is_blocked(day)
        and not e.is_day_off_weekly(day)
        and not _resting_after_night(states[e.name])
        and not (e.schedule_type == ScheduleType.FIVE_TWO and is_holiday)
        and states[e.name].consecutive_working < _max_cw(e)
    ]

    _morning_pinned = any(s == ShiftType.MORNING for s in assigned.values())
    _evening_pinned = any(s == ShiftType.EVENING for s in assigned.values())

    morning_eligible = [
        e
        for e in moscow_available
        if e.can_work_morning()
        and not _resting_after_evening(states[e.name])
        and not _shift_limit_reached(e, states[e.name], ShiftType.MORNING)
    ]
    evening_eligible = [
        e
        for e in moscow_available
        if e.can_work_evening() and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
    ]

    if not _morning_pinned:
        if not morning_eligible:
            raise ScheduleError(
                f"Невозможно покрыть утреннюю смену {day}: нет доступных дежурных в Москве"
            )
        morning_only_pool = [e for e in morning_eligible if e.morning_only]
        if morning_only_pool:
            evening_capable_outside = [
                e
                for e in moscow_available
                if e not in morning_eligible
                and e.can_work_evening()
                and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
            ]
            evening_capable_inside = [
                e
                for e in morning_eligible
                if e.can_work_evening()
                and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
            ]
            if not evening_capable_outside and len(evening_capable_inside) <= 1:
                _morning_select_pool = morning_only_pool
            else:
                _morning_select_pool = morning_eligible
        else:
            _morning_select_pool = morning_eligible
        morning_pick = _select_for_mandatory(
            _morning_select_pool, states, ShiftType.MORNING, remaining_days, rng, 1
        )
        for emp in morning_pick:
            assigned[emp.name] = ShiftType.MORNING
    else:
        morning_pick = []

    if not _evening_pinned:
        evening_pick_pool = [
            e
            for e in moscow_available
            if e.can_work_evening()
            and e not in morning_pick
            and not _shift_limit_reached(e, states[e.name], ShiftType.EVENING)
        ]
        if not evening_pick_pool:
            evening_pick_pool = [e for e in evening_eligible if e not in morning_pick]
        if pins_tomorrow:
            _pinned_non_evening = {
                name
                for name, shift in pins_tomorrow.items()
                if shift in (ShiftType.MORNING, ShiftType.WORKDAY)
            }
            evening_pick_pool = [e for e in evening_pick_pool if e.name not in _pinned_non_evening]
        if not evening_pick_pool:
            raise ScheduleError(
                f"Невозможно покрыть вечернюю смену {day}: все доступные дежурные заняты утром"
            )
        after_evening_deficit = [
            e
            for e in evening_pick_pool
            if _resting_after_evening(states[e.name])
            and states[e.name].needs_more_work(remaining_days)
            and states[e.name].consecutive_working < _max_cw(e) - 1
        ]
        if after_evening_deficit:
            evening_pick = _select_fair(after_evening_deficit, states, ShiftType.EVENING, rng, 1)
        else:
            _evening_well_into_run = [
                e
                for e in evening_pick_pool
                if e.schedule_type == ScheduleType.FLEXIBLE
                and states[e.name].consecutive_working >= MIN_WORK_BETWEEN_OFFS - 1
                and states[e.name].needs_more_work(remaining_days)
            ]
            if _evening_well_into_run:
                _min_ev = min(states[e.name].evening_count for e in _evening_well_into_run)
                _evening_well_into_run = [
                    e for e in _evening_well_into_run if states[e.name].evening_count <= _min_ev + 2
                ]
            _evening_select_pool = (
                _evening_well_into_run if _evening_well_into_run else evening_pick_pool
            )
            evening_pick = _select_for_mandatory(
                _evening_select_pool, states, ShiftType.EVENING, remaining_days, rng, 1
            )
        for emp in evening_pick:
            assigned[emp.name] = ShiftType.EVENING

    if not is_holiday:
        _next_is_holiday = _is_weekend_or_holiday(_next_day, holidays)
        _WORKING = frozenset({ShiftType.MORNING, ShiftType.EVENING, ShiftType.WORKDAY})

        while True:
            extra = [
                e
                for e in moscow_available
                if e.name not in assigned
                and not _duty_only(e)
                and states[e.name].needs_more_work(remaining_days)
                and states[e.name].consecutive_working < _max_cw(e)
                and not _resting_after_evening(states[e.name])
                and not (
                    e.schedule_type == ScheduleType.FLEXIBLE and states[e.name].consecutive_off == 1
                )
            ]
            if not extra:
                break
            by_urgency = _select_by_urgency(extra, states, remaining_days, rng)
            if not by_urgency:
                break
            candidate = by_urgency[0]

            if _next_is_holiday:
                cand_cw_after = states[candidate.name].consecutive_working + 1
                avail_tomorrow = 0
                avail_evening_tomorrow = 0
                for e in moscow_duty:
                    if e.schedule_type == ScheduleType.FIVE_TWO:
                        continue
                    if e.is_blocked(_next_day) or e.is_day_off_weekly(_next_day):
                        continue
                    if e.name == candidate.name:
                        can = cand_cw_after < _max_cw(e)
                    else:
                        s = assigned.get(e.name)
                        cw_ok = states[e.name].consecutive_working + 1 < _max_cw(e)
                        can = s is None or s not in _WORKING or cw_ok
                    if can:
                        avail_tomorrow += 1
                        if e.can_work_evening():
                            avail_evening_tomorrow += 1
                if avail_tomorrow < 2 or avail_evening_tomorrow < 1:
                    break

            assigned[candidate.name] = ShiftType.WORKDAY

        if not is_holiday:
            moscow_duty_on_workday = [
                e for e in moscow_duty if assigned.get(e.name) == ShiftType.WORKDAY
            ]
            if not moscow_duty_on_workday:
                reserve_candidates = [
                    e
                    for e in moscow_available
                    if e.name not in assigned
                    and not _duty_only(e)
                    and states[e.name].consecutive_working < _max_cw(e)
                    and not _resting_after_evening(states[e.name])
                ]
                if reserve_candidates:
                    pick = _select_by_urgency(reserve_candidates, states, remaining_days, rng)
                    if pick:
                        assigned[pick[0].name] = ShiftType.WORKDAY

    for emp in moscow_duty:
        if emp.name not in assigned:
            assigned[emp.name] = (
                ShiftType.VACATION if emp.is_on_vacation(day) else ShiftType.DAY_OFF
            )

    for emp in khabarovsk_duty:
        if emp.name in assigned:
            continue
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
            continue
        if day in emp.unavailable_dates or emp.is_day_off_weekly(day):
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        if states[emp.name].consecutive_working >= _max_cw(emp):
            assigned[emp.name] = ShiftType.DAY_OFF
            continue
        emp_cw_after = states[emp.name].consecutive_working + 1
        needs_work = states[emp.name].needs_more_work(remaining_days)
        if emp_cw_after >= _max_cw(emp) and needs_work:
            others_available = 0
            for other in khabarovsk_duty:
                if other.name == emp.name:
                    continue
                if other.is_blocked(_next_day):
                    continue
                other_shift = assigned.get(other.name)
                if other_shift == ShiftType.VACATION:
                    pass
                elif other_shift == ShiftType.DAY_OFF:
                    others_available += 1
                elif other_shift in (ShiftType.NIGHT, ShiftType.WORKDAY):
                    if states[other.name].consecutive_working + 1 < _max_cw(other):
                        others_available += 1
                else:
                    others_available += 1
            if others_available < 1:
                assigned[emp.name] = ShiftType.DAY_OFF
                continue
        if states[emp.name].needs_more_work(remaining_days) and not (
            emp.schedule_type == ScheduleType.FLEXIBLE and states[emp.name].consecutive_off == 1
        ):
            assigned[emp.name] = ShiftType.WORKDAY
        else:
            assigned[emp.name] = ShiftType.DAY_OFF

    for emp in non_duty:
        if emp.name in assigned:
            continue
        if emp.is_on_vacation(day):
            assigned[emp.name] = ShiftType.VACATION
        elif day in emp.unavailable_dates or emp.is_day_off_weekly(day) or is_holiday:
            assigned[emp.name] = ShiftType.DAY_OFF
        else:
            assigned[emp.name] = ShiftType.WORKDAY

    for emp in moscow_duty + khabarovsk_duty:
        state = states[emp.name]
        if (
            assigned.get(emp.name) == ShiftType.DAY_OFF
            and not _duty_only(emp)
            and state.consecutive_off >= _max_co(emp)
            and _can_work(emp, state, day, holidays)
            and not _resting_after_evening(state)
            and (
                state.needs_more_work(remaining_days) or emp.schedule_type == ScheduleType.FLEXIBLE
            )
            and not is_holiday
        ):
            assigned[emp.name] = ShiftType.WORKDAY

    for emp in moscow_duty + khabarovsk_duty:
        state = states[emp.name]
        if (
            assigned.get(emp.name) == ShiftType.DAY_OFF
            and not _duty_only(emp)
            and emp.schedule_type == ScheduleType.FLEXIBLE
            and 0 < state.consecutive_working < MIN_WORK_BETWEEN_OFFS
            and _can_work(emp, state, day, holidays)
            and not _resting_after_evening(state)
            and not is_holiday
        ):
            assigned[emp.name] = ShiftType.WORKDAY

    for name, shift in assigned.items():
        getattr(ds, shift.value).append(name)

    for emp in employees:
        states[emp.name].record(assigned.get(emp.name, ShiftType.DAY_OFF))

    return ds


def build_candidate(
    config: Config,
    calendar: ProductionCalendar,
    seed: int,
    allow_pending: bool = False,
) -> tuple[list[DaySchedule], bool]:
    from duty_schedule.scheduler.rules import (
        WORKING_SHIFTS,
        assignment_for,
        can_assign_work,
        carry_for_employee,
    )
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
                state.shift_count(shift) / max(targets[employee.name].selected_hours, 1),
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
        for shift in (ShiftType.NIGHT, ShiftType.MORNING, ShiftType.EVENING):
            select(day, shift)
        for name in employees:
            shift = assignment_for(day, name) or ShiftType.DAY_OFF
            states[name].record(shift)
            if shift in WORKING_SHIFTS:
                actual[name] += day.workday_hours.get(name, calendar.hours(day.date) or 8)

    successful = True
    for employee in config.employees:
        if not repair_employee_hours(config, calendar, days, employee, allow_pending):
            successful = False
    return days, successful and all(day.is_covered() for day in days)


def repair_employee_hours(
    config: Config,
    calendar: ProductionCalendar,
    days: list[DaySchedule],
    employee: Employee,
    allow_pending: bool = False,
    allow_extra_duty: bool = False,
) -> bool:
    from duty_schedule.scheduler.rules import (
        WORKING_SHIFTS,
        approval_for,
        assignment_for,
        can_assign_work,
        carry_for_employee,
        normal_streak_limit,
    )
    from duty_schedule.workload import calculate_monthly_targets

    name = employee.name
    target = calculate_monthly_targets(config, calendar)[name].selected_hours
    carry = carry_for_employee(config, employee)
    initial_cw = carry.consecutive_working if carry else 0
    initial_shift = carry.last_shift if carry else None
    initial_off = min(carry.consecutive_off, 2) if carry and not carry.no_previous_shifts else 2
    pins = {(pin.date, pin.employee_name): pin for pin in config.pins}
    states: dict[
        tuple[int, int, bool, int],
        tuple[tuple[int, int, int], tuple[tuple[ShiftType, int], ...]],
    ] = {(0, initial_cw, initial_shift == ShiftType.EVENING, initial_off): ((0, 0, 0), ())}
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
            tuple[tuple[int, int, int], tuple[tuple[ShiftType, int], ...]],
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
                    score[1] + int(working and off_count == 1),
                    score[2] + max(0, new_streak - 5) + new_streak * new_streak,
                )
                key = (new_total, new_streak, shift == ShiftType.EVENING, new_off)
                prior = next_states.get(key)
                if prior is None or new_score < prior[0]:
                    next_states[key] = (new_score, (*path, (shift, hours)))
        states = next_states
        if not states:
            if not allow_extra_duty and employee.on_duty:
                return repair_employee_hours(config, calendar, days, employee, allow_pending, True)
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
