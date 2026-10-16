from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path


def _baseline_file(paths: Iterable[Path], current_sha: str) -> Path | None:
    candidates: list[tuple[str, Path]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                continue
            sha = data.get("commit_info", {}).get("id")
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
                continue
            if sha == current_sha:
                continue
            benchmarks = data.get("benchmarks", [])
            if not benchmarks or not all(
                isinstance(record.get("stats", {}).get("mean"), (int, float))
                and math.isfinite(record["stats"]["mean"])
                and record["stats"]["mean"] > 0
                for record in benchmarks
            ):
                continue
            candidates.append((str(data.get("datetime", "")), path))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return max(candidates)[1] if candidates else None


def find_baseline(root: Path, current_sha: str) -> str:
    path = _baseline_file(root.rglob("*.json"), current_sha)
    return path.stem if path is not None else ""


def remeasure_baseline(root: Path, current_sha: str) -> str:
    root = root.resolve()
    prior = _baseline_file(root.rglob("*.json"), current_sha)
    if prior is None:
        return ""
    prior_sha = json.loads(prior.read_text())["commit_info"]["id"]
    repo = Path(__file__).resolve().parents[1]
    existing = set(root.rglob("*.json"))
    with tempfile.TemporaryDirectory(prefix="duty-benchmark-prior-") as folder:
        checkout = Path(folder) / "previous"
        try:
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(checkout), prior_sha],
                cwd=repo,
                check=True,
                stdout=sys.stderr,
            )
            env = os.environ.copy()
            env["UV_PROJECT_ENVIRONMENT"] = str(checkout / ".venv")
            env.pop("VIRTUAL_ENV", None)
            env.pop("PYTHONPATH", None)
            subprocess.run(
                [
                    "uv",
                    "run",
                    "--frozen",
                    "--python",
                    sys.executable,
                    "--group",
                    "ci-perf",
                    "--extra",
                    "solver",
                    "pytest",
                    "tests/performance",
                    "-q",
                    "--benchmark-only",
                    "--benchmark-storage",
                    str(root),
                    "--benchmark-save",
                    "same_runner",
                    "--benchmark-min-rounds",
                    "2",
                    "--benchmark-max-time",
                    "15",
                ],
                cwd=checkout,
                env=env,
                check=True,
                stdout=sys.stderr,
            )
            fresh = set(root.rglob("*.json")) - existing
            result = _baseline_file(fresh, current_sha)
            if len(fresh) != 1 or result is None:
                raise ValueError("Expected one fresh valid benchmark report")
            if json.loads(result.read_text())["commit_info"]["id"] != prior_sha:
                raise ValueError("Fresh benchmark report has another SHA")
            return result.stem
        finally:
            if checkout.exists():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(checkout)],
                    cwd=repo,
                    check=True,
                    stdout=sys.stderr,
                )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--current-sha", required=True)
    parser.add_argument("--remeasure", action="store_true")
    args = parser.parse_args()
    select = remeasure_baseline if args.remeasure else find_baseline
    print(select(args.root, args.current_sha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
