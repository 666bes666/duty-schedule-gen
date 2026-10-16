from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/project_context.py"


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


@pytest.fixture
def indexed_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "dev")
    (tmp_path / ".gitignore").write_text(".env\n.venv/\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="5.0.0"\n')
    source = tmp_path / "src/duty_schedule/example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "import json\nclass Planner:\n    def plan(self):\n        return json.dumps({})\n"
    )
    spec = tmp_path / "specs/001-feature"
    spec.mkdir(parents=True)
    (spec / "traceability.json").write_text(
        json.dumps(
            {
                "kind": "change",
                "status": "planned",
                "files": ["src/duty_schedule/example.py"],
                "requirements": [
                    {"id": "FR-001", "tests": ["tests/unit/test_example.py::test_plan"]}
                ],
            }
        )
    )
    contract = tmp_path / "specs/000-baseline/contracts/openapi.json"
    contract.parent.mkdir(parents=True)
    contract.write_text(json.dumps({"paths": {"/api/v1/plan": {"post": {"operationId": "plan"}}}}))
    (tmp_path / ".env").write_text("do_not_read=this_file")
    git(tmp_path, "add", ".")
    return tmp_path


def run(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *arguments],
        text=True,
        capture_output=True,
    )


def test_index_is_complete_deterministic_and_contains_contracts(indexed_repo: Path) -> None:
    assert run(indexed_repo, "--write").returncode == 0
    path = indexed_repo / "docs/project-index.json"
    original = path.read_bytes()
    data = json.loads(original)
    files = {entry["path"]: entry for entry in data["files"]}
    assert ".env" not in files
    assert "docs/project-index.json" in files
    assert "docs/project-index.md" in files
    assert files["src/duty_schedule/example.py"]["symbols"] == ["Planner", "Planner.plan"]
    assert files["src/duty_schedule/example.py"]["imports"] == ["json"]
    assert data["specifications"][0]["requirements"][0]["id"] == "FR-001"
    assert data["api_operations"][0]["path"] == "/api/v1/plan"
    assert run(indexed_repo, "--write").returncode == 0
    assert path.read_bytes() == original
    assert run(indexed_repo, "--check").returncode == 0


def test_index_check_detects_new_untracked_file_and_symbol_drift(indexed_repo: Path) -> None:
    assert run(indexed_repo, "--write").returncode == 0
    (indexed_repo / "README.md").write_text("# New entry\n")
    result = run(indexed_repo, "--check")
    assert result.returncode == 1
    assert "stale" in result.stderr
    assert run(indexed_repo, "--write").returncode == 0
    (indexed_repo / "src/duty_schedule/example.py").write_text("def new_symbol():\n    pass\n")
    assert run(indexed_repo, "--check").returncode == 1


def test_deleted_tracked_file_disappears_from_inventory(indexed_repo: Path) -> None:
    (indexed_repo / "src/duty_schedule/example.py").unlink()
    assert run(indexed_repo, "--write").returncode == 0
    data = json.loads((indexed_repo / "docs/project-index.json").read_text())
    assert "src/duty_schedule/example.py" not in {entry["path"] for entry in data["files"]}


def test_context_reports_live_branch_and_explicit_feature_without_pointer(
    indexed_repo: Path,
) -> None:
    result = run(indexed_repo, "--feature", "001-feature")
    assert result.returncode == 0
    assert "dev" in result.stdout and "planned" in result.stdout
    assert "SPECIFY_FEATURE_DIRECTORY" in result.stdout
    assert "SPECIFY_FEATURE_NO_PERSIST=1" in result.stdout
    assert not (indexed_repo / ".specify/feature.json").exists()
    assert run(indexed_repo, "--feature", "../../escape").returncode == 1


def test_index_rejects_invalid_python_and_external_symlink(
    indexed_repo: Path, tmp_path: Path
) -> None:
    source = indexed_repo / "src/duty_schedule/example.py"
    source.write_text("broken(\n")
    assert run(indexed_repo, "--write").returncode == 1
    source.unlink()
    source.symlink_to(tmp_path.parent / "outside.py")
    assert run(indexed_repo, "--write").returncode == 1


def test_context_fails_closed_on_malformed_metadata(indexed_repo: Path) -> None:
    (indexed_repo / "specs/001-feature/traceability.json").write_text("[]")
    result = run(indexed_repo)
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_ignored_spec_metadata_is_not_read_or_copied_to_index(indexed_repo: Path) -> None:
    with (indexed_repo / ".gitignore").open("a") as file:
        file.write("specs/999-local/\n")
    folder = indexed_repo / "specs/999-local"
    folder.mkdir()
    (folder / "traceability.json").write_text("invalid local data")
    assert run(indexed_repo, "--write").returncode == 0
    data = json.loads((indexed_repo / "docs/project-index.json").read_text())
    assert "specs/999-local" not in {spec["path"] for spec in data["specifications"]}


def test_inventory_preserves_leading_space_in_file_names(indexed_repo: Path) -> None:
    (indexed_repo / " leading-file.md").write_text("# Valid file\n")
    assert run(indexed_repo, "--write").returncode == 0
    data = json.loads((indexed_repo / "docs/project-index.json").read_text())
    assert " leading-file.md" in {entry["path"] for entry in data["files"]}


def test_ignored_openapi_is_not_read_or_indexed(indexed_repo: Path) -> None:
    contract = "specs/000-baseline/contracts/openapi.json"
    git(indexed_repo, "rm", "--cached", contract)
    with (indexed_repo / ".gitignore").open("a") as file:
        file.write(contract + "\n")
    (indexed_repo / contract).write_text("invalid private schema")
    assert run(indexed_repo, "--write").returncode == 0
    data = json.loads((indexed_repo / "docs/project-index.json").read_text())
    assert data["api_operations"] == []


def test_index_includes_nested_and_conditional_definitions(indexed_repo: Path) -> None:
    (indexed_repo / "src/duty_schedule/example.py").write_text(
        "def plan():\n    def select():\n        pass\n    if True:\n"
        "        def rank():\n            pass\n"
    )
    assert run(indexed_repo, "--write").returncode == 0
    data = json.loads((indexed_repo / "docs/project-index.json").read_text())
    file = next(entry for entry in data["files"] if entry["path"].endswith("example.py"))
    assert file["symbols"] == ["plan", "plan.rank", "plan.select"]
