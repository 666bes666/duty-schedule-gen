from __future__ import annotations

from datetime import date, timedelta

from duty_schedule.constants import MAX_CONSECUTIVE_WORKING_DEFAULT
from duty_schedule.models import (
    City,
    DaySchedule,
    Employee,
    ScheduleType,
)
from duty_schedule.scheduler.changelog import ChangeLog
from duty_schedule.scheduler.constraints import (
    _consecutive_shift_count_at,
    _duty_only,
    _is_weekend_or_holiday,
    _max_co,
    _max_cw,
)

from .helpers import _consec_work_if_added


def _balance_weekend_work(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
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


def _balance_evening_shifts(
    days: list[DaySchedule],
    employees: list[Employee],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    changelog: ChangeLog | None = None,
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

                    _max_cw_min = min_emp.max_consecutive_working or MAX_CONSECUTIVE_WORKING_DEFAULT
                    cw = 1
                    for i in range(idx_d - 1, -1, -1):
                        if min_name in days[i].all_assigned():
                            cw += 1
                        else:
                            break
                    for i in range(idx_d + 1, len(days)):
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

            if swapped:
                break

        if not swapped:
            break

    return days
