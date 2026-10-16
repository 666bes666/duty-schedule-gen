from __future__ import annotations

import io
import json
import tarfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHA = "a" * 40


def test_packaged_smoke_payload_matches_public_model() -> None:
    from scripts.artifact_smoke import smoke_payload

    from duty_schedule.models import Config

    config = Config.model_validate(smoke_payload())
    assert config.production_calendar is not None and config.production_calendar.verified
    expected = date(config.year, config.month, 1) - timedelta(days=1)
    assert {carry.as_of for carry in config.carry_over} == {expected}
    assert {carry.employee_name for carry in config.carry_over} == {
        employee.name for employee in config.employees
    }


@pytest.mark.asyncio
async def test_packaged_smoke_payload_generates_ready() -> None:
    pytest.importorskip("ortools.sat.python.cp_model")
    from httpx import ASGITransport, AsyncClient
    from scripts.artifact_smoke import smoke_payload

    from duty_schedule.api import create_app
    from duty_schedule.api.settings import ApiSettings, get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: ApiSettings(auth_enabled=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/schedule/generate", json=smoke_payload())
    assert response.status_code == 200, response.text
    schedule = response.json()
    assert schedule["status"] == "ready"
    assert len(schedule["days"]) == 28
    assert not schedule["diagnostics"]


@pytest.mark.parametrize(
    "xml",
    [
        '<testsuite tests="0"/>',
        '<testsuite><testcase name="solver"><skipped/></testcase></testsuite>',
        '<testsuite><testcase name="solver"><failure/></testcase></testsuite>',
    ],
)
def test_required_test_report_rejects_missing_or_unexecuted_tests(tmp_path: Path, xml: str) -> None:
    from scripts.check_junit import verify_junit

    report = tmp_path / "report.xml"
    report.write_text(xml)
    with pytest.raises(ValueError):
        verify_junit(report)


def test_required_test_report_accepts_executed_solver_tests(tmp_path: Path) -> None:
    from scripts.check_junit import verify_junit

    report = tmp_path / "report.xml"
    report.write_text(
        '<testsuites><testsuite><testcase name="coverage"/>'
        '<testcase name="norm"/></testsuite></testsuites>'
    )
    assert verify_junit(report) == 2


def test_previous_sha_benchmark_is_selected_without_exact_cache_hit(tmp_path: Path) -> None:
    from scripts.benchmark_baseline import find_baseline

    folder = tmp_path / "Linux"
    folder.mkdir()
    (folder / "0001_baseline.json").write_text(
        json.dumps(
            {
                "datetime": "2026-10-09T12:00:00",
                "commit_info": {"id": "b" * 40},
                "benchmarks": [{"name": "generation", "stats": {"mean": 1.0}}],
            }
        )
    )
    (folder / "0002_baseline.json").write_text(
        json.dumps(
            {
                "datetime": "2026-10-10T12:00:00",
                "commit_info": {"id": SOURCE_SHA},
                "benchmarks": [{"name": "generation", "stats": {"mean": 1.0}}],
            }
        )
    )
    assert find_baseline(tmp_path, SOURCE_SHA) == "0001_baseline"


def _distribution(folder: Path, version: str = "4.1.0") -> None:
    with zipfile.ZipFile(folder / f"duty_schedule-{version}-py3-none-any.whl", "w") as archive:
        archive.writestr(
            f"duty_schedule-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: duty-schedule\nVersion: {version}\n",
        )
    content = f"Metadata-Version: 2.1\nName: duty-schedule\nVersion: {version}\n".encode()
    with tarfile.open(folder / f"duty_schedule-{version}.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo(f"duty_schedule-{version}/PKG-INFO")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))


def test_release_verifies_same_sha_version_and_bytes(tmp_path: Path) -> None:
    from scripts.artifact_manifest import build_manifest, verify_manifest

    _distribution(tmp_path)
    build_manifest(tmp_path, SOURCE_SHA, "4.1.0")
    files = verify_manifest(tmp_path, SOURCE_SHA, "4.1.0")
    assert {file.suffix for file in files} == {".whl", ".gz"}
    with pytest.raises(ValueError, match="SHA"):
        verify_manifest(tmp_path, "b" * 40, "4.1.0")
    files[0].write_bytes(files[0].read_bytes() + b"changed")
    with pytest.raises(ValueError, match="checksum"):
        verify_manifest(tmp_path, SOURCE_SHA, "4.1.0")


def test_release_rejects_wrong_distribution_version(tmp_path: Path) -> None:
    from scripts.artifact_manifest import build_manifest

    _distribution(tmp_path, "4.0.0")
    with pytest.raises(ValueError, match="version"):
        build_manifest(tmp_path, SOURCE_SHA, "4.1.0")


def test_release_rejects_existing_tag_for_other_sha() -> None:
    from scripts.artifact_manifest import verify_tag

    verify_tag(None, SOURCE_SHA)
    verify_tag(SOURCE_SHA, SOURCE_SHA)
    with pytest.raises(ValueError, match="tag"):
        verify_tag("b" * 40, SOURCE_SHA)


def test_release_graph_requires_all_verified_artifact_gates() -> None:
    main = yaml.load((ROOT / ".github/workflows/ci-main.yml").read_text(), Loader=yaml.BaseLoader)
    jobs = main["jobs"]
    assert "solver-tests" in jobs
    assert "packaged-runtime" in jobs
    assert "release" in jobs
    assert "github.event_name == 'push'" in jobs["release"]["if"]
    assert "refs/heads/main" in jobs["release"]["if"]

    def dependencies(name: str) -> set[str]:
        direct = jobs[name].get("needs", [])
        if isinstance(direct, str):
            direct = [direct]
        return set(direct) | {parent for child in direct for parent in dependencies(child)}

    assert {
        "lint",
        "test-all",
        "security",
        "solver-tests",
        "ui-tests",
        "build",
        "packaged-runtime",
        "performance",
        "promote-benchmark",
    } <= dependencies("release")
    release = yaml.load(
        (ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader
    )
    assert "workflow_call" in release["on"]
    assert "push" not in release["on"]


def test_main_release_compares_previous_success_and_promotes_after_all_gates() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/ci-main.yml").read_text(), Loader=yaml.BaseLoader
    )
    jobs = workflow["jobs"]
    benchmark_steps = jobs["performance"]["steps"]
    restored = next(step for step in benchmark_steps if step.get("id") == "bench-cache")
    assert restored["uses"] == "actions/cache/restore@v4"
    assert restored["with"]["restore-keys"]
    comparison = next(
        step for step in benchmark_steps if "benchmark-compare-fail" in step.get("run", "")
    )
    assert "--current-sha" in comparison["run"]
    assert "--benchmark-compare-fail=mean:10%" in comparison["run"]
    assert comparison["env"]["DUTY_MATCHED_KEY"] == (
        "${{ steps.bench-cache.outputs.cache-matched-key }}"
    )
    assert "performance" in jobs["build"]["needs"]
    promotion = jobs["promote-benchmark"]
    assert {"build", "packaged-runtime"} <= set(promotion["needs"])
    assert "github.event_name == 'push'" in promotion["if"]
    assert "refs/heads/main" in promotion["if"]
    assert "promote-benchmark" in jobs["tag"]["needs"]
    linkage = next(step for step in jobs["lint"]["steps"] if "check_sdd.py" in step.get("run", ""))
    assert linkage["env"]["DUTY_SDD_BASE"] == (
        "${{ github.event.pull_request.base.sha || github.event.before }}"
    )
    assert '--base "$DUTY_SDD_BASE"' in linkage["run"]
    assert any(
        "project_context.py --check" in step.get("run", "") for step in jobs["lint"]["steps"]
    )


def test_sdd_gate_covers_all_branches_index_and_staged_snapshot() -> None:
    workflow = yaml.load((ROOT / ".github/workflows/sdd.yml").read_text(), Loader=yaml.BaseLoader)
    for event in ("push", "pull_request"):
        assert set(workflow["on"][event]["branches"]) == {"dev", "test", "main"}
    steps = workflow["jobs"]["sdd"]["steps"]
    assert any("check_sdd.py --base" in step.get("run", "") for step in steps)
    assert any("project_context.py --check" in step.get("run", "") for step in steps)
    assert any("test_project_context.py" in step.get("run", "") for step in steps)
    hooks = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(hook for repo in hooks["repos"] for hook in repo["hooks"] if hook["id"] == "sdd")
    assert hook["entry"] == "uv run python scripts/check_sdd.py --staged"
    assert hook["always_run"] and not hook["pass_filenames"]


def test_macos_native_pdf_precedes_full_regression() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/ci-main.yml").read_text(), Loader=yaml.BaseLoader
    )
    steps = workflow["jobs"]["test-all"]["steps"]
    native = next(step for step in steps if step.get("id") == "macos_pdf")
    regression = next(step for step in steps if "uv run pytest" in step.get("run", ""))
    assert steps.index(native) < steps.index(regression)
    assert native["if"] == "runner.os == 'macOS'"
    assert native["shell"] == regression["shell"] == "bash"
    assert "brew install pango" in native["run"]
    assert "$(brew --prefix)/lib" in native["run"]
    assert "DUTY_NATIVE_LIBRARY_PATH" in native["run"]
    assert "GITHUB_ENV" in native["run"]
    assert "from weasyprint import HTML" in native["run"]
    assert ".write_pdf()" in native["run"] and 'b"%PDF"' in native["run"]
    assert '"$RUNNER_OS" = "macOS"' in regression["run"]
    assert 'DYLD_FALLBACK_LIBRARY_PATH="$DUTY_NATIVE_LIBRARY_PATH"' in regression["run"]
    assert regression["run"].index("DYLD_FALLBACK_LIBRARY_PATH") < regression["run"].index(
        "uv run pytest"
    )
    assert "--cov-fail-under=80" in regression["run"]
    assert set(workflow["jobs"]["test-all"]["strategy"]["matrix"]["os"]) == {
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    }
