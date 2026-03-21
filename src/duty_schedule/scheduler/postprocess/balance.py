from __future__ import annotations

from datetime import date, timedelta
from statistics import median

from duty_schedule.logging import get_logger
from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    ScheduleType,
    ShiftType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.constraints import (
    _consecutive_shift_count_at,
    _duty_only,
    _had_evening_before,
    _is_weekend_or_holiday,
    _is_working_on_day,
    _max_co,
    _max_cw,
    _max_cw_postprocess,
)

from .helpers import _consec_work_if_added, _streak_around, build_day_lookups

logger = get_logger(__name__)


def _balance_weekend_work(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    changelog: ChangeLog | None = None,
    strict: bool = False,
) -> list[DaySchedule]:
    day_by_date, day_idx_map = build_day_lookups(days)
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
            if counts[max_name] - counts[min_name] <= (0 if strict else 1):
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
                    if _streak_around(max_name, max_idx, days, working=False) > _max_co(max_emp):
                        continue

                getattr(day, max_attr).remove(max_name)
                day.day_off.append(max_name)
                day.day_off.remove(min_name)
                getattr(day, max_attr).append(min_name)
                if changelog:
                    changelog.add(
                        "balance_weekend",
                        "swap",
                        max_name,
                        day.date,
                        f"{max_attr} → day_off, {min_name} day_off → {max_attr}",
                    )
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
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
    for city in [City.MOSCOW, City.KHABAROVSK]:
        duty_emps = [e for e in employees if e.city == city and e.on_duty and not _duty_only(e)]
        if len(duty_emps) < 2:
            continue

        duty_attrs = ["morning", "evening"] if city == City.MOSCOW else ["night"]

        day_by_date, day_idx_map = build_day_lookups(days)
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
                if changelog:
                    changelog.add(
                        "balance_duty",
                        "swap",
                        max_name,
                        day.date,
                        f"{max_attr} → workday, {min_name} workday → {max_attr}",
                    )
                swapped = True
                break

            if not swapped:
                break

    return days


def _can_take_evening(
    name: str,
    day_idx: int,
    days: list[DaySchedule],
    day_by_date: dict[date, DaySchedule],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]],
) -> bool:
    day = days[day_idx]
    if (day.date, name) in pinned_on:
        return False
    nxt = day_by_date.get(day.date + timedelta(days=1))
    return not (nxt and (name in nxt.morning or name in nxt.workday))


def _can_leave_evening(
    name: str,
    day: DaySchedule,
    day_by_date: dict[date, DaySchedule],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]],
) -> bool:
    if (day.date, name) in pinned_on:
        return False
    prev = day_by_date.get(day.date - timedelta(days=1))
    return not (prev and name in prev.evening)


def _try_three_way_rotation(
    days: list[DaySchedule],
    max_name: str,
    min_name: str,
    eligible: list[Employee],
    day_by_date: dict[date, DaySchedule],
    day_idx_map: dict[date, int],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]],
    changelog: ChangeLog | None,
) -> bool:
    mid_names = [
        e.name
        for e in eligible
        if e.name != max_name
        and e.name != min_name
        and e.can_work_morning()
        and e.can_work_evening()
    ]

    for day1 in days:
        if max_name not in day1.evening:
            continue
        if not _can_leave_evening(max_name, day1, day_by_date, pinned_on):
            continue

        for mid_name in mid_names:
            if mid_name not in day1.morning:
                continue
            if (day1.date, mid_name) in pinned_on:
                continue
            idx1 = day_idx_map[day1.date]
            if not _can_take_evening(mid_name, idx1, days, day_by_date, pinned_on):
                continue

            for day2 in days:
                if day2.date == day1.date:
                    continue
                if mid_name not in day2.evening:
                    continue
                if not _can_leave_evening(mid_name, day2, day_by_date, pinned_on):
                    continue
                if day2.date == day1.date + timedelta(days=1):
                    continue
                if min_name not in day2.morning:
                    continue
                if (day2.date, min_name) in pinned_on:
                    continue
                if not _can_take_evening(
                    min_name, day_idx_map[day2.date], days, day_by_date, pinned_on
                ):
                    continue

                day1.evening.remove(max_name)
                day1.morning.remove(mid_name)
                day1.morning.append(max_name)
                day1.evening.append(mid_name)

                day2.evening.remove(mid_name)
                day2.morning.remove(min_name)
                day2.morning.append(mid_name)
                day2.evening.append(min_name)

                if changelog:
                    changelog.add(
                        "balance_evening",
                        "three_way",
                        max_name,
                        day1.date,
                        f"3-way: {max_name}→morning, {mid_name}→evening "
                        f"(day2 {day2.date}: {mid_name}→morning, {min_name}→evening)",
                    )
                return True
    return False


def _balance_evening_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    changelog: ChangeLog | None = None,
    strict: bool = False,
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

    day_by_date, day_idx_map = build_day_lookups(days)
    emp_by_name = {e.name: e for e in eligible}

    _threshold = 0 if strict else 1
    _iterations = len(days) * len(eligible) * (3 if strict else 1)
    for _ in range(_iterations):
        counts: dict[str, int] = {
            e.name: sum(1 for d in days if e.name in d.evening) for e in eligible
        }
        sorted_by_count = sorted(eligible, key=lambda e: counts[e.name])
        max_name = max(counts, key=counts.__getitem__)
        if counts[max_name] - counts[sorted_by_count[0].name] <= _threshold:
            break

        swapped = False
        for candidate in sorted_by_count:
            min_name = candidate.name
            if counts[max_name] - counts[min_name] <= _threshold:
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

                min_emp = emp_by_name[min_name]
                max_emp = emp_by_name[max_name]

                day.evening.remove(max_name)
                day.morning.remove(min_name)
                day.evening.append(min_name)
                day.morning.append(max_name)
                if changelog:
                    changelog.add(
                        "balance_evening",
                        "swap",
                        max_name,
                        day.date,
                        f"evening → morning, {min_name} morning → evening",
                    )
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

                    day.evening.remove(max_name)
                    day.workday.remove(min_name)
                    day.evening.append(min_name)
                    day.workday.append(max_name)
                    if changelog:
                        changelog.add(
                            "balance_evening",
                            "swap",
                            max_name,
                            day.date,
                            f"evening → workday, {min_name} workday → evening",
                        )
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

                    idx_d = day_idx_map[day.date]

                    if _consec_work_if_added(min_name, idx_d, days) > _max_cw_postprocess(min_emp):
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
                        if _consec_work_if_added(max_name, idx_cd, days) > _max_cw_postprocess(
                            max_emp
                        ):
                            continue
                        if min_name in cd.workday:
                            comp_day = cd
                            comp_shift = "workday"
                            break
                        if min_name in cd.morning and not max_emp.evening_only:
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
                    if changelog:
                        changelog.add(
                            "balance_evening",
                            "swap",
                            max_name,
                            day.date,
                            f"evening → day_off, {min_name} day_off → evening "
                            f"(comp: {comp_day.date})",
                        )
                    swapped = True
                    break

            if not swapped:
                swapped = _try_three_way_rotation(
                    days,
                    max_name,
                    min_name,
                    eligible,
                    day_by_date,
                    day_idx_map,
                    pinned_on,
                    changelog,
                )

            if swapped:
                break

        if not swapped:
            break

    return days


def _minimize_max_streak(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
    changelog: ChangeLog | None = None,
    strict: bool = False,
) -> list[DaySchedule]:
    def _max_streak(name: str) -> int:
        best = 0
        cur = 0
        for d in days:
            if _is_working_on_day(name, d):
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        return best

    _iterations = len(days) * (3 if strict else 1)
    for _ in range(_iterations):
        active_emps = [e for e in employees if e.on_duty]
        if not active_emps:
            break
        streaks = {e.name: _max_streak(e.name) for e in active_emps}
        med = median(streaks.values())
        high_emps = sorted(
            [
                e
                for e in active_emps
                if (streaks[e.name] >= med if strict else streaks[e.name] > med)
            ],
            key=lambda e: -streaks[e.name],
        )
        if not high_emps:
            break

        improved = False
        for emp in high_emps:
            best_start = -1
            best_len = 0
            cur_start = -1
            cur_len = 0
            for i, d in enumerate(days):
                if _is_working_on_day(emp.name, d):
                    if cur_len == 0:
                        cur_start = i
                    cur_len += 1
                    if cur_len > best_len:
                        best_len = cur_len
                        best_start = cur_start
                else:
                    cur_len = 0

            if best_len <= med:
                continue

            mid = best_start + best_len // 2
            streak_positions = sorted(
                range(best_start, best_start + best_len),
                key=lambda i: abs(i - mid),
            )

            for streak_idx in streak_positions:
                day = days[streak_idx]
                if emp.name not in day.workday:
                    continue
                if (day.date, emp.name) in pinned_on:
                    continue

                for comp_idx, comp_day in enumerate(days):
                    if emp.name not in comp_day.day_off:
                        continue
                    if (comp_day.date, emp.name) in pinned_on:
                        continue
                    if emp.is_blocked(comp_day.date):
                        continue
                    if emp.is_day_off_weekly(comp_day.date):
                        continue
                    if abs(comp_idx - streak_idx) <= 1:
                        continue
                    if not emp.works_on_weekend() and _is_weekend_or_holiday(
                        comp_day.date, holidays
                    ):
                        continue
                    if _had_evening_before(emp.name, comp_idx, days, carry_over_last_shift):
                        continue
                    if _consec_work_if_added(
                        emp.name, comp_idx, days, carry_over_cw
                    ) > _max_cw_postprocess(emp):
                        continue

                    day.workday.remove(emp.name)
                    day.day_off.append(emp.name)
                    comp_day.day_off.remove(emp.name)
                    comp_day.workday.append(emp.name)

                    if _max_streak(emp.name) < streaks[emp.name]:
                        if changelog:
                            changelog.add(
                                "priority_streak",
                                "swap",
                                emp.name,
                                day.date,
                                f"workday → day_off, comp {comp_day.date} day_off → workday",
                            )
                        improved = True
                        break

                    comp_day.workday.remove(emp.name)
                    comp_day.day_off.append(emp.name)
                    day.day_off.remove(emp.name)
                    day.workday.append(emp.name)
                    logger.debug(
                        "streak_swap_reverted",
                        employee=emp.name,
                        day=str(day.date),
                        comp_day=str(comp_day.date),
                    )

                if improved:
                    break

            if improved:
                break

        if not improved:
            break

    return days
