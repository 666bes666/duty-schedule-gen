from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from duty_schedule.api.schemas import (
    ConfigValidationResponse,
    EmployeeStatsSchema,
    ErrorResponse,
    HolidaysResponse,
)


class TestConfigValidationResponse:
    def test_valid_response(self) -> None:
        resp = ConfigValidationResponse(valid=True, errors=[], warnings=[])
        assert resp.valid is True
        assert resp.errors == []
        assert resp.warnings == []

    def test_invalid_response_with_messages(self) -> None:
        resp = ConfigValidationResponse(
            valid=False,
            errors=["No employees"],
            warnings=["Carry-over ignored"],
        )
        assert resp.valid is False
        assert len(resp.errors) == 1
        assert len(resp.warnings) == 1


class TestHolidaysResponse:
    def test_basic(self) -> None:
        resp = HolidaysResponse(
            year=2025,
            month=3,
            holidays=[date(2025, 3, 8)],
            short_days=[date(2025, 3, 7)],
        )
        assert resp.year == 2025
        assert resp.month == 3
        assert resp.holidays == [date(2025, 3, 8)]

    def test_empty_lists(self) -> None:
        resp = HolidaysResponse(year=2025, month=1, holidays=[], short_days=[])
        assert resp.holidays == []
        assert resp.short_days == []


class TestEmployeeStatsSchema:
    def test_all_fields(self) -> None:
        stats = EmployeeStatsSchema(
            name="Иванов",
            city="Москва",
            total_working=20,
            target=21,
            morning=7,
            evening=6,
            night=0,
            workday=7,
            day_off=8,
            vacation=3,
            weekend_work=4,
            holiday_work=1,
            max_streak_work=5,
            max_streak_rest=3,
            isolated_off=2,
            paired_off=3,
            total_hours=160,
        )
        assert stats.name == "Иванов"
        assert stats.total_working == 20

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            EmployeeStatsSchema(name="Иванов", city="Москва")  # type: ignore[call-arg]


class TestErrorResponse:
    def test_basic(self) -> None:
        resp = ErrorResponse(error="schedule_error", detail="Cannot build schedule")
        assert resp.error == "schedule_error"
        assert resp.detail == "Cannot build schedule"
