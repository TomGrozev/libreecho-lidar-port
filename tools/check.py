#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the published tree.

Compiles every Python file under `tools/` and parses the JSON manifests. Prints a `PASS`
or `FAIL` line per check and exits 1 when any check fails.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_FILES = ("integration.json", "tools/lab-build.json")


def check_python() -> int:
    failures = 0
    for path in sorted((ROOT / "tools").glob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, SyntaxError) as exc:
            print(f"FAIL python: {path.relative_to(ROOT)}: {exc}")
            failures += 1
    if failures == 0:
        print("PASS python: tools/*.py compile")
    return failures


def check_json() -> int:
    failures = 0
    for name in JSON_FILES:
        path = ROOT / name
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"FAIL json: {name}: {exc}")
            failures += 1
    if failures == 0:
        print("PASS json: " + ", ".join(JSON_FILES))
    return failures


def main() -> int:
    failures = check_python() + check_json()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
