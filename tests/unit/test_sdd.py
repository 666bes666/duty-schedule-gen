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
    (feature / "evidence.md").write_text("# Evidence\n\nFR-001: Test passed.\n", encoding="utf-8")
    write_mapping(tmp_path)
    return tmp_path


def write_mapping(root: Path, **changes: object) -> None:
    mapping: dict[str, object] = {
        "kind": "change",
        "status": "complete",
        "files": ["src/feature.py"],
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


@pytest.mark.parametrize(
    "path",
    [
        "scripts/tool.py",
        "tests/unit/test_new.py",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "docs/guide.md",
        "AGENTS.md",
    ],
)
def test_all_project_changes_require_scoped_spec(sdd_repo: Path, path: str) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    target = sdd_repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("new behavior\n")
    result = run_check(sdd_repo, "--base", "HEAD")
    assert result.returncode == 1
    assert path in result.stderr
    write_mapping(sdd_repo, files=[path], status="planned")
    assert run_check(sdd_repo, "--base", "HEAD").returncode == 0


def test_unrelated_feature_cannot_cover_runtime_change(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/other.py").write_text("enabled = True\n")
    write_mapping(sdd_repo, status="planned")
    assert "src/other.py" in run_check(sdd_repo, "--base", "HEAD").stderr


def test_staged_gate_ignores_unstaged_covering_documents(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/feature.py").write_text("enabled = True\n")
    git(sdd_repo, "add", "src")
    write_mapping(sdd_repo, status="planned")
    assert run_check(sdd_repo, "--staged").returncode == 1
    git(sdd_repo, "add", "specs")
    assert run_check(sdd_repo, "--staged").returncode == 0


def test_staged_structure_is_validated_instead_of_worktree(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    (sdd_repo / "specs/001-feature/spec.md").write_text("# No requirements\n")
    git(sdd_repo, "add", "specs")
    (sdd_repo / "specs/001-feature/spec.md").write_text("FR-001: restored only outside index\n")
    assert run_check(sdd_repo, "--staged").returncode == 1


def test_unmapped_spec_requirement_is_rejected(sdd_repo: Path) -> None:
    (sdd_repo / "specs/001-feature/spec.md").write_text(
        "FR-001: observed\nFR-002: missing mapping\n"
    )
    assert "FR-002" in run_check(sdd_repo).stderr


def test_duplicate_task_ids_are_rejected(sdd_repo: Path) -> None:
    (sdd_repo / "specs/001-feature/tasks.md").write_text("- [x] T001 First\n- [x] T001 Second\n")
    assert "duplicate task" in run_check(sdd_repo).stderr


def test_complete_requires_acceptance_for_each_id(sdd_repo: Path) -> None:
    (sdd_repo / "specs/001-feature/evidence.md").write_text("# Evidence\n\nAll tests pass.\n")
    assert "FR-001" in run_check(sdd_repo).stderr


@pytest.mark.parametrize(
    "files",
    [
        [],
        ["../outside.py"],
        ["/tmp/source.py"],
        ["src/*"],
        ["src/../source.py"],
        ["src/a.py", "src/a.py"],
    ],
)
def test_scope_must_be_nonempty_exact_relative_paths(sdd_repo: Path, files: object) -> None:
    write_mapping(sdd_repo, files=files)
    assert run_check(sdd_repo).returncode == 1


@pytest.mark.parametrize(
    "content,reference",
    [
        ("", "tests/unit/test_behavior.py"),
        ("x = 1\n", "tests/unit/test_behavior.py"),
        (
            "def helper():\n    def test_hidden():\n        pass\n",
            "tests/unit/test_behavior.py::helper::test_hidden",
        ),
        (
            "class Helper:\n    def test_hidden(self):\n        pass\n",
            "tests/unit/test_behavior.py::Helper::test_hidden",
        ),
        (
            "class TestHidden:\n    def __init__(self):\n        pass\n"
            "    def test_hidden(self):\n        pass\n",
            "tests/unit/test_behavior.py::TestHidden::test_hidden",
        ),
        ("this is broken(\n", "tests/unit/test_behavior.py"),
    ],
)
def test_complete_test_references_must_be_collectable(
    sdd_repo: Path, content: str, reference: str
) -> None:
    (sdd_repo / "tests/unit/test_behavior.py").write_text(content)
    write_mapping(sdd_repo, requirements=[{"id": "FR-001", "tests": [reference]}])
    assert run_check(sdd_repo).returncode == 1


def test_collectable_class_method_is_accepted(sdd_repo: Path) -> None:
    (sdd_repo / "tests/unit/test_behavior.py").write_text(
        "class TestBehavior:\n    def test_observed(self):\n        pass\n"
    )
    write_mapping(
        sdd_repo,
        requirements=[
            {"id": "FR-001", "tests": ["tests/unit/test_behavior.py::TestBehavior::test_observed"]}
        ],
    )
    assert run_check(sdd_repo).returncode == 0


@pytest.mark.parametrize(
    "content",
    [
        "__test__ = False\ndef test_observed():\n    pass\n",
        "def test_observed():\n    pass\ntest_observed.__test__ = False\n",
        "import pytest\n@pytest.fixture\ndef test_observed():\n    pass\n",
        "__test__: bool = False\ndef test_observed():\n    pass\n",
        "class TestBehavior:\n    __test__: bool = False\n"
        "    def test_observed(self):\n        pass\n",
        "class Helper:\n    def __init__(self):\n        pass\n"
        "class TestBehavior(Helper):\n    def test_observed(self):\n        pass\n",
    ],
)
def test_disabled_tests_and_fixtures_cannot_prove_complete(sdd_repo: Path, content: str) -> None:
    (sdd_repo / "tests/unit/test_behavior.py").write_text(content)
    if "class TestBehavior" in content:
        write_mapping(
            sdd_repo,
            requirements=[
                {
                    "id": "FR-001",
                    "tests": ["tests/unit/test_behavior.py::TestBehavior::test_observed"],
                }
            ],
        )
    assert run_check(sdd_repo).returncode == 1


def test_runtime_config_inside_specs_is_not_an_artifact(sdd_repo: Path) -> None:
    git(sdd_repo, "init", "-q", "-b", "dev")
    git(sdd_repo, "add", ".")
    git(sdd_repo, "commit", "-qm", "baseline")
    (sdd_repo / "specs/001-feature/runtime-config.yaml").write_text("enabled: true\n")
    assert "runtime-config.yaml" in run_check(sdd_repo, "--base", "HEAD").stderr


def test_file_scope_rejects_external_symlink(sdd_repo: Path) -> None:
    (sdd_repo / "src").mkdir()
    (sdd_repo / "src/feature.py").symlink_to(sdd_repo.parent / "external.py")
    assert run_check(sdd_repo).returncode == 1
