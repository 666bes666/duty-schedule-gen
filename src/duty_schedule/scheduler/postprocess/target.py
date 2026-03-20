from __future__ import annotations

from datetime import date

from duty_schedule.constants import MIN_WORK_BETWEEN_OFFS
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
    _duty_only,
    _had_evening_before,
    _is_weekend_or_holiday,
    _is_working_on_day,
    _max_co,
    _max_cw,
)
from duty_schedule.scheduler.core import EmployeeState

from .helpers import _streak_around

logger = get_logger(__name__)


def _target_adjustment_pass(
    days: list[DaySchedule],
    employees: list[Employee],
    states: dict[str, EmployeeState],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
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
                    if changelog:
                        changelog.add(
                            "target_adjust",
                            "remove_workday",
                            emp.name,
                            day.date,
                            f"workday → day_off (excess={excess})",
                        )
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
                        if changelog:
                            changelog.add(
                                "target_adjust",
                                "remove_workday",
                                emp.name,
                                day.date,
                                f"workday → day_off fallback (excess={excess})",
                            )
                    if excess > 0:
                        logger.warning(
                            "excess_workdays_not_removed",
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
                if changelog:
                    changelog.add(
                        "target_adjust",
                        "add_workday",
                        emp.name,
                        day.date,
                        f"day_off → workday (deficit={deficit})",
                    )
            if deficit > 0:
                logger.warning(
                    "deficit_workdays_not_filled",
                    employee=emp.name,
                    deficit=deficit,
                )

    return days


def _trim_long_off_blocks(
    days: list[DaySchedule],
    employees: list[Employee],
    holidays: set[date],
    pinned_on: frozenset[tuple[date, str]] | set[tuple[date, str]] = frozenset(),
    carry_over_cw: dict[str, int] | None = None,
    carry_over_last_shift: dict[str, ShiftType] | None = None,
    changelog: ChangeLog | None = None,
) -> list[DaySchedule]:
    def is_off_day(name: str, d: DaySchedule) -> bool:
        return name in d.day_off or name in d.vacation

    for emp in employees:
        if not emp.on_duty or _duty_only(emp):
            continue
        if emp.schedule_type != ScheduleType.FLEXIBLE:
            continue
        from duty_schedule.scheduler.constraints import _max_cw_postprocess

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
                    from .helpers import _consec_work_if_added

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
