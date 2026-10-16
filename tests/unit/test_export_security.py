from __future__ import annotations

import pytest

from duty_schedule.export.ics import _sanitize_ics_value
from duty_schedule.export.xls import _sanitize_cell


def test_pdf_names_are_escaped_in_both_tables(minimal_config) -> None:
    from duty_schedule.export.pdf import _build_schedule_html
    from duty_schedule.models import Schedule
    from duty_schedule.stats import compute_stats

    raw_name = 'Audit<img src="https://audit.invalid/marker.png"> & <tag>'
    minimal_config.employees[0].name = raw_name
    schedule = Schedule(config=minimal_config, days=[])
    stats = compute_stats(schedule, {}, 21)
    html = _build_schedule_html(schedule, {}, minimal_config.employees, stats)

    assert '<img src="https://audit.invalid/marker.png">' not in html
    assert html.count("Audit&lt;img src=&quot;https://audit.invalid/marker.png&quot;&gt;") == 2
    assert "&amp; &lt;tag&gt;" in html


@pytest.mark.parametrize(
    "url",
    [
        "https://audit.invalid/marker.png",
        "http://127.0.0.1/marker.png",
        "file:///private/marker.txt",
        "data:image/svg+xml,<svg></svg>",
    ],
)
def test_pdf_fetcher_blocks_resources_before_opening(url: str, monkeypatch) -> None:
    from unittest.mock import Mock

    from duty_schedule.export.pdf import _safe_url_fetcher

    opened = Mock(side_effect=AssertionError("A blocked URL reached the IO layer"))
    monkeypatch.setattr("urllib.request.OpenerDirector.open", opened)
    try:
        fetcher = _safe_url_fetcher()
    except OSError:
        pytest.skip("Native PDF libraries are unavailable")

    with pytest.raises(ValueError, match="disallowed protocol"):
        fetcher.fetch(url)
    opened.assert_not_called()


def test_archive_names_are_safe_unique_and_preserve_original_inputs() -> None:
    import ntpath
    import posixpath

    from duty_schedule.export.filenames import safe_filenames

    names = ["../Alice", "..\\Alice", "ALICE", "Alice", "CON", "..", "\r\n", "Иван Иван"]
    original = list(names)
    filenames = safe_filenames(names, ".ics")

    assert names == original
    assert len(filenames) == len(names)
    assert len({name.casefold() for name in filenames}) == len(names)
    for filename in filenames:
        assert filename == posixpath.basename(filename) == ntpath.basename(filename)
        assert not any(ord(char) < 32 for char in filename)
        assert filename.endswith(".ics")
        assert filename.split(".")[0].upper() != "CON"
    assert filenames[-1] == "Иван Иван.ics"


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
            (" =SUM(A1)", "' =SUM(A1)"),
            ("\t+cmd", "'\t+cmd"),
            ("  @data", "'  @data"),
            ("  -1", "'  -1"),
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
            ("user@domain", "user_domain"),
            ("test@test.com;a,b", "test_test.com_a_b"),
        ],
    )
    def test_ics_sanitize_value(self, raw: str, expected: str) -> None:
        assert _sanitize_ics_value(raw) == expected
