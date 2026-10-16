from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree


def verify_junit(path: Path) -> int:
    root = ElementTree.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("Required test suite did not execute any tests")
    for case in cases:
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise ValueError(f"Required test did not pass: {case.get('name', 'unknown')}")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        count = verify_junit(args.report)
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"Verified {count} executed tests without skips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
