from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "examples" / "config.yaml"


class TestCliWorkflow:
    def test_validate_example_config(self):
        result = subprocess.run(
            ["uv", "run", "duty-schedule", "validate", str(EXAMPLE_CONFIG)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "корректна" in result.stdout.lower() or "✓" in result.stdout

    def test_generate_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "duty-schedule",
                    "generate",
                    str(EXAMPLE_CONFIG),
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

    def test_generate_xls_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "duty-schedule",
                    "generate",
                    str(EXAMPLE_CONFIG),
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
