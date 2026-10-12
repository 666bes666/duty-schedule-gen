from datetime import date

import pytest

from duty_schedule.models import CarryOverState, DaySchedule, ShiftType
from duty_schedule.scheduler.postprocess.carry_over_calc import compute_carry_over
from duty_schedule.xls_import import XlsImportError, _build_carry_over, _resolve_shift


def test_mixed_working_streak_is_distinct_from_identical_shift_streak():
    carry = _build_carry_over("employee", [ShiftType.WORKDAY, ShiftType.MORNING, ShiftType.EVENING])
    assert carry.consecutive_working == 3
    assert carry.consecutive_same_shift == 1


def test_all_rest_month_continues_initial_rest_and_tracks_period(minimal_employees):
    employee = minimal_employees[0]
    initial = [
        CarryOverState(
            employee_name=employee.name,
            employee_id=employee.employee_id,
            last_shift=ShiftType.DAY_OFF,
            consecutive_off=4,
            as_of=date(2026, 3, 31),
            source="manual",
        )
    ]
    days = [DaySchedule(date=date(2026, 4, d), day_off=[employee.name]) for d in range(1, 31)]
    carry = compute_carry_over(days, [employee], initial_history=initial)[0]
    assert carry["consecutive_off"] == 34
    assert carry["employee_id"] == employee.employee_id
    assert carry["as_of"] == "2026-04-30"
    assert carry["source"] == "schedule"


def test_partial_workday_and_sick_labels_are_recognized():
    assert _resolve_shift("День (3 ч)") == ShiftType.WORKDAY
    assert _resolve_shift("Б") == ShiftType.SICK_LEAVE
    with pytest.raises(XlsImportError):
        _resolve_shift("unknown edited label")
