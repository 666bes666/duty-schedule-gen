from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def find_baseline(root: Path, current_sha: str) -> str:
    candidates: list[tuple[str, str]] = []
    for path in root.rglob("*.json"):
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or data.get("commit_info", {}).get("id") == current_sha:
                continue
            benchmarks = data.get("benchmarks", [])
            if not benchmarks or not all(
                isinstance(record.get("stats", {}).get("mean"), (int, float))
                and math.isfinite(record["stats"]["mean"])
                and record["stats"]["mean"] > 0
                for record in benchmarks
            ):
                continue
            candidates.append((str(data.get("datetime", "")), path.stem))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return max(candidates)[1] if candidates else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--current-sha", required=True)
    args = parser.parse_args()
    print(find_baseline(args.root, args.current_sha))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
