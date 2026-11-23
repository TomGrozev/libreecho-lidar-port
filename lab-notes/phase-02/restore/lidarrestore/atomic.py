"""Atomic file helpers and hash utilities.

Plan, state, and result files are JSON documents that a later run reads. A
crash must never leave a half-written document behind: serialize fully in
memory first, write a temporary file in the same directory, fsync it, rename
it over the target, then fsync the directory entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Stable JSON bytes used for hashing plans and journal records."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write data to path with fsync and rename, never exposing partial bytes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    fsync_dir(path.parent)


def atomic_write_json(path: Path, value: Any) -> None:
    # Serialize before touching the filesystem so an unserializable value
    # leaves the destination and its directory untouched.
    data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(path, data)


def fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
