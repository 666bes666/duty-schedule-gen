from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from duty_schedule.input_validation import migrate_legacy_config
from duty_schedule.models import Config
from tests.conftest import complete_config

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "config.example.yaml"


@pytest.fixture
def complete_config_file(tmp_path: Path) -> Path:
    config = complete_config(
        Config.model_validate(
            migrate_legacy_config(yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8")))
        )
    )
    path = tmp_path / "complete.yaml"
    path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True), encoding="utf-8"
    )
    return path


class TestCliWorkflow:
    def test_validate_example_config(self):
        result = subprocess.run(
            ["uv", "run", "duty-schedule", "validate", str(EXAMPLE_CONFIG)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "корректна" in result.stdout.lower() or "✓" in result.stdout

    def test_generate_creates_files(self, complete_config_file):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "duty-schedule",
                    "generate",
                    str(complete_config_file),
                    "--output-dir",
                    tmpdir,
                    "--format",
                    "all",
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0

            output_path = Path(tmpdir)
            xlsx_files = list(output_path.glob("*.xlsx"))
            ics_files = list(output_path.glob("*.ics"))
            assert len(xlsx_files) >= 1
            assert len(ics_files) >= 1

    def test_generate_xls_only(self, complete_config_file):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "duty-schedule",
                    "generate",
                    str(complete_config_file),
                    "--output-dir",
                    tmpdir,
                    "--format",
                    "xls",
                ],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0
            assert list(Path(tmpdir).glob("*.xlsx"))

    def test_version_command(self):
        result = subprocess.run(
            ["uv", "run", "duty-schedule", "version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "duty-schedule" in result.stdout.lower()

    def test_help_command(self):
        result = subprocess.run(
            ["uv", "run", "duty-schedule", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
