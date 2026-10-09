from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

PLANNED = {"planned", "in-progress", "complete"}
STATUSES = {"draft", "specified", *PLANNED}
ARTIFACTS = {"spec.md", "plan.md", "tasks.md", "evidence.md", "traceability.json"}


def read_document(path: Path, errors: list[str]) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: missing or unreadable document ({exc})")
        return ""
    if not content.strip():
        errors.append(f"{path}: empty document")
    return content


def check_test(root: Path, reference: object, required: bool, errors: list[str]) -> None:
    if not isinstance(reference, str):
        errors.append(f"test reference must be a string: {reference!r}")
        return
    parts = reference.split("::")
    path = PurePosixPath(parts[0])
    if (
        path.is_absolute()
        or ".." in path.parts
        or not path.parts
        or path.parts[0] != "tests"
        or not path.name.startswith("test_")
        or path.suffix != ".py"
        or re.search(r"[\\*?\[\]]", reference)
        or any(ord(character) < 32 or ord(character) == 127 for character in reference)
    ):
        errors.append(f"invalid test reference: {reference}")
        return
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        errors.append(f"test reference escapes repository: {reference}")
        return
    if not required:
        return
    if not target.is_file():
        errors.append(f"missing test: {reference}")
        return
    if len(parts) == 1:
        return
    try:
        nodes = ast.parse(target.read_text(encoding="utf-8")).body
    except (SyntaxError, OSError, UnicodeError) as exc:
        errors.append(f"cannot inspect test {reference}: {exc}")
        return
    selected: ast.AST | None = None
    for name in parts[1:]:
        selected = next((node for node in nodes if getattr(node, "name", None) == name), None)
        if selected is None:
            errors.append(f"missing test selector: {reference}")
            return
        nodes = getattr(selected, "body", [])
    if not isinstance(selected, ast.FunctionDef | ast.AsyncFunctionDef) or not parts[-1].startswith(
        "test_"
    ):
        errors.append(f"selector is not a test function: {reference}")


def check_feature(root: Path, folder: Path, errors: list[str]) -> tuple[str, str]:
    metadata_path = folder / "traceability.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{metadata_path}: invalid or missing traceability.json ({exc})")
        return "", ""
    if not isinstance(metadata, dict):
        errors.append(f"{metadata_path}: metadata must be an object")
        return "", ""
    kind, status = metadata.get("kind"), metadata.get("status")
    if (
        not isinstance(kind, str)
        or not isinstance(status, str)
        or kind not in ("baseline", "change")
        or (kind == "baseline" and status != "recorded")
        or (kind == "change" and status not in STATUSES)
    ):
        errors.append(f"{metadata_path}: invalid kind/status")
        return "", ""
    spec = read_document(folder / "spec.md", errors)
    if kind == "change" and status in PLANNED:
        read_document(folder / "plan.md", errors)
        tasks = read_document(folder / "tasks.md", errors)
        boxes = re.findall(r"^\s*- \[([ xX])\] .+", tasks, re.MULTILINE)
        if not boxes:
            errors.append(f"{folder / 'tasks.md'}: no task checkboxes")
        if status == "complete":
            read_document(folder / "evidence.md", errors)
            if " " in boxes:
                errors.append(f"{folder / 'tasks.md'}: complete feature has unchecked tasks")
        if "NEEDS CLARIFICATION" in spec:
            errors.append(f"{folder / 'spec.md'}: unresolved clarification")
    requirements = metadata.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append(f"{metadata_path}: requirements must be a nonempty list")
        return kind, status
    seen: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            errors.append(f"{metadata_path}: requirement must be an object")
            continue
        identifier, tests = requirement.get("id"), requirement.get("tests")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Z][A-Z0-9]*-\d{3}", identifier):
            errors.append(f"{metadata_path}: invalid requirement ID {identifier!r}")
            continue
        if identifier in seen:
            errors.append(f"{metadata_path}: duplicate requirement ID {identifier}")
        seen.add(identifier)
        if not re.search(rf"(?<![\w-]){re.escape(identifier)}(?![\w-])", spec):
            errors.append(f"{folder / 'spec.md'}: missing requirement ID {identifier}")
        if not isinstance(tests, list) or not tests:
            errors.append(f"{metadata_path}: {identifier} must reference tests")
            continue
        for reference in tests:
            check_test(root, reference, kind == "baseline" or status == "complete", errors)
    return kind, status


def check_repository(root: Path, base: str | None = None) -> list[str]:
    errors: list[str] = []
    read_document(root / ".specify" / "memory" / "constitution.md", errors)
    specs = root / "specs"
    folders = sorted(path for path in specs.iterdir() if path.is_dir()) if specs.is_dir() else []
    if not folders:
        errors.append(f"{specs}: no specifications")
    states = {folder.name: check_feature(root, folder, errors) for folder in folders}
    if base:
        result = subprocess.run(
            ["git", "diff", "--no-renames", "--name-only", "-z", base, "HEAD", "--"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            errors.append(f"git diff failed: {result.stderr.strip()}")
            return errors
        changed = result.stdout.split("\0")
        runtime_changed = any(
            path.startswith("src/") or path in ("app.py", "api_main.py") for path in changed
        )
        feature_changed = any(
            len(parts := PurePosixPath(path).parts) == 3
            and parts[0] == "specs"
            and parts[2] in ARTIFACTS
            and (root / path).is_file()
            and states.get(parts[1], ("", ""))[0] == "change"
            and states[parts[1]][1] in PLANNED
            for path in changed
        )
        if runtime_changed and not feature_changed:
            errors.append("runtime changes require a planned change feature artifact in this diff")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SDD artifacts and implementation linkage"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base", help="Compare committed implementation changes from BASE to HEAD")
    arguments = parser.parse_args()
    errors = check_repository(arguments.root.resolve(), arguments.base)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("SDD checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
