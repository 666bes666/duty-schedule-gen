"""Тесты загрузки производственного календаря."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest

from duty_schedule.calendar import (
    CalendarError,
    compute_short_days,
    fetch_holidays,
    get_all_days,
    parse_manual_holidays,
)


class TestGetAllDays:
    def test_march_2025(self):
        days = get_all_days(2025, 3)
        assert len(days) == 31
        assert days[0] == date(2025, 3, 1)
        assert days[-1] == date(2025, 3, 31)

    def test_february_2025_not_leap(self):
        days = get_all_days(2025, 2)
        assert len(days) == 28

    def test_february_2024_leap(self):
        days = get_all_days(2024, 2)
        assert len(days) == 29


class TestParseManualHolidays:
    def test_valid_dates(self):
        result, short = parse_manual_holidays("2025-03-08,2025-03-09", 2025, 3)
        assert date(2025, 3, 8) in result
        assert date(2025, 3, 9) in result
        assert len(result) == 2
        assert date(2025, 3, 7) in short

    def test_empty_string(self):
        result, short = parse_manual_holidays("", 2025, 3)
        assert result == set()
        assert short == set()

    def test_invalid_format_raises(self):
        with pytest.raises(CalendarError, match="Неверный формат"):
            parse_manual_holidays("08.03.2025", 2025, 3)

    def test_wrong_month_skipped(self):
        result, short = parse_manual_holidays("2025-04-01,2025-03-08", 2025, 3)
        assert date(2025, 3, 8) in result
        assert date(2025, 4, 1) not in result


class TestComputeShortDays:
    def test_april_2026_may1_pre_holiday(self):
        holidays = {date(2026, 4, d) for d in range(1, 31) if date(2026, 4, d).weekday() >= 5}
        short = compute_short_days(2026, 4, holidays)
        assert date(2026, 4, 30) in short

    def test_no_holidays_no_short_days(self):
        short = compute_short_days(2025, 7, set())
        assert short == set()

    def test_february_pre_23feb(self):
        holidays = {date(2026, 2, d) for d in range(1, 29) if date(2026, 2, d).weekday() >= 5}
        short = compute_short_days(2026, 2, holidays)
        assert date(2026, 2, 20) in short

    def test_december_pre_january_holidays(self):
        holidays = {date(2025, 12, d) for d in range(1, 32) if date(2025, 12, d).weekday() >= 5}
        short = compute_short_days(2025, 12, holidays)
        assert date(2025, 12, 31) in short

    def test_empty_holidays_with_next_month_public(self):
        short = compute_short_days(2026, 4, set())
        assert date(2026, 4, 30) in short

    def test_pre_holiday_skips_weekends(self):
        holidays = {date(2025, 3, 8)}
        short = compute_short_days(2025, 3, holidays)
        assert date(2025, 3, 7) in short


class TestFetchHolidays:
    def test_success(self):
        mock_data = "0000000100000000000000000000000"
        assert len(mock_data) == 31

        with patch("httpx.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.text = mock_data
            mock_resp.raise_for_status = lambda: None

            result, short = fetch_holidays(2025, 3)

        assert date(2025, 3, 8) in result
        assert short == set()

    def test_short_days_detected(self):
        mock_data = "0000000100000020000000000000000"
        assert len(mock_data) == 31

        with patch("httpx.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.text = mock_data
            mock_resp.raise_for_status = lambda: None

            result, short = fetch_holidays(2025, 3)

        assert date(2025, 3, 8) in result
        assert date(2025, 3, 15) in short

    def test_http_error_raises(self):
        with (
            patch("httpx.get", side_effect=httpx.ConnectError("timeout")),
            pytest.raises(CalendarError, match="Не удалось получить"),
        ):
            fetch_holidays(2025, 3)

    def test_wrong_length_raises(self):
        with patch("httpx.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.text = "0101"
            mock_resp.raise_for_status = lambda: None

            with pytest.raises(CalendarError, match="Неожиданный ответ"):
                fetch_holidays(2025, 3)
