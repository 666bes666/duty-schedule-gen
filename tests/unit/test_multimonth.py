from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from duty_schedule.calendar import calendar_for_config
from duty_schedule.scheduler.multimonth import _next_month, generate_multimonth


def test_next_month_normal() -> None:
    assert _next_month(2026, 3) == (2026, 4)


def test_next_month_december() -> None:
    assert _next_month(2026, 12) == (2027, 1)


def test_next_month_january() -> None:
    assert _next_month(2026, 1) == (2026, 2)


def test_range_keeps_ready_month_and_stops_on_first_diagnostic(planning_config):
    second = planning_config.model_copy(update={"month": 5, "production_calendar": None})
    calendar = calendar_for_config(second)
    calendar.verified = True
    calendar.source = "fixture"
    for employee in planning_config.employees[-2:]:
        employee.unavailable_dates = [date(2026, 5, 1)]
    with patch(
        "duty_schedule.scheduler.multimonth.fetch_production_calendar",
        side_effect=AssertionError("network"),
    ):
        result = generate_multimonth(
            planning_config,
            4,
            2026,
            6,
            2026,
            saved_calendars=[planning_config.production_calendar, calendar],
        )
    assert len(result) == 2
    assert result[0].status == "ready"
    assert result[1].status == "diagnostic"
    assert all(carry.as_of == date(2026, 4, 30) for carry in result[1].config.carry_over)


def test_range_rejects_reverse_period(planning_config):
    with pytest.raises(ValueError):
        generate_multimonth(planning_config, 5, 2026, 4, 2026)
