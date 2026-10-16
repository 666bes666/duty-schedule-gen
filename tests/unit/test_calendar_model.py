from datetime import UTC, date, datetime

import httpx
import pytest
from pydantic import ValidationError

from duty_schedule.calendar import CalendarError, fetch_production_calendar
from duty_schedule.models import CalendarDay, ProductionCalendar


def test_calendar_preserves_working_saturday_and_short_day(httpx_mock):
    codes = list("0" * 30)
    codes[4] = "2"
    httpx_mock.add_response(text="".join(codes))
    calendar = fetch_production_calendar(2026, 4)
    assert calendar.is_working(date(2026, 4, 4))
    assert calendar.hours(date(2026, 4, 5)) == 7
    assert httpx_mock.get_request().url.params["pre"] == "1"


def test_calendar_rejects_unknown_codes(httpx_mock):
    httpx_mock.add_response(text="0" * 29 + "9")
    with pytest.raises(CalendarError):
        fetch_production_calendar(2026, 4)


def test_calendar_requires_complete_unique_month():
    with pytest.raises(ValidationError):
        ProductionCalendar(
            year=2026,
            month=4,
            days=[CalendarDay(date=date(2026, 4, 1), kind="working")],
            source="fixture",
            fetched_at=datetime.now(UTC),
        )


def test_calendar_uses_only_verified_saved_requested_period(httpx_mock):
    saved = ProductionCalendar(
        year=2026,
        month=4,
        days=[CalendarDay(date=date(2026, 4, d), kind="working") for d in range(1, 31)],
        source="saved fixture",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    result = fetch_production_calendar(2026, 4, saved=saved)
    assert result.used_saved
    assert result.source == saved.source
    assert result.fetched_at == saved.fetched_at
    assert not saved.used_saved


def test_wrong_saved_period_does_not_replace_calendar(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("offline"))
    with pytest.raises(CalendarError):
        fetch_production_calendar(2026, 4)
