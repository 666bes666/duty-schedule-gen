from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

PLANNED = {"planned", "in-progress", "complete"}
STATUSES = {"draft", "specified", *PLANNED}
ARTIFACTS = {"spec.md", "plan.md", "tasks.md", "evidence.md", "traceability.json"}
SUPPLEMENTS = {
    "gaps.md",
    "decisions.md",
    "data-model.md",
    "research.md",
    "quickstart.md",
    "audit.md",
    "versions.json",
}
ID = r"[A-Z][A-Z0-9]*-\d{3}"
DEFINITION = re.compile(rf"^(?:###\s+|\s*-\s+\*\*)?({ID})(?:\*\*)?\s*(?:[:—–-])", re.M)
TASK = re.compile(r"^\s*- \[([ xX])\] (T\d{3})\b", re.M)


def read_document(path: Path, errors: list[str]) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"{path}: missing or unreadable document ({exc})")
        return ""
    if not content.strip():
        errors.append(f"{path}: empty document")
    return content


def exact_path(reference: object) -> bool:
    if not isinstance(reference, str) or not reference:
        return False
    path = PurePosixPath(reference)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == reference
        and not re.search(r"[\\*?\[\]]", reference)
        and not any(ord(character) < 32 or ord(character) == 127 for character in reference)
        and reference != "."
    )


def disabled_test_names(nodes: list[ast.stmt]) -> set[str]:
    flags: dict[str, bool] = {}
    for node in nodes:
        if isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(node.value, ast.Constant):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                name = ast.unparse(target)
                if name == "__test__":
                    flags[""] = bool(node.value.value)
                elif name.endswith(".__test__"):
                    flags[name.removesuffix(".__test__")] = bool(node.value.value)
    return {name for name, enabled in flags.items() if not enabled}


def is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        ast.unparse(decorator.func if isinstance(decorator, ast.Call) else decorator).split(".")[-1]
        in {"fixture", "yield_fixture"}
        for decorator in node.decorator_list
    )


def test_nodes(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    result: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    disabled = disabled_test_names(tree.body)
    if "" in disabled:
        return result
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}

    def has_constructor(node: ast.ClassDef, visited: frozenset[str] = frozenset()) -> bool:
        if node.name in visited:
            return True
        if any(getattr(child, "name", "") in ("__init__", "__new__") for child in node.body):
            return True
        return any(
            not isinstance(base, ast.Name)
            or base.id not in classes
            or has_constructor(classes[base.id], visited | {node.name})
            for base in node.bases
        )

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
            and node.name not in disabled
            and not is_fixture(node)
        ):
            result[node.name] = node
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            class_disabled = disabled_test_names(node.body)
            if node.name in disabled or "" in class_disabled:
                continue
            if has_constructor(node):
                continue
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
                    and child.name.startswith("test_")
                    and child.name not in class_disabled
                    and f"{node.name}.{child.name}" not in disabled
                    and not is_fixture(child)
                ):
                    result[f"{node.name}::{child.name}"] = child
    return result


def check_test(root: Path, reference: object, required: bool, errors: list[str]) -> None:
    if not isinstance(reference, str):
        errors.append(f"test reference must be a string: {reference!r}")
        return
    parts = reference.split("::")
    path = PurePosixPath(parts[0])
    if (
        not exact_path(parts[0])
        or not path.parts
        or path.parts[0] != "tests"
        or not path.name.startswith("test_")
        or path.suffix != ".py"
        or any(not re.fullmatch(r"[A-Za-z_]\w*", name) for name in parts[1:])
    ):
        errors.append(f"invalid test reference: {reference}")
        return
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        errors.append(f"test reference escapes repository: {reference}")
        return
    if not required:
        return
    try:
        nodes = test_nodes(ast.parse(target.read_text(encoding="utf-8")))
    except (SyntaxError, OSError, UnicodeError) as exc:
        errors.append(f"cannot inspect test {reference}: {exc}")
        return
    if not nodes:
        errors.append(f"no collectable tests: {reference}")
    elif len(parts) > 1 and "::".join(parts[1:]) not in nodes:
        errors.append(f"missing collectable test selector: {reference}")


def check_scope(
    root: Path, metadata: dict[str, object], folder: Path, errors: list[str]
) -> set[str]:
    files = metadata.get("files")
    if not isinstance(files, list) or not files:
        errors.append(f"{folder}: planned change requires nonempty files scope")
        return set()
    paths: set[str] = set()
    for reference in files:
        if not exact_path(reference):
            errors.append(f"{folder}: invalid files scope path {reference!r}")
        elif not (root / reference).resolve().is_relative_to(root.resolve()):
            errors.append(f"{folder}: files scope escapes repository: {reference}")
        elif reference in paths:
            errors.append(f"{folder}: duplicate files scope path {reference}")
        else:
            paths.add(reference)
    return paths


def check_feature(root: Path, folder: Path, errors: list[str]) -> tuple[str, str, set[str]]:
    metadata_path = folder / "traceability.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{metadata_path}: invalid or missing traceability.json ({exc})")
        return "", "", set()
    if not isinstance(metadata, dict):
        errors.append(f"{metadata_path}: metadata must be an object")
        return "", "", set()
    kind, status = metadata.get("kind"), metadata.get("status")
    if (
        not isinstance(kind, str)
        or not isinstance(status, str)
        or kind not in ("baseline", "change")
        or (kind == "baseline" and status != "recorded")
        or (kind == "change" and status not in STATUSES)
    ):
        errors.append(f"{metadata_path}: invalid kind/status")
        return "", "", set()
    spec = read_document(folder / "spec.md", errors)
    scope: set[str] = set()
    evidence = ""
    if kind == "change" and status in PLANNED:
        scope = check_scope(root, metadata, folder, errors)
        read_document(folder / "plan.md", errors)
        tasks = read_document(folder / "tasks.md", errors)
        boxes = re.findall(r"^\s*- \[([ xX])\] .+", tasks, re.M)
        matches = TASK.findall(tasks)
        if not boxes:
            errors.append(f"{folder / 'tasks.md'}: no task checkboxes")
        if len(matches) != len(boxes):
            errors.append(f"{folder / 'tasks.md'}: each task requires a T-ID")
        identifiers = [identifier for _, identifier in matches]
        if len(set(identifiers)) != len(identifiers):
            errors.append(f"{folder / 'tasks.md'}: duplicate task IDs")
        if status == "complete":
            evidence = read_document(folder / "evidence.md", errors)
            if " " in boxes:
                errors.append(f"{folder / 'tasks.md'}: complete feature has unchecked tasks")
        if "NEEDS CLARIFICATION" in spec:
            errors.append(f"{folder / 'spec.md'}: unresolved clarification")
    requirements = metadata.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        errors.append(f"{metadata_path}: requirements must be a nonempty list")
        return kind, status, scope
    definitions = DEFINITION.findall(spec)
    if len(set(definitions)) != len(definitions):
        errors.append(f"{folder / 'spec.md'}: duplicate requirement definitions")
    seen: set[str] = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            errors.append(f"{metadata_path}: requirement must be an object")
            continue
        identifier, tests = requirement.get("id"), requirement.get("tests")
        if not isinstance(identifier, str) or not re.fullmatch(ID, identifier):
            errors.append(f"{metadata_path}: invalid requirement ID {identifier!r}")
            continue
        if identifier in seen:
            errors.append(f"{metadata_path}: duplicate requirement ID {identifier}")
        seen.add(identifier)
        if identifier not in definitions:
            errors.append(f"{folder / 'spec.md'}: missing requirement definition {identifier}")
        if status == "complete" and not re.search(rf"(?<![\w-]){identifier}(?![\w-])", evidence):
            errors.append(f"{folder / 'evidence.md'}: missing acceptance for {identifier}")
        if not isinstance(tests, list) or not tests:
            errors.append(f"{metadata_path}: {identifier} must reference tests")
            continue
        for reference in tests:
            check_test(root, reference, kind == "baseline" or status == "complete", errors)
    for identifier in sorted(set(definitions) - seen):
        errors.append(f"{metadata_path}: unmapped specification requirement {identifier}")
    return kind, status, scope


def git_output(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError(f"git {' '.join(arguments[:2])} failed: {result.stderr.strip()}")
    return result.stdout


def changed_files(root: Path, base: str) -> list[str]:
    sha = git_output(
        root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"
    ).strip()
    changed = git_output(root, "diff", "--no-renames", "--name-only", "-z", sha, "--")
    untracked = git_output(root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(set(filter(None, (changed + untracked).split("\0"))))


def check_repository(
    root: Path, base: str | None = None, *, changes: list[str] | None = None
) -> list[str]:
    errors: list[str] = []
    read_document(root / ".specify" / "memory" / "constitution.md", errors)
    specs = root / "specs"
    folders = sorted(path for path in specs.iterdir() if path.is_dir()) if specs.is_dir() else []
    if not folders:
        errors.append(f"{specs}: no specifications")
    states: dict[str, tuple[str, str, set[str]]] = {}
    for folder in folders:
        if not folder.resolve().is_relative_to(root.resolve()):
            errors.append(f"{folder}: specification escapes repository")
            continue
        if any(not (folder / name).resolve().is_relative_to(root.resolve()) for name in ARTIFACTS):
            errors.append(f"{folder}: artifact escapes repository")
            continue
        states[folder.name] = check_feature(root, folder, errors)
    if base:
        try:
            changes = changed_files(root, base)
        except (OSError, ValueError) as exc:
            errors.append(f"git diff failed: {exc}")
            return errors
    if changes is not None:
        covered: set[str] = set()
        for path in changes:
            parts = PurePosixPath(path).parts
            if len(parts) != 3 or parts[0] != "specs" or parts[2] not in ARTIFACTS:
                continue
            kind, status, scope = states.get(parts[1], ("", "", set()))
            if kind == "change" and status in PLANNED and (root / path).is_file():
                covered.update(scope)
        for path in changes:
            parts = PurePosixPath(path).parts
            artifact = (
                len(parts) >= 3
                and parts[0] == "specs"
                and parts[1] in states
                and (
                    (len(parts) == 3 and parts[2] in ARTIFACTS | SUPPLEMENTS)
                    or (len(parts) == 4 and parts[2] == "checklists" and path.endswith(".md"))
                    or (
                        parts[2] == "contracts"
                        and PurePosixPath(path).suffix in {".json", ".yaml", ".yml"}
                    )
                )
            )
            if not artifact and path not in covered:
                errors.append(
                    f"{path}: changes require a scoped planned change feature artifact in this diff"
                )
    return errors


def check_staged(root: Path) -> list[str]:
    try:
        changes = list(
            filter(
                None,
                git_output(
                    root, "diff", "--cached", "--no-renames", "--name-only", "-z", "--"
                ).split("\0"),
            )
        )
        with tempfile.TemporaryDirectory(prefix="duty-sdd-index-") as temporary:
            git_output(root, "checkout-index", "--all", f"--prefix={temporary}/")
            return check_repository(Path(temporary), changes=changes)
    except (OSError, ValueError) as exc:
        return [f"staged SDD check failed: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SDD artifacts and exact change scope")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--base", help="Compare BASE to current worktree, including untracked files")
    scope.add_argument(
        "--staged", action="store_true", help="Validate the staged Git snapshot and diff"
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    errors = check_staged(root) if arguments.staged else check_repository(root, arguments.base)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("SDD checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
