"""Append-only JSONL resume journal.

The journal is the authority on what has been written. Each completed write is
one line, fsynced before the next operation starts. A torn or edited journal is
refused instead of guessed at: resume must prove that every recorded operation
is the exact plan prefix, in order, for this manifest and plan.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, TextIO

from .atomic import canonical_json
from .errors import JournalError

JOURNAL_VERSION = 1

OP_FIELDS = ("index", "partition", "kind", "offset", "length", "sha256")


def make_header(manifest_sha256: str, plan_sha256: str, backend_name: str) -> dict[str, Any]:
    return {
        "type": "header",
        "version": JOURNAL_VERSION,
        "manifest_sha256": manifest_sha256,
        "plan_sha256": plan_sha256,
        "backend": backend_name,
    }


def make_op_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "op",
        "index": item["index"],
        "partition": item["partition"],
        "kind": item["kind"],
        "offset": item["offset"],
        "length": item["length"],
        "sha256": item["sha256"],
    }


def encode_record(record: dict[str, Any]) -> bytes:
    return canonical_json(record) + b"\n"


def append_record(fh: TextIO, record: dict[str, Any]) -> None:
    fh.write(encode_record(record).decode("utf-8"))
    fh.flush()
    os.fsync(fh.fileno())


def read_journal(
    path: Path,
    manifest_sha256: str,
    plan_sha256: str,
    backend_name: str,
    items: list[dict[str, Any]],
) -> set[int]:
    """Validate a journal and return the set of completed item indices.

    Raises JournalError on any deviation: wrong header, wrong hashes, wrong
    backend, malformed JSON, non-prefix order, or a record that does not match
    the plan item at that index.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise JournalError(f"cannot read journal {path}: {exc}") from exc
    if not raw:
        raise JournalError(f"journal {path} is empty; it has no header")
    if not raw.endswith(b"\n"):
        raise JournalError(f"journal {path} ends with a partial line")

    lines = raw.splitlines()
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise JournalError(f"journal {path} line 1 is not valid JSON: {exc}") from exc
    if not isinstance(header, dict) or header.get("type") != "header":
        raise JournalError(f"journal {path} line 1 is not a header record")
    if header.get("version") != JOURNAL_VERSION:
        raise JournalError(
            f"journal {path} version is {header.get('version')!r}, expected {JOURNAL_VERSION}"
        )
    for field, expected, label in (
        ("manifest_sha256", manifest_sha256, "manifest"),
        ("plan_sha256", plan_sha256, "plan"),
        ("backend", backend_name, "backend"),
    ):
        if header.get(field) != expected:
            raise JournalError(
                f"journal {path} does not belong to this run: {label} mismatch "
                f"(journal {header.get(field)!r}, now {expected!r})"
            )

    completed: set[int] = set()
    for offset, line in enumerate(lines[1:], start=2):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalError(f"journal {path} line {offset} is not valid JSON: {exc}") from exc
        if not isinstance(record, dict) or record.get("type") != "op":
            raise JournalError(f"journal {path} line {offset} is not an operation record")
        expected_index = len(completed)
        if record.get("index") != expected_index:
            raise JournalError(
                f"journal {path} line {offset} has index {record.get('index')!r}, "
                f"expected {expected_index}; the completed set must be a prefix of the plan"
            )
        if expected_index >= len(items):
            raise JournalError(
                f"journal {path} line {offset} records more operations than the plan has"
            )
        item = items[expected_index]
        for field in OP_FIELDS:
            if record.get(field) != item[field]:
                raise JournalError(
                    f"journal {path} line {offset} does not match plan item "
                    f"{expected_index}: {field} is {record.get(field)!r}, "
                    f"plan says {item[field]!r}"
                )
        extra = set(record) - {"type", *OP_FIELDS}
        if extra:
            raise JournalError(f"journal {path} line {offset} has unknown fields {sorted(extra)}")
        completed.add(expected_index)
    return completed

