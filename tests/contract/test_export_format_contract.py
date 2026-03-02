from __future__ import annotations

import tempfile
from pathlib import Path

from icalendar import Calendar

from duty_schedule.export.ics import export_ics
from duty_schedule.export.xls import export_xls
from duty_schedule.models import Schedule
from duty_schedule.scheduler import generate_schedule


def _generate(config) -> Schedule:
    holidays = set()
    return generate_schedule(config, holidays)


class TestXlsFormatContract:
    def test_xls_file_created(self, minimal_config):
        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_xls(schedule, Path(tmpdir))
            assert path.exists()
            assert path.suffix == ".xlsx"

    def test_xls_has_content(self, minimal_config):
        from openpyxl import load_workbook

        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = export_xls(schedule, Path(tmpdir))
            wb = load_workbook(path)
            assert len(wb.sheetnames) >= 1
            ws = wb.active
            assert ws.max_row > 1
            assert ws.max_column > 1


class TestIcsFormatContract:
    def test_ics_files_created(self, minimal_config):
        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_ics(schedule, Path(tmpdir))
            assert len(paths) == 4
            for p in paths:
                assert p.exists()
                assert p.suffix == ".ics"

    def test_ics_filenames(self, minimal_config):
        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_ics(schedule, Path(tmpdir))
            names = {p.name for p in paths}
            assert names == {"morning.ics", "evening.ics", "night.ics", "workday.ics"}

    def test_ics_valid_ical(self, minimal_config):
        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_ics(schedule, Path(tmpdir))
            for p in paths:
                cal = Calendar.from_ical(p.read_bytes())
                assert cal.get("VERSION") == "2.0"
                assert "Duty Schedule" in str(cal.get("PRODID"))

    def test_ics_has_events(self, minimal_config):
        schedule = _generate(minimal_config)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_ics(schedule, Path(tmpdir))
            total_events = 0
            for p in paths:
                cal = Calendar.from_ical(p.read_bytes())
                events = [c for c in cal.walk() if c.name == "VEVENT"]
                total_events += len(events)
            assert total_events > 0
