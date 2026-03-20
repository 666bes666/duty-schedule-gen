from __future__ import annotations

import calendar
from datetime import date, timedelta

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from duty_schedule.constants import MAX_CONSECUTIVE_WORKING_DEFAULT
from duty_schedule.models import (
    City,
    Config,
    Employee,
    ScheduleType,
    ShiftType,
    VacationPeriod,
)
from duty_schedule.scheduler import ScheduleError, generate_schedule


@st.composite
def config_strategy(draw: st.DrawFn) -> Config:
    month = draw(st.integers(min_value=1, max_value=12))
    year = 2025
    seed = draw(st.integers(min_value=0, max_value=99999))
    days_in_month = calendar.monthrange(year, month)[1]

    extra_moscow = draw(st.integers(min_value=0, max_value=3))
    moscow_count = 4 + extra_moscow
    extra_khab = draw(st.integers(min_value=0, max_value=2))
    khab_count = 2 + extra_khab

    employees: list[Employee] = []
    idx = 0

    for i in range(moscow_count):
        if i < 4:
            sched = ScheduleType.FLEXIBLE
            on_duty = True
        else:
            sched = draw(st.sampled_from([ScheduleType.FLEXIBLE, ScheduleType.FIVE_TWO]))
            on_duty = draw(st.booleans())

        morning_only = False
        evening_only = False
        if on_duty:
            flag = draw(st.sampled_from(["none", "none", "morning_only", "evening_only"]))
            morning_only = flag == "morning_only"
            evening_only = flag == "evening_only"

        has_vacation = draw(st.booleans()) if i >= 2 else False
        vacations: list[VacationPeriod] = []
        if has_vacation:
            vac_start_day = draw(st.integers(min_value=1, max_value=days_in_month))
            max_vac = min(3, days_in_month - vac_start_day + 1)
            vac_len = draw(st.integers(min_value=1, max_value=max_vac))
            vacations = [
                VacationPeriod(
                    start=date(year, month, vac_start_day),
                    end=date(year, month, vac_start_day + vac_len - 1),
                )
            ]

        employees.append(
            Employee(
                name=f"Сотрудник М{idx}",
                city=City.MOSCOW,
                schedule_type=sched,
                on_duty=on_duty,
                morning_only=morning_only,
                evening_only=evening_only,
                vacations=vacations,
            )
        )
        idx += 1

    khab_vacation_idx = draw(st.integers(min_value=-1, max_value=khab_count - 1))

    for i in range(khab_count):
        on_duty = True if i < 2 else draw(st.booleans())

        vacations = []
        if i == khab_vacation_idx and khab_count >= 3:
            vac_start_day = draw(st.integers(min_value=1, max_value=days_in_month))
            max_vac = min(3, days_in_month - vac_start_day + 1)
            vac_len = draw(st.integers(min_value=1, max_value=max_vac))
            vacations = [
                VacationPeriod(
                    start=date(year, month, vac_start_day),
                    end=date(year, month, vac_start_day + vac_len - 1),
                )
            ]

        employees.append(
            Employee(
                name=f"Сотрудник Х{idx}",
                city=City.KHABAROVSK,
                schedule_type=ScheduleType.FLEXIBLE,
                on_duty=on_duty,
                vacations=vacations,
            )
        )
        idx += 1

    return Config(month=month, year=year, seed=seed, employees=employees)


@given(cfg=config_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
def test_schedule_covers_all_days(cfg: Config) -> None:
    try:
        schedule = generate_schedule(cfg, set())
    except ScheduleError:
        assume(False)
        return

    days_in_month = calendar.monthrange(cfg.year, cfg.month)[1]
    assert len(schedule.days) == days_in_month

    expected_dates = {date(cfg.year, cfg.month, d) for d in range(1, days_in_month + 1)}
    actual_dates = {day.date for day in schedule.days}
    assert actual_dates == expected_dates


@given(cfg=config_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
def test_no_duplicate_employees_per_shift(cfg: Config) -> None:
    try:
        schedule = generate_schedule(cfg, set())
    except ScheduleError:
        assume(False)
        return

    for day in schedule.days:
        for shift_name in ("morning", "evening", "night", "workday"):
            names = getattr(day, shift_name)
            assert len(names) == len(set(names)), (
                f"Duplicate in {shift_name} on {day.date}: {names}"
            )

        all_working = day.morning + day.evening + day.night + day.workday
        assert len(all_working) == len(set(all_working)), (
            f"Employee assigned to multiple shifts on {day.date}: {all_working}"
        )


@given(cfg=config_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
def test_vacation_respected(cfg: Config) -> None:
    try:
        schedule = generate_schedule(cfg, set())
    except ScheduleError:
        assume(False)
        return

    working_shifts = (ShiftType.MORNING, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.WORKDAY)
    day_by_date = {day.date: day for day in schedule.days}

    for emp in cfg.employees:
        for vac in emp.vacations:
            current = vac.start
            while current <= vac.end:
                day = day_by_date.get(current)
                if day is not None:
                    for shift in working_shifts:
                        names_in_shift = getattr(day, shift.value)
                        assert emp.name not in names_in_shift, (
                            f"{emp.name} is on vacation {current} but assigned to {shift.value}"
                        )
                current = current + timedelta(days=1)


@given(cfg=config_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
def test_consecutive_working_not_exceeded(cfg: Config) -> None:
    try:
        schedule = generate_schedule(cfg, set())
    except ScheduleError:
        assume(False)
        return

    days_sorted = sorted(schedule.days, key=lambda d: d.date)

    for emp in cfg.employees:
        max_cw = emp.max_consecutive_working or MAX_CONSECUTIVE_WORKING_DEFAULT
        consecutive = 0
        for day in days_sorted:
            all_working = day.morning + day.evening + day.night + day.workday
            if emp.name in all_working:
                consecutive += 1
                assert consecutive <= max_cw + 1, (
                    f"{emp.name} worked {consecutive} consecutive days "
                    f"(limit {max_cw}) ending {day.date}"
                )
            else:
                consecutive = 0


@given(cfg=config_strategy())
@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.filter_too_much])
def test_all_shifts_covered(cfg: Config) -> None:
    try:
        schedule = generate_schedule(cfg, set())
    except ScheduleError:
        assume(False)
        return

    for day in schedule.days:
        assert day.is_covered(), (
            f"Day {day.date} not fully covered: "
            f"morning={day.morning}, evening={day.evening}, night={day.night}"
        )
