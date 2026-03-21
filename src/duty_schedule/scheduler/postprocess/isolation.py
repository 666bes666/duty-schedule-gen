from __future__ import annotations

from datetime import date

from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.constraints import (
    _duty_only,
    _had_evening_before,
    _is_weekend_or_holiday,
    _max_co,
    _max_co_postprocess,
    _max_cw_postprocess,
)

from .helpers import (
    _consec_work_if_added,
    _count_isolated_off,
    _is_isolated_off_at,
    _streak_around,
    _try_duty_shift_swap,
)


def _minimize_isolated_off(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
    def is_off(name: str, d: DaySchedule) -> bool:
        return name in d.day_off or name in d.vacation

    def is_working(name: str, d: DaySchedule) -> bool:
        return name in d.morning or name in d.evening or name in d.night or name in d.workday

    def consec_off_if_freed(name: str, freed_idx: int) -> int:
        length = 1
        for i in range(freed_idx - 1, -1, -1):
            if is_off(name, days[i]):
                length += 1
            else:
                break
        for i in range(freed_idx + 1, len(days)):
            if is_off(name, days[i]):
                length += 1
            else:
                break
        return length

    for emp in employees:
        if not emp.on_duty:
            continue

        for _ in range(len(days)):
            improved_any = False
            for isolated_idx, day in enumerate(days):
                if emp.name not in day.day_off:
                    continue
                left_ok = isolated_idx == 0 or is_off(emp.name, days[isolated_idx - 1])
                right_ok = isolated_idx == len(days) - 1 or is_off(emp.name, days[isolated_idx + 1])
                if left_ok or right_ok:
                    continue

                improved = False
                count_before = _count_isolated_off(emp.name, days)
                for extend_idx in [isolated_idx - 1, isolated_idx + 1]:
                    if extend_idx < 0 or extend_idx >= len(days):
                        continue
                    free_day = days[extend_idx]
                    in_workday = emp.name in free_day.workday
                    duty_shift_type = None
                    if not in_workday:
                        if emp.name in free_day.morning:
                            duty_shift_type = "morning"
                        elif emp.name in free_day.evening:
                            duty_shift_type = "evening"
                        elif emp.name in free_day.night:
                            duty_shift_type = "night"
                        if duty_shift_type is None:
                            continue
                    if (free_day.date, emp.name) in pinned_on:
                        continue
                    if consec_off_if_freed(emp.name, extend_idx) > _max_co_postprocess(emp):
                        continue

                    if in_workday:
                        comp_candidates = []
                        for comp_i, comp_day in enumerate(days):
                            if emp.name not in comp_day.day_off:
                                continue
                            if comp_i == isolated_idx:
                                continue
                            if (comp_day.date, emp.name) in pinned_on:
                                continue
                            if _is_weekend_or_holiday(comp_day.date, holidays):
                                continue
                            if emp.is_blocked(comp_day.date):
                                continue
                            if emp.is_day_off_weekly(comp_day.date):
                                continue
                            if _had_evening_before(emp.name, comp_i, days, carry_over_last_shift):
                                continue
                            if _consec_work_if_added(
                                emp.name, comp_i, days, carry_over_cw
                            ) > _max_cw_postprocess(emp):
                                continue
                            comp_candidates.append(comp_i)

                        comp_candidates.sort(
                            key=lambda ci: (
                                0 if _is_isolated_off_at(emp.name, ci, days) else 1,
                                abs(ci - isolated_idx),
                            )
                        )

                        for comp_i in comp_candidates:
                            comp_day = days[comp_i]
                            free_day.workday.remove(emp.name)
                            free_day.day_off.append(emp.name)
                            comp_day.day_off.remove(emp.name)
                            comp_day.workday.append(emp.name)
                            if _count_isolated_off(emp.name, days) < count_before:
                                improved = True
                                break
                            free_day.day_off.remove(emp.name)
                            free_day.workday.append(emp.name)
                            comp_day.workday.remove(emp.name)
                            comp_day.day_off.append(emp.name)

                    elif emp.schedule_type == ScheduleType.FLEXIBLE:
                        improved = _try_duty_shift_swap(
                            emp,
                            extend_idx,
                            isolated_idx,
                            days,
                            employees,
                            pinned_on,
                            holidays,
                            carry_over_cw,
                            carry_over_last_shift,
                        )

                    if improved:
                        break

                if improved:
                    improved_any = True

                if not improved and emp.schedule_type == ScheduleType.FLEXIBLE:
                    if (days[isolated_idx].date, emp.name) in pinned_on:
                        continue
                    if emp.is_blocked(days[isolated_idx].date):
                        continue
                    if emp.is_day_off_weekly(days[isolated_idx].date):
                        continue
                    if _had_evening_before(emp.name, isolated_idx, days, carry_over_last_shift):
                        continue
                    if _consec_work_if_added(
                        emp.name, isolated_idx, days, carry_over_cw
                    ) > _max_cw_postprocess(emp):
                        continue
                    for target_i, target_day in enumerate(days):
                        if emp.name not in target_day.day_off:
                            continue
                        if target_i == isolated_idx:
                            continue
                        t_left = target_i == 0 or is_off(emp.name, days[target_i - 1])
                        t_right = target_i == len(days) - 1 or is_off(emp.name, days[target_i + 1])
                        if t_left or t_right:
                            continue
                        for nb_i in [target_i - 1, target_i + 1]:
                            if nb_i < 0 or nb_i >= len(days):
                                continue
                            if emp.name not in days[nb_i].workday:
                                continue
                            if (days[nb_i].date, emp.name) in pinned_on:
                                continue
                            outer = nb_i - 1 if nb_i < target_i else nb_i + 1
                            if 0 <= outer < len(days) and is_off(emp.name, days[outer]):
                                continue
                            days[isolated_idx].day_off.remove(emp.name)
                            days[isolated_idx].workday.append(emp.name)
                            days[nb_i].workday.remove(emp.name)
                            days[nb_i].day_off.append(emp.name)
                            improved = True
                            improved_any = True
                            break
                        if improved:
                            break

                    if not improved:
                        swap_candidates = []
                        for comp_i in range(len(days)):
                            comp_day = days[comp_i]
                            if emp.name not in comp_day.workday:
                                continue
                            if comp_i == isolated_idx:
                                continue
                            if (comp_day.date, emp.name) in pinned_on:
                                continue
                            if emp.is_blocked(comp_day.date):
                                continue
                            if _had_evening_before(emp.name, comp_i, days, carry_over_last_shift):
                                continue
                            if _streak_around(emp.name, comp_i, days, working=False) > _max_co(emp):
                                continue
                            swap_candidates.append(comp_i)

                        swap_candidates.sort(key=lambda ci: abs(ci - isolated_idx))

                        for comp_i in swap_candidates:
                            comp_day = days[comp_i]
                            days[isolated_idx].day_off.remove(emp.name)
                            days[isolated_idx].workday.append(emp.name)
                            comp_day.workday.remove(emp.name)
                            comp_day.day_off.append(emp.name)
                            if _count_isolated_off(emp.name, days) < count_before:
                                improved = True
                                improved_any = True
                                break
                            days[isolated_idx].workday.remove(emp.name)
                            days[isolated_idx].day_off.append(emp.name)
                            comp_day.day_off.remove(emp.name)
                            comp_day.workday.append(emp.name)

            if not improved_any:
                break

    return days


def _break_evening_isolated_pattern(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
    def is_off(name: str, idx: int) -> bool:
        if idx < 0 or idx >= len(days):
            return True
        return name in days[idx].day_off or name in days[idx].vacation

    moscow_flex = [
        e
        for e in employees
        if e.on_duty
        and e.schedule_type == ScheduleType.FLEXIBLE
        and e.city == City.MOSCOW
        and not e.morning_only
        and not e.evening_only
    ]

    for emp_a in moscow_flex:
        if _count_isolated_off(emp_a.name, days) == 0:
            continue

        for iso_idx in range(len(days)):
            if _count_isolated_off(emp_a.name, days) == 0:
                break
            if emp_a.name not in days[iso_idx].day_off:
                continue
            if is_off(emp_a.name, iso_idx - 1) or is_off(emp_a.name, iso_idx + 1):
                continue

            if iso_idx == 0 or emp_a.name not in days[iso_idx - 1].evening:
                continue
            ev_idx = iso_idx - 1

            if ev_idx > 0 and emp_a.name in days[ev_idx - 1].evening:
                continue

            count_a_before = _count_isolated_off(emp_a.name, days)

            for emp_b in moscow_flex:
                if emp_b.name == emp_a.name:
                    continue

                ev_day = days[ev_idx]

                if (ev_day.date, emp_a.name) in pinned_on or (ev_day.date, emp_b.name) in pinned_on:
                    continue

                if emp_b.name in ev_day.morning:
                    b_source = "morning"
                elif emp_b.name in ev_day.workday:
                    b_source = "workday"
                else:
                    continue

                if ev_idx + 1 < len(days):
                    next_d = days[ev_idx + 1]
                    if not (
                        emp_b.name in next_d.evening
                        or emp_b.name in next_d.day_off
                        or emp_b.name in next_d.vacation
                    ):
                        continue

                ev_day.evening.remove(emp_a.name)
                b_list = ev_day.morning if b_source == "morning" else ev_day.workday
                b_list.remove(emp_b.name)
                ev_day.evening.append(emp_b.name)
                (ev_day.morning if b_source == "morning" else ev_day.workday).append(emp_a.name)

                count_b_after = _count_isolated_off(emp_b.name, days)

                count_a_after = _count_isolated_off(emp_a.name, days)
                if count_a_after < count_a_before and count_b_after <= 2:
                    break

                ev_day.evening.remove(emp_b.name)
                (ev_day.morning if b_source == "morning" else ev_day.workday).remove(emp_a.name)
                ev_day.evening.append(emp_a.name)
                (ev_day.morning if b_source == "morning" else ev_day.workday).append(emp_b.name)

    return days


def _equalize_isolated_off(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    changelog: ChangeLog | None = None,
    strict: bool = False,
) -> list[DaySchedule]:
    flex_duty = [
        e
        for e in employees
        if e.on_duty and e.schedule_type == ScheduleType.FLEXIBLE and not _duty_only(e)
    ]
    if len(flex_duty) < 2:
        return days

    _iterations = len(days) * (3 if strict else 1)
    for _ in range(_iterations):
        iso_counts = {e.name: _count_isolated_off(e.name, days) for e in flex_duty}
        max_name = max(iso_counts, key=lambda n: iso_counts[n])
        min_name = min(iso_counts, key=lambda n: iso_counts[n])
        max_val = iso_counts[max_name]
        min_val = iso_counts[min_name]

        if strict:
            if max_val - min_val <= 0:
                break
        elif max_val - min_val <= 1 or max_val <= 2:
            break

        max_emp = next(e for e in flex_duty if e.name == max_name)
        min_emp = next(e for e in flex_duty if e.name == min_name)

        if max_emp.city != min_emp.city:
            break

        swapped = False
        for day_a_idx in range(len(days)):
            if not _is_isolated_off_at(max_name, day_a_idx, days):
                continue
            if min_name not in days[day_a_idx].workday:
                continue
            if (days[day_a_idx].date, max_name) in pinned_on:
                continue
            if (days[day_a_idx].date, min_name) in pinned_on:
                continue
            if max_emp.is_blocked(days[day_a_idx].date):
                continue
            if min_emp.is_blocked(days[day_a_idx].date):
                continue
            if day_a_idx > 0 and max_name in days[day_a_idx - 1].evening:
                continue
            if _consec_work_if_added(
                max_name, day_a_idx, days, carry_over_cw
            ) > _max_cw_postprocess(max_emp):
                continue

            for day_b_idx in range(len(days)):
                if day_b_idx == day_a_idx:
                    continue
                if max_name not in days[day_b_idx].workday:
                    continue
                if min_name not in days[day_b_idx].day_off:
                    continue
                if (days[day_b_idx].date, max_name) in pinned_on:
                    continue
                if (days[day_b_idx].date, min_name) in pinned_on:
                    continue
                if max_emp.is_blocked(days[day_b_idx].date):
                    continue
                if min_emp.is_blocked(days[day_b_idx].date):
                    continue
                if max_emp.is_day_off_weekly(days[day_b_idx].date):
                    continue
                if min_emp.is_day_off_weekly(days[day_a_idx].date):
                    continue
                if day_b_idx > 0 and min_name in days[day_b_idx - 1].evening:
                    continue
                if _consec_work_if_added(
                    min_name, day_b_idx, days, carry_over_cw
                ) > _max_cw_postprocess(min_emp):
                    continue
                co_max = _streak_around(max_name, day_b_idx, days, working=False)
                if co_max > _max_co(max_emp):
                    continue

                days[day_a_idx].day_off.remove(max_name)
                days[day_a_idx].workday.append(max_name)
                days[day_a_idx].workday.remove(min_name)
                days[day_a_idx].day_off.append(min_name)

                days[day_b_idx].workday.remove(max_name)
                days[day_b_idx].day_off.append(max_name)
                days[day_b_idx].day_off.remove(min_name)
                days[day_b_idx].workday.append(min_name)

                new_max = _count_isolated_off(max_name, days)
                new_min = _count_isolated_off(min_name, days)

                if new_max < max_val and new_min <= min_val + (max_val - new_max):
                    swapped = True
                    break

                days[day_a_idx].workday.remove(max_name)
                days[day_a_idx].day_off.append(max_name)
                days[day_a_idx].day_off.remove(min_name)
                days[day_a_idx].workday.append(min_name)

                days[day_b_idx].day_off.remove(max_name)
                days[day_b_idx].workday.append(max_name)
                days[day_b_idx].workday.remove(min_name)
                days[day_b_idx].day_off.append(min_name)

            if swapped:
                break

        if not swapped:
            break

    return days
