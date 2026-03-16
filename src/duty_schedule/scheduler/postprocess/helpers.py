from __future__ import annotations

from datetime import date

from duty_schedule.models import (
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
    _max_cw_postprocess,
)


def _streak_around(
    emp_name: str,
    idx: int,
    days: list[DaySchedule],
    working: bool,
    carry_over_cw: dict[str, int] | None = None,
) -> int:
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
