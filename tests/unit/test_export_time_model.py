from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from icalendar import Calendar

from duty_schedule.export.ics import (
    _render_employee_ics_bytes,
    _shift_times,
    export_ics,
    generate_employee_ics_bytes,
)
from duty_schedule.models import Config, DaySchedule, Schedule, ShiftType
from duty_schedule.project import ExportBlockedError


def test_night_is_eight_clock_hours_in_same_date() -> None:
    start, end = _shift_times(ShiftType.NIGHT, date(2026, 12, 31), ZoneInfo("Europe/Moscow"))
    assert (end - start).total_seconds() == 8 * 3600
    assert start.date() == end.date()


def test_individual_workday_calendar_does_not_regulate_breaks(minimal_config: Config) -> None:
    name = minimal_config.employees[0].name
    schedule = Schedule(
        config=minimal_config,
        days=[DaySchedule(date=date(2025, 3, 3), workday=[name], workday_hours={name: 4})],
    )
    calendar = Calendar.from_ical(_render_employee_ics_bytes(schedule, name))
    event = calendar.walk("VEVENT")[0]
    assert event.decoded("DTSTART").hour == 9
    assert "DTEND" not in event and "DURATION" not in event
    assert "4" in str(event["DESCRIPTION"])


def test_public_ics_exports_reject_diagnostic(minimal_config: Config, tmp_path: Path) -> None:
    forged = Schedule(config=minimal_config, days=[], status="ready")
    with pytest.raises(ExportBlockedError):
        generate_employee_ics_bytes(forged, minimal_config.employees[0].name)
    with pytest.raises(ExportBlockedError):
        export_ics(forged, tmp_path)
    assert not list(tmp_path.iterdir())
