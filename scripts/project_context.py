from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

INDEX_JSON = "docs/project-index.json"
INDEX_MD = "docs/project-index.md"


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ValueError(f"git {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout


def role(path: str) -> str:
    categories = (
        ("specs/", "sdd_contract"),
        (".specify/", "sdd_toolkit"),
        (".agents/", "codex_instructions"),
        (".claude/", "claude_instructions"),
        (".github/", "delivery"),
        ("tests/", "tests"),
        ("scripts/", "tooling"),
        ("docs/", "documentation"),
        ("src/duty_schedule/api/", "api"),
        ("src/duty_schedule/ui/", "ui"),
        ("src/duty_schedule/export/", "export"),
        ("src/duty_schedule/scheduler/", "scheduler"),
        ("src/duty_schedule/", "domain"),
    )
    return next((category for prefix, category in categories if path.startswith(prefix)), "project")


def python_structure(path: Path) -> tuple[list[str], list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols: list[str] = []

    def collect(nodes: list[ast.stmt], prefix: str = "") -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                name = f"{prefix}{node.name}"
                symbols.append(name)
                collect(node.body, f"{name}.")
            else:
                collect(
                    [child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt)],
                    prefix,
                )

    collect(tree.body)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add("." * node.level + (node.module or ""))
    return sorted(symbols), sorted(imports)


def repository_paths(root: Path) -> list[str]:
    output = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    names = set(filter(None, output.split("\0")))
    if ".specify/feature.json" in names:
        raise ValueError("local .specify/feature.json must remain ignored and untracked")
    result = {INDEX_JSON, INDEX_MD}
    for name in names:
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"indexed path escapes repository: {name}")
        if path.is_file():
            result.add(name)
    return sorted(result)


def build_index(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for name in repository_paths(root):
        entry: dict[str, Any] = {"path": name, "role": role(name)}
        if name.endswith(".py"):
            entry["symbols"], entry["imports"] = python_structure(root / name)
        files.append(entry)
    paths = {entry["path"] for entry in files}
    specifications: list[dict[str, Any]] = []
    for entry in files:
        parts = Path(entry["path"]).parts
        if len(parts) != 3 or parts[0] != "specs" or parts[2] != "traceability.json":
            continue
        path = root / entry["path"]
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("requirements"), list):
            raise ValueError(f"invalid traceability: {path.relative_to(root)}")
        specifications.append(
            {
                "path": path.parent.relative_to(root).as_posix(),
                "kind": data.get("kind"),
                "status": data.get("status"),
                "requirements": data["requirements"],
                "files": data.get("files", []),
            }
        )
    contract = root / "specs/000-baseline/contracts/openapi.json"
    operations: list[dict[str, str]] = []
    if "specs/000-baseline/contracts/openapi.json" in paths:
        schema = json.loads(contract.read_text(encoding="utf-8"))
        for path, methods in sorted(schema["paths"].items()):
            for method, operation in sorted(methods.items()):
                if method in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}:
                    operations.append(
                        {
                            "method": method.upper(),
                            "path": path,
                            "operation_id": operation.get("operationId", ""),
                        }
                    )
    with (root / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    return {
        "schema_version": 1,
        "version": project["version"],
        "entrypoints": [
            path
            for path in (
                "app.py",
                "api_main.py",
                "src/duty_schedule/cli.py",
                "src/duty_schedule/api/__init__.py",
            )
            if path in paths
        ],
        "files": files,
        "specifications": specifications,
        "api_operations": operations,
    }


def render_markdown(index: dict[str, Any]) -> str:
    files = index["files"]
    lines = [
        "# Индекс проекта",
        "",
        "Генерируется `uv run python scripts/project_context.py --write`; "
        "ручные изменения запрещены.",
        f"Версия приложения: {index['version']}. Файлов: {len(files)}. "
        "Полные symbols/imports/traceability: [JSON](project-index.json).",
        "",
        "Холодный старт: [руководство](cold-start.md). Правила: [AGENTS](../AGENTS.md), "
        "[SDD](sdd.md), [конституция](../.specify/memory/constitution.md).",
        "",
        "## Карта областей",
        "",
        "| Область | Файлов |",
        "|---|---:|",
    ]
    counts = Counter(entry["role"] for entry in files)
    lines.extend(f"| {name} | {count} |" for name, count in sorted(counts.items()))
    lines.extend(
        [
            "",
            "## Спецификации и требования",
            "",
            "| Спецификация | Статус | Требования |",
            "|---|---|---|",
        ]
    )
    for spec in index["specifications"]:
        ids = ", ".join(item["id"] for item in spec["requirements"])
        lines.append(f"| [{spec['path']}](../{spec['path']}/spec.md) | {spec['status']} | {ids} |")
    lines.extend(["", "## API операции", "", "| Метод | Путь | Operation ID |", "|---|---|---|"])
    for operation in index["api_operations"]:
        lines.append(
            f"| {operation['method']} | `{operation['path']}` | {operation['operation_id']} |"
        )
    lines.extend(["", "## Все файлы", "", "| Путь | Область |", "|---|---|"])
    for entry in files:
        name = entry["path"]
        lines.append(f"| [{name}](../{quote(name, safe='/')}) | {entry['role']} |")
    return "\n".join(lines) + "\n"


def index_contents(root: Path) -> dict[str, str]:
    index = build_index(root)
    return {
        INDEX_JSON: json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        INDEX_MD: render_markdown(index),
    }


def check_index(root: Path) -> list[str]:
    errors: list[str] = []
    for name, expected in index_contents(root).items():
        target = root / name
        if not target.is_file() or target.read_text(encoding="utf-8") != expected:
            errors.append(f"{name}: missing or stale; run scripts/project_context.py --write")
    return errors


def context(root: Path, feature: str | None) -> str:
    if feature and not re.fullmatch(r"\d{3}-[a-z0-9][a-z0-9-]*", feature):
        raise ValueError("feature must be an exact specs directory name")
    index = build_index(root)
    if feature and not any(spec["path"] == f"specs/{feature}" for spec in index["specifications"]):
        raise ValueError(f"unknown feature: {feature}")
    branch = git(root, "branch", "--show-current").strip() or "detached"
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    sha = head.stdout.strip() if head.returncode == 0 else "unborn"
    status = git(root, "status", "--short", "--branch")
    lines = [
        f"Repository: {root}",
        f"Git: {branch} @ {sha}; application {index['version']}",
        status,
        "Read: AGENTS.md → .specify/memory/constitution.md → docs/sdd.md → "
        "docs/project-index.md → selected spec/plan/tasks/traceability/evidence.",
        "Ordinary implementation is allowed only in dev and only after SDD planning.",
    ]
    for spec in index["specifications"]:
        tasks = root / spec["path"] / "tasks.md"
        opened = (
            len(re.findall(r"^\s*- \[ \]", tasks.read_text(encoding="utf-8"), re.M))
            if tasks.is_file()
            else 0
        )
        lines.append(
            f"{spec['path']}: {spec['status']}; "
            f"requirements={len(spec['requirements'])}; open_tasks={opened}"
        )
    if feature:
        lines.append(
            f"export SPECIFY_FEATURE_DIRECTORY={shlex.quote(str(root / 'specs' / feature))}"
        )
        lines.append("export SPECIFY_FEATURE_NO_PERSIST=1")
    lines.extend(
        [
            "Validate: uv run python scripts/check_sdd.py --base HEAD; "
            "uv run python scripts/project_context.py --check",
            "Before commit: uv run python scripts/check_sdd.py --staged",
            "Delivery: commit dev → push → green CI → GitHub PR dev→test→main; "
            "approvals and required checks remain mandatory.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic repository index and live cold-start context"
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--feature", help="Exact specification directory name")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write", action="store_true", help="Regenerate committed indexes")
    action.add_argument("--check", action="store_true", help="Reject missing or stale indexes")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    try:
        if arguments.write:
            for name, content in index_contents(root).items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            print("Project index written")
        elif arguments.check:
            errors = check_index(root)
            if errors:
                raise ValueError("\n".join(errors))
            print("Project index checks passed")
        else:
            print(context(root, arguments.feature), end="")
    except (OSError, ValueError, SyntaxError, KeyError, TypeError) as exc:
        print(f"Project context failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
