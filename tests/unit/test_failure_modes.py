from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest

from duty_schedule.calendar import CalendarError, fetch_holidays
from duty_schedule.models import (
    City,
    Config,
    DaySchedule,
    Employee,
    Schedule,
    ScheduleType,
)
from duty_schedule.scheduler.solver import SolverUnavailableError, solve_schedule
from duty_schedule.xls_import import XlsImportError, parse_carry_over_from_xls


def _emp(name: str, city: City = City.MOSCOW) -> Employee:
    return Employee(name=name, city=city, schedule_type=ScheduleType.FLEXIBLE)


_EMPLOYEES = [
    _emp("A"),
    _emp("B"),
    _emp("C"),
    _emp("D"),
    _emp("E", City.KHABAROVSK),
    _emp("F", City.KHABAROVSK),
]


def _minimal_schedule() -> Schedule:
    return Schedule(
        config=Config(
            month=3,
            year=2025,
            seed=42,
            employees=_EMPLOYEES,
        ),
        days=[
            DaySchedule(
                date=date(2025, 3, 1),
                morning=["A"],
                evening=["B"],
                night=[],
                workday=[],
                day_off=[],
                vacation=[],
            ),
        ],
    )


class TestWeasyPrintUnavailable:
    def test_oserror_raises_runtime_error(self) -> None:
        import builtins

        from duty_schedule.export.pdf import generate_schedule_pdf

        schedule = _minimal_schedule()

        _real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "weasyprint":
                raise OSError("cannot load library 'libgobject-2.0-0'")
            return _real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_fake_import),
            pytest.raises(RuntimeError, match="weasyprint unavailable"),
        ):
            generate_schedule_pdf(schedule)


class TestCalendarAPITimeout:
    def test_timeout_raises_calendar_error(self) -> None:
        with (
            patch(
                "duty_schedule.calendar.httpx.get",
                side_effect=httpx.TimeoutException("timeout"),
            ),
            pytest.raises(CalendarError, match="Не удалось получить"),
        ):
            fetch_holidays(2025, 3)


class TestCalendarAPI500:
    def test_server_error_raises_calendar_error(self) -> None:
        mock_resp = httpx.Response(500, request=httpx.Request("GET", "https://example.com"))
        with (
            patch("duty_schedule.calendar.httpx.get", return_value=mock_resp),
            pytest.raises(CalendarError, match="Не удалось получить"),
        ):
            fetch_holidays(2025, 3)


class TestSolverUnavailable:
    def test_no_ortools_raises_solver_unavailable(self) -> None:
        cfg = Config(
            month=3,
            year=2025,
            seed=42,
            employees=_EMPLOYEES,
        )
        with (
            patch("duty_schedule.scheduler.solver._HAS_ORTOOLS", False),
            pytest.raises(SolverUnavailableError),
        ):
            solve_schedule(cfg, holidays=set())


class TestCorruptXlsImport:
    def test_garbage_bytes_raises_xls_import_error(self) -> None:
        with pytest.raises(XlsImportError, match="Не удалось открыть"):
            parse_carry_over_from_xls(b"\x00\x01\x02garbage")
