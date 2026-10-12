from datetime import date
from pathlib import Path

import yaml
from typer.testing import CliRunner

from duty_schedule.cli import app
from duty_schedule.models import City, Config
from duty_schedule.project import current_schedule, load_project


def _write_config(config: Config, path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True), encoding="utf-8"
    )
    return path


def test_cli_project_reopen_exports_same_revision(planning_config: Config, tmp_path: Path) -> None:
    path = _write_config(planning_config, tmp_path / "config.yaml")
    runner = CliRunner()
    first = runner.invoke(app, ["generate", str(path), "-o", str(tmp_path / "first")])
    assert first.exit_code == 0, first.output
    project_path = tmp_path / "first" / "project_2026_04.duty.json"
    schedule = current_schedule(load_project(project_path.read_bytes()))
    assert schedule is not None and schedule.status == "ready"
    second = runner.invoke(
        app, ["export-project", str(project_path), "-o", str(tmp_path / "second")]
    )
    assert second.exit_code == 0, second.output
    assert (tmp_path / "second" / "schedule_2026_04.xlsx").exists()
    assert len(list((tmp_path / "second").glob("*.ics"))) == 4


def test_cli_diagnostic_preserves_project_and_blocks_binary_exports(
    planning_config: Config, tmp_path: Path
) -> None:
    for employee in planning_config.employees:
        if employee.city == City.KHABAROVSK:
            employee.unavailable_dates = [date(2026, 4, 1)]
    path = _write_config(planning_config, tmp_path / "config.yaml")
    runner = CliRunner()
    result = runner.invoke(app, ["generate", str(path), "-o", str(tmp_path / "output")])
    assert result.exit_code == 1
    assert "Диагностический" in result.output
    projects = list((tmp_path / "output").glob("*.duty.json"))
    assert len(projects) == 1
    assert current_schedule(load_project(projects[0].read_bytes())).status == "diagnostic"
    assert not list((tmp_path / "output").glob("*.xlsx"))
    assert not list((tmp_path / "output").glob("*.ics"))
