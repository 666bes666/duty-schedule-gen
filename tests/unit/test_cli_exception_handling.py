"""Тесты каталога обработки исключений в CLI generate-range."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

from duty_schedule.calendar import CalendarError
from duty_schedule.cli import app
from duty_schedule.scheduler import ScheduleError

runner = CliRunner()


@pytest.fixture
def config_yaml(tmp_path: Path) -> Path:
    cfg = {
        "month": 3,
        "year": 2025,
        "seed": 42,
        "employees": [
            {"name": f"Москва {i}", "city": "moscow", "schedule_type": "flexible"}
            for i in range(1, 5)
        ]
        + [
            {"name": f"Хабаровск {i}", "city": "khabarovsk", "schedule_type": "flexible"}
            for i in range(1, 3)
        ],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(cfg, allow_unicode=True), encoding="utf-8")
    return path


def _make_validation_error() -> ValidationError:
    class _Probe(BaseModel):
        n: int

    try:
        _Probe(n="not-an-int")
    except ValidationError as exc:
        return exc
    raise RuntimeError("Expected ValidationError")


class TestGenerateRangeExceptionCatalog:
    def test_schedule_error_exit_code_and_message(self, config_yaml: Path, tmp_path: Path) -> None:
        with patch(
            "duty_schedule.scheduler.multimonth.generate_multimonth",
            side_effect=ScheduleError("24/7 покрытие невозможно"),
        ):
            result = runner.invoke(
                app,
                [
                    "generate-range",
                    str(config_yaml),
                    "--start",
                    "03.2025",
                    "--end",
                    "05.2025",
                    "--output-dir",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 1
        assert "ScheduleError" in result.output
        assert "24/7" in result.output

    def test_calendar_error_exit_code_and_message(self, config_yaml: Path, tmp_path: Path) -> None:
        with patch(
            "duty_schedule.scheduler.multimonth.generate_multimonth",
            side_effect=CalendarError("Источник праздников недоступен"),
        ):
            result = runner.invoke(
                app,
                [
                    "generate-range",
                    str(config_yaml),
                    "--start",
                    "03.2025",
                    "--end",
                    "05.2025",
                    "--output-dir",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 4
        assert "CalendarError" in result.output
        assert "Источник праздников" in result.output

    def test_validation_error_exit_code_and_message(
        self, config_yaml: Path, tmp_path: Path
    ) -> None:
        with patch(
            "duty_schedule.scheduler.multimonth.generate_multimonth",
            side_effect=_make_validation_error(),
        ):
            result = runner.invoke(
                app,
                [
                    "generate-range",
                    str(config_yaml),
                    "--start",
                    "03.2025",
                    "--end",
                    "05.2025",
                    "--output-dir",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 3
        assert "ValidationError" in result.output

    def test_value_error_exit_code_and_message(self, config_yaml: Path, tmp_path: Path) -> None:
        with patch(
            "duty_schedule.scheduler.multimonth.generate_multimonth",
            side_effect=ValueError("некорректный диапазон"),
        ):
            result = runner.invoke(
                app,
                [
                    "generate-range",
                    str(config_yaml),
                    "--start",
                    "03.2025",
                    "--end",
                    "05.2025",
                    "--output-dir",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 5
        assert "ValueError" in result.output
        assert "некорректный диапазон" in result.output

    def test_programming_bug_propagates(self, config_yaml: Path, tmp_path: Path) -> None:
        with patch(
            "duty_schedule.scheduler.multimonth.generate_multimonth",
            side_effect=KeyError("oops"),
        ):
            result = runner.invoke(
                app,
                [
                    "generate-range",
                    str(config_yaml),
                    "--start",
                    "03.2025",
                    "--end",
                    "05.2025",
                    "--output-dir",
                    str(tmp_path),
                ],
            )
        assert isinstance(result.exception, KeyError)
        assert "oops" in str(result.exception)
