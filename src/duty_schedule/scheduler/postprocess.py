from __future__ import annotations

from datetime import date, timedelta

from duty_schedule.constants import MAX_CONSECUTIVE_WORKING_DEFAULT, MIN_WORK_BETWEEN_OFFS
from duty_schedule.logging import get_logger
from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.constraints import (
    _consecutive_shift_count_at,
    _duty_only,
    _had_evening_before,
    _is_weekend_or_holiday,
    _is_working_on_day,
    _max_co,
    _max_co_postprocess,
    _max_cw,
    _max_cw_postprocess,
)
from duty_schedule.scheduler.core import EmployeeState

logger = get_logger()


def _streak_around(
    emp_name: str,
    idx: int,
    days: list[DaySchedule],
    working: bool,
    carry_over_cw: dict[str, int] | None = None,
) -> int:
    """Длина серии вокруг days[idx], если он становится рабочим (working=True) или выходным.

    carry_over_cw: число рабочих дней подряд, перенесённых с конца предыдущего месяца.
    Добавляется к левой части серии, если левый скан достигает начала массива.
    """

    def active(d: DaySchedule) -> bool:
        return (
            _is_working_on_day(emp_name, d)
            if working
            else (emp_name in d.day_off or emp_name in d.vacation)
        )

    left = 0
    reached_left_boundary = True
    for i in range(idx - 1, -1, -1):
        if active(days[i]):
            left += 1
        else:
            reached_left_boundary = False
            break
    if reached_left_boundary and working and carry_over_cw is not None:
        left += carry_over_cw.get(emp_name, 0)
    right = 0
    for i in range(idx + 1, len(days)):
        if active(days[i]):
            right += 1
        else:
            break
    return left + 1 + right


def _consec_work_if_added(
    emp_name: str,
    add_idx: int,
    days: list[DaySchedule],
    carry_over_cw: dict[str, int] | None = None,
) -> int:
    """Длина рабочей серии, если days[add_idx] становится рабочим днём.

    carry_over_cw: число рабочих дней подряд с конца предыдущего месяца.
    """
    length = 1
    reached_left_boundary = True
    for i in range(add_idx - 1, -1, -1):
        if _is_working_on_day(emp_name, days[i]):
            length += 1
        else:
            reached_left_boundary = False
            break
    if reached_left_boundary and carry_over_cw is not None:
        length += carry_over_cw.get(emp_name, 0)
    for i in range(add_idx + 1, len(days)):
        if _is_working_on_day(emp_name, days[i]):
            length += 1
        else:
            break
    return length


def _count_isolated_off(emp_name: str, days: list[DaySchedule]) -> int:
    count = 0
    for i, day in enumerate(days):
        if emp_name not in day.day_off:
            continue
        left_ok = i == 0 or emp_name in days[i - 1].day_off or emp_name in days[i - 1].vacation
        right_ok = (
            i == len(days) - 1
            or emp_name in days[i + 1].day_off
            or emp_name in days[i + 1].vacation
        )
        if not left_ok and not right_ok:
            count += 1
    return count


def _is_isolated_off_at(name: str, idx: int, days: list[DaySchedule]) -> bool:
    if name not in days[idx].day_off:
        return False
    left_ok = idx == 0 or name in days[idx - 1].day_off or name in days[idx - 1].vacation
    right_ok = (
        idx == len(days) - 1 or name in days[idx + 1].day_off or name in days[idx + 1].vacation
    )
    return not left_ok and not right_ok


def _try_duty_shift_swap(
    emp: Employee,
    extend_idx: int,
    isolated_idx: int,
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]],
    holidays: set[date],
    carry_over_cw: dict[str, int] | None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
) -> bool:
    free_day = days[extend_idx]
    if emp.name in free_day.morning:
        duty_shift_type = "morning"
    elif emp.name in free_day.evening:
        duty_shift_type = "evening"
    elif emp.name in free_day.night:
        duty_shift_type = "night"
    else:
        return False

    shift_list: list[str] = getattr(free_day, duty_shift_type)
    count_before = _count_isolated_off(emp.name, days)

    for partner in employees:
        if partner.name == emp.name:
            continue
        if not partner.on_duty or partner.city != emp.city:
            continue
        if partner.schedule_type != ScheduleType.FLEXIBLE:
            continue
        if _duty_only(partner):
            continue
        if duty_shift_type == "morning" and not partner.can_work_morning():
            continue
        if duty_shift_type == "evening" and not partner.can_work_evening():
            continue
        if (free_day.date, partner.name) in pinned_on:
            continue
        if partner.is_blocked(free_day.date):
            continue

        if partner.name in free_day.workday:
            partner_source = "workday"
        elif partner.name in free_day.day_off:
            partner_source = "day_off"
        else:
            continue

        if partner_source == "day_off" and _consec_work_if_added(
            partner.name, extend_idx, days, carry_over_cw
        ) > _max_cw_postprocess(partner):
            continue

        if duty_shift_type == "evening" and extend_idx + 1 < len(days):
            next_day = days[extend_idx + 1]
            if partner.name in next_day.morning or partner.name in next_day.workday:
                continue

        if duty_shift_type in ("morning", "night") and _had_evening_before(
            partner.name, extend_idx, days, carry_over_last_shift
        ):
            continue

        if (
            duty_shift_type == "morning"
            and partner.max_morning_shifts is not None
            and sum(1 for d in days if partner.name in d.morning) >= partner.max_morning_shifts
        ):
            continue
        if (
            duty_shift_type == "evening"
            and partner.max_evening_shifts is not None
            and sum(1 for d in days if partner.name in d.evening) >= partner.max_evening_shifts
        ):
            continue

        _consec_limit = getattr(partner, f"max_consecutive_{duty_shift_type}", None)
        if _consec_limit is not None and (
            _consecutive_shift_count_at(partner.name, extend_idx, days, duty_shift_type)
            >= _consec_limit
        ):
            continue

        emp_comp_candidates = []
        for ci, cd in enumerate(days):
            if emp.name not in cd.day_off:
                continue
            if ci in (isolated_idx, extend_idx):
                continue
            if (cd.date, emp.name) in pinned_on:
                continue
            if _is_weekend_or_holiday(cd.date, holidays):
                continue
            if emp.is_blocked(cd.date):
                continue
            if emp.is_day_off_weekly(cd.date):
                continue
            if _had_evening_before(emp.name, ci, days, carry_over_last_shift):
                continue
            if _consec_work_if_added(emp.name, ci, days, carry_over_cw) > _max_cw_postprocess(emp):
                continue
            emp_comp_candidates.append(ci)

        if not emp_comp_candidates:
            continue

        emp_comp_candidates.sort(
            key=lambda ci: (
                0 if _is_isolated_off_at(emp.name, ci, days) else 1,
                abs(ci - isolated_idx),
            )
        )

        count_partner_before = _count_isolated_off(partner.name, days)

        shift_list.remove(emp.name)
        free_day.day_off.append(emp.name)
        if partner_source == "workday":
            free_day.workday.remove(partner.name)
        else:
            free_day.day_off.remove(partner.name)
        shift_list.append(partner.name)

        comp_accepted = False
        for ci in emp_comp_candidates:
            cd = days[ci]
            cd.day_off.remove(emp.name)
            cd.workday.append(emp.name)

            ce = _count_isolated_off(emp.name, days)
            cp = _count_isolated_off(partner.name, days)

            if ce < count_before and cp <= count_partner_before:
                comp_accepted = True
                break

            cd.workday.remove(emp.name)
            cd.day_off.append(emp.name)

        if comp_accepted:
            return True

        shift_list.remove(partner.name)
        if partner_source == "workday":
            free_day.workday.append(partner.name)
        else:
            free_day.day_off.append(partner.name)
        free_day.day_off.remove(emp.name)
        shift_list.append(emp.name)

    return False


def _minimize_isolated_off(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
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
) -> list[DaySchedule]:
    flex_duty = [
        e
        for e in employees
        if e.on_duty and e.schedule_type == ScheduleType.FLEXIBLE and not _duty_only(e)
    ]
    if len(flex_duty) < 2:
        return days

    for _ in range(len(days)):
        iso_counts = {e.name: _count_isolated_off(e.name, days) for e in flex_duty}
        max_name = max(iso_counts, key=lambda n: iso_counts[n])
        min_name = min(iso_counts, key=lambda n: iso_counts[n])
        max_val = iso_counts[max_name]
        min_val = iso_counts[min_name]

        if max_val - min_val <= 1 or max_val <= 2:
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


def _trim_long_off_blocks(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
) -> list[DaySchedule]:
    """
    Для гибких дежурных: обрезать блоки выходных длиной ≥ 3 до ≤ 2,
    одновременно расширяя изолированный выходной до пары (своп без изменения нормы).
    Если изолированный кандидат не найден, просто конвертируем день блока в WORKDAY
    (небольшой избыток скорректирует _target_adjustment_pass при повторном вызове).
    """

    def is_off_day(name: str, d: DaySchedule) -> bool:
        return name in d.day_off or name in d.vacation

    for emp in employees:
        if not emp.on_duty or _duty_only(emp):
            continue
        if emp.schedule_type != ScheduleType.FLEXIBLE:
            continue
        max_cw = _max_cw_postprocess(emp)

        for _ in range(len(days)):
            changed = False

            i = 0
            while i < len(days):
                if not is_off_day(emp.name, days[i]):
                    i += 1
                    continue
                j = i
                while j < len(days) and is_off_day(emp.name, days[j]):
                    j += 1
                block_len = j - i
                if block_len <= _max_co(emp):
                    i = j
                    continue

                candidates = []
                for k in range(i, j):
                    if emp.name not in days[k].day_off:
                        continue
                    if (days[k].date, emp.name) in pinned_on:
                        continue
                    if _is_weekend_or_holiday(days[k].date, holidays):
                        continue
                    if emp.is_blocked(days[k].date):
                        continue
                    if emp.is_day_off_weekly(days[k].date):
                        continue
                    if _had_evening_before(emp.name, k, days, carry_over_last_shift):
                        continue
                    if _consec_work_if_added(emp.name, k, days, carry_over_cw) > max_cw:
                        continue
                    candidates.append(k)

                if not candidates:
                    i = j
                    continue

                candidates.sort(key=lambda k: min(k - i, j - 1 - k))
                trim_idx = candidates[0]

                if trim_idx is None:
                    i = j
                    continue

                paired = False
                for iso_i, iso_day in enumerate(days):
                    if emp.name not in iso_day.day_off:
                        continue
                    if iso_i >= i and iso_i < j:
                        continue
                    t_left = iso_i == 0 or is_off_day(emp.name, days[iso_i - 1])
                    t_right = iso_i == len(days) - 1 or is_off_day(emp.name, days[iso_i + 1])
                    if t_left or t_right:
                        continue
                    for nb_i in [iso_i - 1, iso_i + 1]:
                        if nb_i < 0 or nb_i >= len(days):
                            continue
                        if emp.name not in days[nb_i].workday:
                            continue
                        if (days[nb_i].date, emp.name) in pinned_on:
                            continue
                        outer = nb_i - 1 if nb_i < iso_i else nb_i + 1
                        if 0 <= outer < len(days) and is_off_day(emp.name, days[outer]):
                            continue
                        days[trim_idx].day_off.remove(emp.name)
                        days[trim_idx].workday.append(emp.name)
                        days[nb_i].workday.remove(emp.name)
                        days[nb_i].day_off.append(emp.name)
                        paired = True
                        changed = True
                        break
                    if paired:
                        break

                if not paired:
                    days[trim_idx].day_off.remove(emp.name)
                    days[trim_idx].workday.append(emp.name)
                    changed = True

                i = j

            if not changed:
                break

    return days


def _target_adjustment_pass(
    days: list[DaySchedule],
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
) -> list[DaySchedule]:
    """
    Пост-обработка: скорректировать WORKDAY/DAY_OFF, чтобы каждый сотрудник
    отработал ровно столько дней, сколько предписывает производственный календарь.

    - Избыток: снимаем WORKDAY (с конца месяца), не создавая цепочек выходных > MAX.
    - Недостача: добавляем WORKDAY (с начала месяца), не создавая цепочек рабочих > MAX+1.
    """
    moscow_duty_names = {
        e.name for e in employees if e.on_duty and e.city == City.MOSCOW and not _duty_only(e)
    }

    def _can_remove_workday(emp_name: str, day: DaySchedule) -> bool:
        if emp_name not in moscow_duty_names:
            return True
        if _is_weekend_or_holiday(day.date, holidays):
            return True
        others_on_workday = sum(1 for n in day.workday if n != emp_name and n in moscow_duty_names)
        return others_on_workday >= 1

    for emp in employees:
        if not emp.on_duty:
            continue

        state = states[emp.name]
        target = state.effective_target
        actual = state.total_working

        if actual > target:
            excess = actual - target
            for i in range(len(days) - 1, -1, -1):
                if excess == 0:
                    break
                day = days[i]
                if (
                    emp.name in day.workday
                    and not _is_weekend_or_holiday(day.date, holidays)
                    and (day.date, emp.name) not in pinned_on
                    and _streak_around(emp.name, i, days, working=False) <= _max_co(emp)
                ):
                    if not _can_remove_workday(emp.name, day):
                        continue
                    if (
                        emp.schedule_type == ScheduleType.FLEXIBLE
                        and emp.on_duty
                        and not _duty_only(emp)
                        and emp.workload_pct == 100
                    ):
                        _left_len = 0
                        for _li in range(i - 1, -1, -1):
                            if _is_working_on_day(emp.name, days[_li]):
                                _left_len += 1
                            else:
                                break
                        if 0 < _left_len < MIN_WORK_BETWEEN_OFFS:
                            continue
                        _right_len = 0
                        for _ri in range(i + 1, len(days)):
                            if _is_working_on_day(emp.name, days[_ri]):
                                _right_len += 1
                            else:
                                break
                        if 0 < _right_len < MIN_WORK_BETWEEN_OFFS:
                            continue
                    if emp.schedule_type == ScheduleType.FLEXIBLE and emp.on_duty:
                        _lw = i > 0 and _is_working_on_day(emp.name, days[i - 1])
                        _rw = i < len(days) - 1 and _is_working_on_day(emp.name, days[i + 1])
                        if _lw and _rw:
                            continue
                    day.workday.remove(emp.name)
                    day.day_off.append(emp.name)
                    state.total_working -= 1
                    excess -= 1
            if excess > 0:
                for i in range(len(days) - 1, -1, -1):
                    if excess == 0:
                        break
                    day = days[i]
                    if (
                        emp.name in day.workday
                        and not _is_weekend_or_holiday(day.date, holidays)
                        and (day.date, emp.name) not in pinned_on
                    ):
                        day.workday.remove(emp.name)
                        day.day_off.append(emp.name)
                        state.total_working -= 1
                        excess -= 1
                if excess > 0:
                    logger.warning(
                        "Не удалось убрать избыток рабочих дней",
                        employee=emp.name,
                        excess=excess,
                    )

        elif actual < target and not _duty_only(emp):
            deficit = target - actual

            def _off_block_priority(idx: int, _emp: Employee = emp) -> int:
                def _is_off(di: int, _e: Employee = _emp) -> bool:
                    if di < 0 or di >= len(days):
                        return False
                    return _e.name in days[di].day_off or _e.name in days[di].vacation

                if not _is_off(idx):
                    return 1

                block_size = 1
                left = idx - 1
                while left >= 0 and _is_off(left):
                    block_size += 1
                    left -= 1
                right = idx + 1
                while right < len(days) and _is_off(right):
                    block_size += 1
                    right += 1

                if block_size == 1:
                    return 0
                if block_size >= 3:
                    return 1
                return 2

            prefer_isolated = emp.schedule_type == ScheduleType.FLEXIBLE and emp.on_duty
            day_indices: list[int] = list(range(len(days)))
            if prefer_isolated:
                day_indices.sort(key=lambda idx: (_off_block_priority(idx), idx))

            for i in day_indices:
                if deficit == 0:
                    break
                day = days[i]
                if (
                    emp.name not in day.day_off
                    or _is_weekend_or_holiday(day.date, holidays)
                    or emp.is_blocked(day.date)
                    or emp.is_day_off_weekly(day.date)
                ):
                    continue
                if _had_evening_before(emp.name, i, days, carry_over_last_shift):
                    continue
                if _streak_around(
                    emp.name, i, days, working=True, carry_over_cw=carry_over_cw
                ) > _max_cw(emp):
                    continue
                day.day_off.remove(emp.name)
                day.workday.append(emp.name)
                state.total_working += 1
                deficit -= 1
            if deficit > 0:
                logger.warning(
                    "Не удалось закрыть недостачу рабочих дней",
                    employee=emp.name,
                    deficit=deficit,
                )

    return days


def _balance_weekend_work(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
) -> list[DaySchedule]:
    """
    Пост-обработка: выровнять число рабочих суббот/воскресений между дежурными
    гибкого графика одного города. Разница max−min должна быть ≤ 1.

    Принцип: swap между перегруженным (A) и недогруженным (B) в выходной день
    (сб/вс), где A несёт дежурство (утро/вечер/ночь), а B стоит «выходным» (DAY_OFF).
    Балансировка меняет total_working — caller обязан пересчитать состояния.
    """
    day_by_date = {d.date: d for d in days}
    day_idx_map = {d.date: i for i, d in enumerate(days)}
    weekend_days = [d for d in days if d.date.weekday() >= 5]
    if not weekend_days:
        return days

    for city in [City.MOSCOW, City.KHABAROVSK]:
        duty_emps = [
            e
            for e in employees
            if e.city == city and e.on_duty and e.schedule_type == ScheduleType.FLEXIBLE
        ]
        if len(duty_emps) < 2:
            continue

        duty_attrs = ["morning", "evening"] if city == City.MOSCOW else ["night"]

        for _ in range(len(weekend_days) * len(duty_emps)):
            counts: dict[str, int] = {
                e.name: sum(
                    1 for d in weekend_days for attr in duty_attrs if e.name in getattr(d, attr)
                )
                for e in duty_emps
            }
            max_name = max(counts, key=counts.__getitem__)
            min_name = min(counts, key=counts.__getitem__)
            if counts[max_name] - counts[min_name] <= 1:
                break

            swapped = False
            for day in weekend_days:
                if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                    continue
                if min_name in day.vacation or max_name in day.vacation:
                    continue

                max_attr = next(
                    (attr for attr in duty_attrs if max_name in getattr(day, attr)),
                    None,
                )
                if max_attr is None:
                    continue

                if min_name not in day.day_off:
                    continue

                min_emp = next(e for e in duty_emps if e.name == min_name)
                if max_attr == "morning" and not min_emp.can_work_morning():
                    continue
                if max_attr == "evening" and not min_emp.can_work_evening():
                    continue

                if max_attr == "morning" and min_emp.max_morning_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.morning)
                    if cur >= min_emp.max_morning_shifts:
                        continue
                if max_attr == "evening" and min_emp.max_evening_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.evening)
                    if cur >= min_emp.max_evening_shifts:
                        continue
                if max_attr == "night" and min_emp.max_night_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.night)
                    if cur >= min_emp.max_night_shifts:
                        continue

                prev = day_by_date.get(day.date - timedelta(days=1))
                if max_attr == "morning" and prev and min_name in prev.evening:
                    continue

                nxt = day_by_date.get(day.date + timedelta(days=1))
                if (
                    max_attr == "evening"
                    and nxt
                    and (min_name in nxt.morning or min_name in nxt.workday)
                ):
                    continue

                if _consec_work_if_added(
                    min_name, day_idx_map[day.date], days, carry_over_cw
                ) > _max_cw(min_emp):
                    continue

                _wk_idx = day_idx_map[day.date]
                _consec_limit = getattr(min_emp, f"max_consecutive_{max_attr}", None)
                if _consec_limit is not None and (
                    _consecutive_shift_count_at(min_name, _wk_idx, days, max_attr) >= _consec_limit
                ):
                    continue

                max_emp = next(e for e in duty_emps if e.name == max_name)
                if max_emp.schedule_type == ScheduleType.FLEXIBLE:
                    max_idx = day_idx_map[day.date]
                    _off_streak = 1
                    for _li in range(max_idx - 1, -1, -1):
                        if max_name in days[_li].day_off or max_name in days[_li].vacation:
                            _off_streak += 1
                        else:
                            break
                    for _ri in range(max_idx + 1, len(days)):
                        if max_name in days[_ri].day_off or max_name in days[_ri].vacation:
                            _off_streak += 1
                        else:
                            break
                    if _off_streak > _max_co(max_emp):
                        continue

                getattr(day, max_attr).remove(max_name)
                day.day_off.append(max_name)
                day.day_off.remove(min_name)
                getattr(day, max_attr).append(min_name)
                swapped = True
                break

            if not swapped:
                break

    return days


def _balance_duty_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
) -> list[DaySchedule]:
    """
    Пост-обработка: выровнять число дежурных смен между сотрудниками одного города.
    Разница max−min должна быть ≤ 1.

    Принцип: swap между перегруженным (A) и недогруженным (B) в будний день,
    где A несёт дежурство (утро/вечер/ночь), а B стоит «рабочим днём» (WORKDAY).
    Оба по-прежнему отрабатывают один рабочий день — итоговый счёт не меняется.
    """
    for city in [City.MOSCOW, City.KHABAROVSK]:
        duty_emps = [e for e in employees if e.city == city and e.on_duty and not _duty_only(e)]
        if len(duty_emps) < 2:
            continue

        duty_attrs = ["morning", "evening"] if city == City.MOSCOW else ["night"]

        day_by_date = {d.date: d for d in days}
        day_idx_map = {d.date: i for i, d in enumerate(days)}
        emp_by_name = {e.name: e for e in duty_emps}

        for _ in range(len(days) * len(duty_emps)):
            counts: dict[str, int] = {
                e.name: sum(1 for d in days for attr in duty_attrs if e.name in getattr(d, attr))
                for e in duty_emps
            }
            max_name = max(counts, key=counts.__getitem__)
            min_name = min(counts, key=counts.__getitem__)
            if counts[max_name] - counts[min_name] <= 1:
                break

            swapped = False
            for day in days:
                if _is_weekend_or_holiday(day.date, holidays):
                    continue
                if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                    continue

                max_attr = next(
                    (attr for attr in duty_attrs if max_name in getattr(day, attr)),
                    None,
                )
                if max_attr is None:
                    continue

                if min_name not in day.workday:
                    continue

                min_emp = next(e for e in duty_emps if e.name == min_name)
                if max_attr == "morning" and not min_emp.can_work_morning():
                    continue
                if max_attr == "evening" and not min_emp.can_work_evening():
                    continue

                if max_attr == "morning" and min_emp.max_morning_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.morning)
                    if cur >= min_emp.max_morning_shifts:
                        continue
                if max_attr == "evening" and min_emp.max_evening_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.evening)
                    if cur >= min_emp.max_evening_shifts:
                        continue
                if max_attr == "night" and min_emp.max_night_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.night)
                    if cur >= min_emp.max_night_shifts:
                        continue

                prev = day_by_date.get(day.date - timedelta(days=1))
                if prev and max_name in prev.evening:
                    continue
                if max_attr == "morning" and prev and min_name in prev.evening:
                    continue

                nxt = day_by_date.get(day.date + timedelta(days=1))
                if (
                    max_attr == "evening"
                    and nxt
                    and (min_name in nxt.morning or min_name in nxt.workday)
                ):
                    continue

                idx = day_idx_map[day.date]
                _consec_limit = getattr(
                    emp_by_name.get(min_name), f"max_consecutive_{max_attr}", None
                )
                if (
                    _consec_limit is not None
                    and _consecutive_shift_count_at(min_name, idx, days, max_attr) >= _consec_limit
                ):
                    continue

                getattr(day, max_attr).remove(max_name)
                day.workday.append(max_name)
                day.workday.remove(min_name)
                getattr(day, max_attr).append(min_name)
                swapped = True
                break

            if not swapped:
                break

    return days


def _balance_evening_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
) -> list[DaySchedule]:
    eligible = [
        e
        for e in employees
        if e.city == City.MOSCOW
        and e.on_duty
        and not _duty_only(e)
        and e.can_work_morning()
        and e.can_work_evening()
    ]
    if len(eligible) < 2:
        return days

    day_by_date = {d.date: d for d in days}
    day_idx_map = {d.date: i for i, d in enumerate(days)}
    emp_by_name = {e.name: e for e in eligible}

    for _ in range(len(days) * len(eligible)):
        counts: dict[str, int] = {
            e.name: sum(1 for d in days if e.name in d.evening) for e in eligible
        }
        sorted_by_count = sorted(eligible, key=lambda e: counts[e.name])
        max_name = max(counts, key=counts.__getitem__)
        if counts[max_name] - counts[sorted_by_count[0].name] <= 1:
            break

        swapped = False
        for candidate in sorted_by_count:
            min_name = candidate.name
            if counts[max_name] - counts[min_name] <= 1:
                break

            for day in days:
                if max_name not in day.evening or min_name not in day.morning:
                    continue
                if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                    continue

                prev = day_by_date.get(day.date - timedelta(days=1))
                if prev and max_name in prev.evening:
                    continue

                nxt = day_by_date.get(day.date + timedelta(days=1))
                if nxt and (min_name in nxt.morning or min_name in nxt.workday):
                    continue

                max_emp = emp_by_name[max_name]
                if max_emp.max_morning_shifts is not None:
                    cur = sum(1 for d in days if max_name in d.morning)
                    if cur >= max_emp.max_morning_shifts:
                        continue

                min_emp = emp_by_name[min_name]
                if min_emp.max_evening_shifts is not None:
                    cur = sum(1 for d in days if min_name in d.evening)
                    if cur >= min_emp.max_evening_shifts:
                        continue

                idx = day_idx_map[day.date]

                if (
                    max_emp.max_consecutive_morning is not None
                    and _consecutive_shift_count_at(max_name, idx, days, "morning")
                    >= max_emp.max_consecutive_morning
                ):
                    continue

                if (
                    min_emp.max_consecutive_evening is not None
                    and _consecutive_shift_count_at(min_name, idx, days, "evening")
                    >= min_emp.max_consecutive_evening
                ):
                    continue

                day.evening.remove(max_name)
                day.morning.remove(min_name)
                day.evening.append(min_name)
                day.morning.append(max_name)
                swapped = True
                break

            if not swapped:
                for day in days:
                    if max_name not in day.evening or min_name not in day.workday:
                        continue
                    if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                        continue

                    prev = day_by_date.get(day.date - timedelta(days=1))
                    if prev and max_name in prev.evening:
                        continue

                    nxt = day_by_date.get(day.date + timedelta(days=1))
                    if nxt and (min_name in nxt.morning or min_name in nxt.workday):
                        continue

                    min_emp = emp_by_name[min_name]
                    if min_emp.max_evening_shifts is not None:
                        cur = sum(1 for d in days if min_name in d.evening)
                        if cur >= min_emp.max_evening_shifts:
                            continue

                    idx = day_idx_map[day.date]

                    if (
                        min_emp.max_consecutive_evening is not None
                        and _consecutive_shift_count_at(min_name, idx, days, "evening")
                        >= min_emp.max_consecutive_evening
                    ):
                        continue

                    day.evening.remove(max_name)
                    day.workday.remove(min_name)
                    day.evening.append(min_name)
                    day.workday.append(max_name)
                    swapped = True
                    break

            if not swapped:
                for day in days:
                    if max_name not in day.evening or min_name not in day.day_off:
                        continue
                    if (day.date, max_name) in pinned_on or (day.date, min_name) in pinned_on:
                        continue

                    min_emp = emp_by_name[min_name]
                    max_emp = emp_by_name[max_name]
                    if min_emp.is_day_off_weekly(day.date):
                        continue

                    nxt = day_by_date.get(day.date + timedelta(days=1))
                    if nxt and (min_name in nxt.morning or min_name in nxt.workday):
                        continue

                    if min_emp.max_evening_shifts is not None:
                        cur = sum(1 for d in days if min_name in d.evening)
                        if cur >= min_emp.max_evening_shifts:
                            continue

                    idx_d = day_idx_map[day.date]
                    if (
                        min_emp.max_consecutive_evening is not None
                        and _consecutive_shift_count_at(min_name, idx_d, days, "evening")
                        >= min_emp.max_consecutive_evening
                    ):
                        continue

                    _max_cw_min = min_emp.max_consecutive_working or MAX_CONSECUTIVE_WORKING_DEFAULT
                    cw = 1
                    for i in range(idx_d - 1, -1, -1):
                        if min_name in days[i].all_assigned():
                            cw += 1
                        else:
                            break
                    if cw > _max_cw_min:
                        continue

                    comp_day = None
                    comp_shift = ""
                    for cd in days:
                        if cd.date == day.date:
                            continue
                        if max_name not in cd.day_off:
                            continue
                        if (cd.date, min_name) in pinned_on or (cd.date, max_name) in pinned_on:
                            continue
                        if max_emp.is_day_off_weekly(cd.date):
                            continue
                        prev_cd = day_by_date.get(cd.date - timedelta(days=1))
                        if prev_cd and max_name in prev_cd.evening:
                            continue
                        idx_cd = day_idx_map[cd.date]
                        _max_cw_max = (
                            max_emp.max_consecutive_working or MAX_CONSECUTIVE_WORKING_DEFAULT
                        )
                        cw_max = 1
                        for i in range(idx_cd - 1, -1, -1):
                            if max_name in days[i].all_assigned():
                                cw_max += 1
                            else:
                                break
                        for i in range(idx_cd + 1, len(days)):
                            if max_name in days[i].all_assigned():
                                cw_max += 1
                            else:
                                break
                        if cw_max > _max_cw_max:
                            continue
                        if min_name in cd.workday:
                            comp_day = cd
                            comp_shift = "workday"
                            break
                        if min_name in cd.morning and not max_emp.evening_only:
                            if max_emp.max_morning_shifts is not None:
                                cur_mo = sum(1 for d2 in days if max_name in d2.morning)
                                if cur_mo >= max_emp.max_morning_shifts:
                                    continue
                            if (
                                max_emp.max_consecutive_morning is not None
                                and _consecutive_shift_count_at(max_name, idx_cd, days, "morning")
                                >= max_emp.max_consecutive_morning
                            ):
                                continue
                            comp_day = cd
                            comp_shift = "morning"
                            break

                    if comp_day is None:
                        continue

                    day.evening.remove(max_name)
                    day.day_off.remove(min_name)
                    day.evening.append(min_name)
                    day.day_off.append(max_name)
                    getattr(comp_day, comp_shift).remove(min_name)
                    comp_day.day_off.remove(max_name)
                    comp_day.day_off.append(min_name)
                    getattr(comp_day, comp_shift).append(max_name)
                    swapped = True
                    break

            if swapped:
                break

        if not swapped:
            break

    return days
