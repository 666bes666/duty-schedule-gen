from __future__ import annotations

import pytest

from duty_schedule.export.ics import _sanitize_ics_value
from duty_schedule.export.xls import _sanitize_cell


class TestSanitizeCell:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("=SUM(A1:A2)", "'=SUM(A1:A2)"),
            ("+cmd|'/C calc'!A1", "'+cmd|'/C calc'!A1"),
            ("-1+1", "'-1+1"),
            ("@SUM(A1)", "'@SUM(A1)"),
            ("Иванов Иван", "Иванов Иван"),
            ("", ""),
        ],
    )
    def test_xls_formula_injection_sanitized(self, raw: str, expected: str) -> None:
        assert _sanitize_cell(raw) == expected


class TestSanitizeIcsValue:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Иванов\nИван", "Иванов Иван"),
            ("Иванов\r\nИван", "Иванов Иван"),
            ("Фамилия;Имя", "Фамилия_Имя"),
            ("Фамилия,Имя", "Фамилия_Имя"),
            ("Обычное имя", "Обычное имя"),
            ("a\n;,\r", "a __"),
        ],
    )
    def test_ics_sanitize_value(self, raw: str, expected: str) -> None:
        assert _sanitize_ics_value(raw) == expected
