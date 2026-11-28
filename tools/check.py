#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check the published tree.

Compiles every Python file under `tools/`, parses every published JSON file,
checks that relative Markdown links resolve, checks that the manifest's repos
are named in the integration doc, and runs the `tools/test_*.py` tests. Prints
a `PASS` or `FAIL` line per check and exits 1 when any check fails.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"lab-notes", "work", "private"}
DOC_FORKS = Path("docs/agents/integration-and-builds.md")
LINK_RE = re.compile(r"""(?<!!)\[[^\]]*\]\(\s*([^)\s]+)(?:\s+["'][^"']*["'])?\s*\)""")
SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def published_files(root, pattern):
    """Files matching `pattern` outside the generated and private trees."""
    for path in sorted(root.rglob(pattern)):
        if not path.is_file():
            continue
        parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in parts):
            continue
        if any(part.startswith(".") for part in parts):
            continue
        yield path


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


def check_json(root=ROOT) -> int:
    failures = 0
    paths = list(published_files(root, "*.json"))
    for path in paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"FAIL json: {path.relative_to(root)}: {exc}")
            failures += 1
    if failures == 0:
        print(f"PASS json: {len(paths)} published file(s) parse")
    return failures


def markdown_links(text):
    """Yield (line number, target) for inline links outside fenced code blocks."""
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in LINK_RE.finditer(line):
            yield number, match.group(1)


def relative_link_problems(root=ROOT):
    """Return (file, line, target) for relative links that do not resolve."""
    problems = []
    for path in published_files(root, "*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append((path, 0, f"unreadable: {exc}"))
            continue
        for number, target in markdown_links(text):
            if target.startswith("#"):
                continue
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if target.startswith("/") or SCHEME_RE.match(target):
                continue
            target = unquote(target.split("#", 1)[0])
            if not target:
                continue
            if not (path.parent / target).exists():
                problems.append((path, number, target))
    return problems


def check_links(root=ROOT) -> int:
    problems = relative_link_problems(root)
    for path, number, target in problems:
        print(f"FAIL link: {path.relative_to(root)}:{number}: {target}")
    if problems:
        return 1
    count = len(list(published_files(root, "*.md")))
    print(f"PASS links: {count} Markdown file(s)")
    return 0


def manifest_doc_problems(root=ROOT):
    """Manifest repos the integration doc does not name by fork path."""
    doc_path = root / DOC_FORKS
    try:
        doc = doc_path.read_text(encoding="utf-8")
        manifest = json.loads((root / "integration.json").read_text(encoding="utf-8"))
        names = [repo["name"] for repo in manifest["repos"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, [str(exc)]
    return names, [name for name in names if f"work/forks/{name}" not in doc]


def check_manifest_docs(root=ROOT) -> int:
    names, missing = manifest_doc_problems(root)
    if names is None:
        print(f"FAIL docs: cannot read integration.json or {DOC_FORKS}: {missing[0]}")
        return 1
    if missing:
        print(f"FAIL docs: {DOC_FORKS} does not name: " + ", ".join(missing))
        return 1
    print(f"PASS docs: {len(names)} manifest repo(s) named in {DOC_FORKS}")
    return 0


def check_tests() -> int:
    failures = 0
    for path in sorted((ROOT / "tools").glob("test_*.py")):
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if proc.returncode != 0:
            print(f"FAIL tests: {path.relative_to(ROOT)}")
            print(proc.stdout.rstrip())
            failures += 1
    if failures == 0:
        print("PASS tests: tools/test_*.py")
    return failures


def main() -> int:
    failures = (
        check_python()
        + check_json()
        + check_links()
        + check_manifest_docs()
        + check_tests()
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
