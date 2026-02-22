"""Тесты загрузки производственного календаря."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest

from duty_schedule.calendar import (
    CalendarError,
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
        result = parse_manual_holidays("2025-03-08,2025-03-09", 2025, 3)
        assert date(2025, 3, 8) in result
        assert date(2025, 3, 9) in result
        assert len(result) == 2

    def test_empty_string(self):
        result = parse_manual_holidays("", 2025, 3)
        assert result == set()

    def test_invalid_format_raises(self):
        with pytest.raises(CalendarError, match="Неверный формат"):
            parse_manual_holidays("08.03.2025", 2025, 3)

    def test_wrong_month_skipped(self):
        result = parse_manual_holidays("2025-04-01,2025-03-08", 2025, 3)
        assert date(2025, 3, 8) in result
        assert date(2025, 4, 1) not in result


class TestFetchHolidays:
    def test_success(self):
        # Март 2025: 31 день, ответ API — строка из 31 символа
        # Помечаем 8-е (0-based индекс 7) как праздник (код "1")
        mock_data = "0000000100000000000000000000000"  # 8 марта = праздник
        assert len(mock_data) == 31

        with patch("httpx.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.text = mock_data
            mock_resp.raise_for_status = lambda: None

            result = fetch_holidays(2025, 3)

        assert date(2025, 3, 8) in result

    def test_http_error_raises(self):
        with (
            patch("httpx.get", side_effect=httpx.ConnectError("timeout")),
            pytest.raises(CalendarError, match="Не удалось получить"),
        ):
            fetch_holidays(2025, 3)

    def test_wrong_length_raises(self):
        with patch("httpx.get") as mock_get:
            mock_resp = mock_get.return_value
            mock_resp.text = "0101"  # неверная длина
            mock_resp.raise_for_status = lambda: None

            with pytest.raises(CalendarError, match="Неожиданный ответ"):
                fetch_holidays(2025, 3)
