from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "check_sdd.py"


@pytest.fixture
def sdd_repo(tmp_path: Path) -> Path:
    constitution = tmp_path / ".specify" / "memory" / "constitution.md"
    constitution.parent.mkdir(parents=True)
    constitution.write_text("# Project principles\n", encoding="utf-8")
    test = tmp_path / "tests" / "unit" / "test_behavior.py"
    test.parent.mkdir(parents=True)
    test.write_text("def test_observed():\n    pass\n", encoding="utf-8")
    feature = tmp_path / "specs" / "001-feature"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text("# Feature\n\nFR-001: observed behavior\n", encoding="utf-8")
    (feature / "plan.md").write_text("# Plan\n\nReuse existing boundary.\n", encoding="utf-8")
    (feature / "tasks.md").write_text("- [x] T001 Verify behavior\n", encoding="utf-8")
    (feature / "evidence.md").write_text("# Evidence\n\nTest passed.\n", encoding="utf-8")
    write_mapping(tmp_path)
    return tmp_path


def write_mapping(root: Path, **changes: object) -> None:
    mapping: dict[str, object] = {
        "kind": "change",
        "status": "complete",
        "requirements": [{"id": "FR-001", "tests": ["tests/unit/test_behavior.py::test_observed"]}],
    }
    mapping.update(changes)
    (root / "specs" / "001-feature" / "traceability.json").write_text(
        json.dumps(mapping), encoding="utf-8"
    )


def run_check(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_feature_and_real_repository_pass(sdd_repo: Path) -> None:
    assert run_check(sdd_repo).returncode == 0
    assert run_check(CHECKER.parents[1]).returncode == 0


@pytest.mark.parametrize("status", ["draft", "specified"])
def test_early_spec_does_not_require_plan_or_finished_tasks(sdd_repo: Path, status: str) -> None:
    write_mapping(sdd_repo, status=status)
    (sdd_repo / "specs/001-feature/plan.md").unlink()
    (sdd_repo / "specs/001-feature/tasks.md").unlink()
    assert run_check(sdd_repo).returncode == 0


def test_planned_test_may_not_exist_yet(sdd_repo: Path) -> None:
    write_mapping(sdd_repo, status="planned")
    (sdd_repo / "tests/unit/test_behavior.py").unlink()
    (sdd_repo / "specs/001-feature/tasks.md").write_text("- [ ] T001 Implement\n")
    assert run_check(sdd_repo).returncode == 0


@pytest.mark.parametrize("document", ["spec.md", "plan.md", "tasks.md", "evidence.md"])
def test_complete_feature_requires_documents(sdd_repo: Path, document: str) -> None:
    (sdd_repo / "specs/001-feature" / document).unlink()
    result = run_check(sdd_repo)
    assert result.returncode == 1
    assert document in result.stderr


def test_complete_feature_rejects_open_tasks(sdd_repo: Path) -> None:
    (sdd_repo / "specs/001-feature/tasks.md").write_text("- [ ] T001 Implement\n")
    assert "unchecked tasks" in run_check(sdd_repo).stderr


def test_missing_traceability_is_not_silently_skipped(sdd_repo: Path) -> None:
    (sdd_repo / "specs/001-feature/traceability.json").unlink()
    assert "traceability.json" in run_check(sdd_repo).stderr


@pytest.mark.parametrize(
    "mapping",
    ["[]", "{broken", '{"kind":"other"}', '{"kind":"change","status":"done"}'],
)
def test_invalid_mapping_is_reported_without_traceback(sdd_repo: Path, mapping: str) -> None:
    (sdd_repo / "specs/001-feature/traceability.json").write_text(mapping)
    result = run_check(sdd_repo)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_duplicate_requirement_ids_are_rejected(sdd_repo: Path) -> None:
    row = {"id": "FR-001", "tests": ["tests/unit/test_behavior.py"]}
    write_mapping(sdd_repo, requirements=[row, row])
    assert "duplicate" in run_check(sdd_repo).stderr


@pytest.mark.parametrize(
    "reference",
    [
        "../test_behavior.py",
        "/tmp/test_behavior.py",
        "tests/unit/missing.py",
        "tests/unit/test_behavior.py::test_missing",
        "tests/unit/test_*.py",
        "tests/unit/test_\u0000.py",
    ],
)
def test_bad_test_references_are_rejected(sdd_repo: Path, reference: str) -> None:
    write_mapping(sdd_repo, requirements=[{"id": "FR-001", "tests": [reference]}])
    result = run_check(sdd_repo)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_baseline_records_evidence_without_feature_tasks(sdd_repo: Path) -> None:
    write_mapping(sdd_repo, kind="baseline", status="recorded")
    (sdd_repo / "specs/001-feature/plan.md").unlink()
    (sdd_repo / "specs/001-feature/tasks.md").unlink()
    assert run_check(sdd_repo).returncode == 0


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=SDD Test", "-c", "user.email=sdd@example.invalid", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_runtime_diff_requires_nonbaseline_planned_feature(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    base = git(sdd_repo, "rev-parse", "HEAD")
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/feature.py").write_text("enabled = True\n")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "implementation only")
    assert "feature artifact" in run_check(sdd_repo, "--base", base).stderr
    write_mapping(sdd_repo, kind="baseline", status="recorded")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline update")
    assert "feature artifact" in run_check(sdd_repo, "--base", base).stderr
    write_mapping(sdd_repo, status="draft")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "draft update")
    assert "feature artifact" in run_check(sdd_repo, "--base", base).stderr
    write_mapping(sdd_repo, status="planned")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "planned feature")
    assert run_check(sdd_repo, "--base", base).returncode == 0


def test_unknown_diff_base_is_an_error(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    assert "git diff" in run_check(sdd_repo, "--base", "missing-ref").stderr


def test_moving_source_out_of_runtime_still_requires_spec(sdd_repo: Path) -> None:
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/feature.py").write_text("enabled = True\n")
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    base = git(sdd_repo, "rev-parse", "HEAD")
    (sdd_repo / "docs").mkdir()
    git(sdd_repo, "mv", "src/feature.py", "docs/feature.py")
    git(sdd_repo, "commit", "-qm", "move runtime source")
    assert "feature artifact" in run_check(sdd_repo, "--base", base).stderr


def test_deleting_optional_evidence_does_not_satisfy_runtime_gate(sdd_repo: Path) -> None:
    write_mapping(sdd_repo, status="planned")
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    base = git(sdd_repo, "rev-parse", "HEAD")
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/feature.py").write_text("enabled = True\n")
    (sdd_repo / "specs/001-feature/evidence.md").unlink()
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "implementation and deleted evidence")
    assert "feature artifact" in run_check(sdd_repo, "--base", base).stderr
