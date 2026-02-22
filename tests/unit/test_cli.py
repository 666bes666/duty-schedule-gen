"""Тесты CLI-команд."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from duty_schedule.cli import app

runner = CliRunner()


@pytest.fixture
def config_yaml(tmp_path: Path) -> Path:
    """Минимальная валидная конфигурация в YAML-файле."""
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


class TestVersionCommand:
    def test_version_output(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "duty-schedule" in result.output


class TestValidateCommand:
    def test_valid_config(self, config_yaml):
        result = runner.invoke(app, ["validate", str(config_yaml)])
        assert result.exit_code == 0
        assert "корректна" in result.output

    def test_missing_file(self, tmp_path):
        result = runner.invoke(app, ["validate", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code != 0

    def test_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : invalid yaml :::", encoding="utf-8")
        result = runner.invoke(app, ["validate", str(bad)])
        assert result.exit_code != 0

    def test_invalid_config_missing_employees(self, tmp_path):
        cfg_path = tmp_path / "cfg.yaml"
        cfg_path.write_text(
            yaml.dump({"month": 3, "year": 2025, "employees": []}),
            encoding="utf-8",
        )
        result = runner.invoke(app, ["validate", str(cfg_path)])
        assert result.exit_code != 0


class TestGenerateCommand:
    def test_generate_xls(self, config_yaml, tmp_path):
        result = runner.invoke(
            app,
            ["generate", str(config_yaml), "--output-dir", str(tmp_path), "--format", "xls"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        xlsx_files = list(tmp_path.glob("*.xlsx"))
        assert len(xlsx_files) == 1

    def test_generate_ics(self, config_yaml, tmp_path):
        result = runner.invoke(
            app,
            ["generate", str(config_yaml), "--output-dir", str(tmp_path), "--format", "ics"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        ics_files = list(tmp_path.glob("*.ics"))
        assert len(ics_files) == 4

    def test_generate_all(self, config_yaml, tmp_path):
        result = runner.invoke(
            app,
            ["generate", str(config_yaml), "--output-dir", str(tmp_path), "--format", "all"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert list(tmp_path.glob("*.xlsx"))
        assert list(tmp_path.glob("*.ics"))

    def test_generate_unknown_format(self, config_yaml, tmp_path):
        result = runner.invoke(
            app,
            ["generate", str(config_yaml), "--output-dir", str(tmp_path), "--format", "pdf"],
        )
        assert result.exit_code == 0
        assert "неизвестный формат" in result.output

    def test_generate_verbose(self, config_yaml, tmp_path):
        result = runner.invoke(
            app,
            ["generate", str(config_yaml), "--output-dir", str(tmp_path), "--verbose"],
        )
        assert result.exit_code == 0

    def test_generate_missing_config(self, tmp_path):
        result = runner.invoke(
            app, ["generate", str(tmp_path / "nope.yaml"), "--output-dir", str(tmp_path)]
        )
        assert result.exit_code != 0
