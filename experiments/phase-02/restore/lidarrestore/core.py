"""Plan construction, apply, and verify.

Write order is defined entirely by the manifest order, except that a
`sector0_last` partition is split into its body (sector 1 to end) followed by
sector 0 as the final write to that partition. A readback mismatch raises
immediately, so later items, including sector 0, are never written.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic import atomic_write_json, canonical_json, fsync_dir, sha256_bytes, sha256_file
from .backends import Backend
from .errors import (
    BackendWriteRefused,
    GuardError,
    JournalError,
    ManifestError,
    ReadbackError,
)
from .journal import append_record, make_header, make_op_record, read_journal
from .manifest import (
    POLICY_FULL_BOOT0,
    POLICY_NEVER_WRITE,
    POLICY_SECTOR0_LAST,
    DeviceIdentity,
    Manifest,
    PartitionSpec,
)

PLAN_VERSION = 1
ITEM_FIELDS = {
    "index",
    "partition",
    "kind",
    "offset",
    "length",
    "source_offset",
    "sha256",
    "purpose",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def compute_plan_hash(plan: dict[str, Any]) -> str:
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    return sha256_bytes(canonical_json(body))


def compare_identity(expected: DeviceIdentity, actual: DeviceIdentity) -> list[str]:
    mismatches = []
    for field in ("hwcode", "flash_bytes", "boot_area_bytes", "sector_bytes"):
        left = getattr(expected, field)
        right = getattr(actual, field)
        if left != right:
            mismatches.append(f"{field}: manifest {left!r}, backend {right!r}")
    return mismatches


def _read_source_slice(spec: PartitionSpec, offset: int, length: int) -> bytes:
    try:
        with open(spec.source, "rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
    except OSError as exc:
        raise ManifestError(f"cannot read source {spec.source}: {exc}") from exc
    if len(data) != length:
        raise ManifestError(
            f"short source read for {spec.name!r}: wanted {length} bytes at {offset}, "
            f"got {len(data)}"
        )
    return data


def _target_kinds(spec: PartitionSpec) -> tuple[str, ...]:
    if POLICY_FULL_BOOT0 in spec.policies:
        return ("boot1", "boot2")
    return (spec.kind,)


def _items_for(spec: PartitionSpec, sector_bytes: int) -> list[dict[str, Any]]:
    # Each span is (write offset, source offset, length, purpose, kind).
    spans: list[tuple[int, int, int, str, str]]
    if POLICY_FULL_BOOT0 in spec.policies:
        # The 4 MiB source covers boot area 1 then boot area 2. Emit area 2 as
        # its own item so the plan shows the identity-store write explicitly.
        # Boot-area writes are addressed from each area's own base.
        area_bytes = spec.partition_bytes // 2
        spans = [
            (spec.offset + sector_bytes, sector_bytes, area_bytes - sector_bytes, "body", "boot1"),
            (spec.offset, area_bytes, spec.source_bytes - area_bytes, "area2", "boot2"),
            (spec.offset, 0, sector_bytes, "sector_zero", "boot1"),
        ]
    elif POLICY_SECTOR0_LAST in spec.policies:
        spans = [
            (spec.offset + sector_bytes, sector_bytes, spec.source_bytes - sector_bytes, "body", spec.kind),
            (spec.offset, 0, sector_bytes, "sector_zero", spec.kind),
        ]
    else:
        spans = [(spec.offset, 0, spec.source_bytes, "full", spec.kind)]
    items = []
    for write_offset, source_offset, length, purpose, kind in spans:
        data = _read_source_slice(spec, source_offset, length)
        items.append(
            {
                "partition": spec.name,
                "kind": kind,
                "offset": write_offset,
                "length": length,
                "source_offset": source_offset,
                "sha256": sha256_bytes(data),
                "purpose": purpose,
            }
        )
    return items


def build_plan(manifest: Manifest, backend: Backend) -> dict[str, Any]:
    """Validate the target and sources, then emit the ordered write plan."""
    mismatches = compare_identity(manifest.device, backend.identity())
    if mismatches:
        raise GuardError(
            "device identity mismatch: " + "; ".join(mismatches) + ". Refusing to plan."
        )

    items: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for spec in manifest.partitions:
        kinds = _target_kinds(spec)
        # The existence guard runs first so a missing partition reports as a
        # guard failure rather than as the backend's file error from capacity().
        if POLICY_NEVER_WRITE not in spec.policies:
            for kind in kinds:
                if not backend.known(spec.name, kind):
                    raise GuardError(
                        f"unknown partition {spec.name!r} ({kind}): not present on backend "
                        f"{backend.describe()}"
                    )
        expected_bytes = spec.partition_bytes // len(kinds)
        for kind in kinds:
            actual_bytes = backend.capacity(spec.name, kind)
            if actual_bytes is not None and actual_bytes != expected_bytes:
                if len(kinds) == 1:
                    raise GuardError(
                        f"partition size mismatch for {spec.name!r}: manifest says "
                        f"{spec.partition_bytes} bytes, backend reports {actual_bytes} bytes"
                    )
                raise GuardError(
                    f"partition size mismatch for {spec.name!r} ({kind}): manifest says "
                    f"{expected_bytes} bytes per boot area, backend reports {actual_bytes} bytes"
                )
        if POLICY_NEVER_WRITE in spec.policies:
            skipped.append({"name": spec.name, "reason": "never_write"})
            continue
        if sha256_file(spec.source) != spec.sha256:
            raise GuardError(
                f"source hash mismatch for {spec.name!r}: the file changed after the manifest "
                "was loaded"
            )
        for item in _items_for(spec, manifest.device.sector_bytes):
            item["index"] = len(items)
            items.append(item)

    # The boot header is the commit point of the whole run, not just of boot0:
    # no later write may leave a new header over a body or companion partition
    # that was rolled back or half-written.
    body_items = [item for item in items if item["purpose"] != "sector_zero"]
    header_items = [item for item in items if item["purpose"] == "sector_zero"]
    items = body_items + header_items
    for index, item in enumerate(items):
        item["index"] = index

    plan: dict[str, Any] = {
        "schema_version": PLAN_VERSION,
        "manifest_sha256": manifest.raw_sha256,
        "device": manifest.device.to_dict(),
        "items": items,
        "skipped": skipped,
    }
    plan["plan_sha256"] = compute_plan_hash(plan)
    return plan


def write_plan(path: Path, plan: dict[str, Any]) -> None:
    atomic_write_json(Path(path), plan)


def load_plan(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        doc = json.loads(path.read_bytes())
    except OSError as exc:
        raise ManifestError(f"cannot read plan {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"plan {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError("plan must be a JSON object")
    required = {"schema_version", "manifest_sha256", "device", "items", "skipped", "plan_sha256"}
    missing = required - set(doc)
    if missing:
        raise ManifestError(f"plan is missing {sorted(missing)}")
    if set(doc) != required:
        raise ManifestError(f"plan has unknown fields {sorted(set(doc) - required)}")
    if doc["schema_version"] != PLAN_VERSION:
        raise ManifestError(
            f"plan schema_version must be {PLAN_VERSION}, got {doc['schema_version']!r}"
        )
    DeviceIdentity.from_dict(doc["device"], "plan.device")
    if not isinstance(doc["items"], list) or not isinstance(doc["skipped"], list):
        raise ManifestError("plan items and skipped must be lists")
    for index, item in enumerate(doc["items"]):
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            raise ManifestError(f"plan item {index} has the wrong fields")
        if item["index"] != index:
            raise ManifestError(f"plan item {index} carries index {item['index']!r}")
        for field in ("offset", "length", "source_offset"):
            if not isinstance(item[field], int) or item[field] < 0:
                raise ManifestError(f"plan item {index} has an invalid {field}")
        if item["length"] <= 0:
            raise ManifestError(f"plan item {index} has an empty length")
    if doc["plan_sha256"] != compute_plan_hash(doc):
        raise ManifestError("plan hash does not match its contents; the plan file was edited")
    return doc


def validate_plan_against(manifest: Manifest, plan: dict[str, Any], backend: Backend) -> None:
    if plan["manifest_sha256"] != manifest.raw_sha256:
        raise GuardError(
            "plan was built for a different manifest: plan says "
            f"{plan['manifest_sha256']}, manifest hashes to {manifest.raw_sha256}"
        )
    if plan["plan_sha256"] != compute_plan_hash(plan):
        raise GuardError("plan hash does not match its contents; the plan file was edited")
    rebuilt = build_plan(manifest, backend)
    if rebuilt["items"] != plan["items"]:
        raise GuardError(
            "plan does not match a freshly built plan for this manifest and backend; "
            "sources, identity, or manifest changed since the plan was written"
        )
    if rebuilt["skipped"] != plan["skipped"]:
        raise GuardError("plan skipped list does not match the current manifest")


def _write_state(path: Path, plan: dict[str, Any], completed: int, total: int) -> None:
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "plan_sha256": plan["plan_sha256"],
            "completed_items": completed,
            "total_items": total,
            "updated_at": _now(),
        },
    )


def _write_result(
    path: Path,
    manifest: Manifest,
    plan: dict[str, Any],
    status: str,
    completed: int,
    started_at: str,
    error: str | None = None,
) -> None:
    doc: dict[str, Any] = {
        "schema_version": 1,
        "status": status,
        "manifest_sha256": manifest.raw_sha256,
        "plan_sha256": plan["plan_sha256"],
        "completed_items": completed,
        "total_items": len(plan["items"]),
        "started_at": started_at,
        "finished_at": _now(),
    }
    if error is not None:
        doc["error"] = error
    atomic_write_json(path, doc)


def apply_plan(
    manifest: Manifest,
    plan: dict[str, Any],
    backend: Backend,
    journal_path: Path,
    state_path: Path | None = None,
    result_path: Path | None = None,
    allow_write: bool = False,
    resume: bool = False,
) -> dict[str, Any]:
    """Execute a plan. Dry-run unless allow_write is set.

    Every write is read back and compared before its journal record is
    appended. A mismatch aborts before the next plan item, which keeps sector 0
    of a `sector0_last` partition untouched unless its body already verified.
    """
    validate_plan_against(manifest, plan, backend)
    items = plan["items"]
    journal_path = Path(journal_path)

    if not allow_write:
        completed: set[int] = set()
        if resume and journal_path.exists():
            completed = read_journal(
                journal_path,
                manifest.raw_sha256,
                plan["plan_sha256"],
                backend.name,
                items,
            )
        return {
            "dry_run": True,
            "backend": backend.describe(),
            "manifest_sha256": manifest.raw_sha256,
            "plan_sha256": plan["plan_sha256"],
            "total_items": len(items),
            "would_skip": sorted(completed),
            "items": items,
        }

    if not backend.writable:
        raise BackendWriteRefused(
            f"backend {backend.describe()} does not permit writes; the mtkclient backend "
            "needs --allow-device-write"
        )

    state_path = Path(state_path) if state_path else Path(str(journal_path) + ".state.json")
    result_path = Path(result_path) if result_path else Path(str(journal_path) + ".result.json")

    if journal_path.exists() and journal_path.stat().st_size == 0:
        # A crash between file creation and the header fsync leaves an empty
        # journal. It records no run, so it must not block a fresh start or a
        # resume.
        journal_path.unlink()
    if journal_path.exists():
        if not resume:
            raise JournalError(
                f"journal {journal_path} already exists; pass --resume to continue it or "
                "choose a new journal path"
            )
        completed = read_journal(
            journal_path,
            manifest.raw_sha256,
            plan["plan_sha256"],
            backend.name,
            items,
        )
    else:
        completed = set()

    started_at = _now()
    _write_state(state_path, plan, len(completed), len(items))

    journal_path.parent.mkdir(parents=True, exist_ok=True)
    if not journal_path.exists():
        # The header fsync covers the bytes; the parent fsync covers the name.
        with open(journal_path, "x", encoding="utf-8"):
            pass
        fsync_dir(journal_path.parent)
    with open(journal_path, "a", encoding="utf-8") as journal:
        if not completed and journal_path.stat().st_size == 0:
            append_record(
                journal,
                make_header(manifest.raw_sha256, plan["plan_sha256"], backend.name),
            )
        try:
            for item in items:
                if item["index"] in completed:
                    continue
                spec = manifest.partition(item["partition"])
                data = _read_source_slice(spec, item["source_offset"], item["length"])
                if sha256_bytes(data) != item["sha256"]:
                    raise GuardError(
                        f"source for {spec.name!r} changed after the plan was built"
                    )
                backend.write(
                    spec.name,
                    item["kind"],
                    item["offset"],
                    data,
                    boot_area_2_write=POLICY_FULL_BOOT0 in spec.policies,
                )
                readback = backend.read(spec.name, item["kind"], item["offset"], len(data))
                if readback != data:
                    raise ReadbackError(
                        f"readback mismatch for {spec.name!r} at offset 0x{item['offset']:x} "
                        f"({item['length']} bytes): expected sha256 {item['sha256']}, "
                        f"readback sha256 {sha256_bytes(readback)}"
                    )
                append_record(journal, make_op_record(item))
                completed.add(item["index"])
                _write_state(state_path, plan, len(completed), len(items))
        except Exception as exc:
            try:
                _write_result(
                    result_path,
                    manifest,
                    plan,
                    "failed",
                    len(completed),
                    started_at,
                    error=str(exc),
                )
            except Exception as result_exc:
                exc.add_note(f"could not write result file {result_path}: {result_exc}")
            raise

    _write_result(result_path, manifest, plan, "complete", len(completed), started_at)
    return {
        "dry_run": False,
        "backend": backend.describe(),
        "manifest_sha256": manifest.raw_sha256,
        "plan_sha256": plan["plan_sha256"],
        "total_items": len(items),
        "completed_items": len(completed),
        "journal": str(journal_path),
        "state": str(state_path),
        "result": str(result_path),
    }


def verify_manifest(manifest: Manifest, backend: Backend) -> dict[str, Any]:
    """Read-only comparison of every manifest source extent against the backend."""
    mismatches = compare_identity(manifest.device, backend.identity())
    if mismatches:
        raise GuardError(
            "device identity mismatch: " + "; ".join(mismatches) + ". Refusing to verify."
        )

    results = []
    for spec in manifest.partitions:
        kinds = _target_kinds(spec)
        for kind in kinds:
            if not backend.known(spec.name, kind):
                raise GuardError(
                    f"unknown partition {spec.name!r} ({kind}): not present on backend "
                    f"{backend.describe()}"
                )
        if POLICY_FULL_BOOT0 in spec.policies:
            area_bytes = spec.partition_bytes // 2
            data = b"".join(
                backend.read(spec.name, kind, 0, area_bytes) for kind in kinds
            )
            kind_label = "+".join(kinds)
        else:
            data = backend.read(spec.name, spec.kind, spec.offset, spec.source_bytes)
            kind_label = spec.kind
        actual = sha256_bytes(data)
        entry: dict[str, Any] = {
            "name": spec.name,
            "kind": kind_label,
            "expected_sha256": spec.sha256,
            "actual_sha256": actual,
            "bytes_read": len(data),
            "ok": actual == spec.sha256 and len(data) == spec.source_bytes,
        }
        if not entry["ok"]:
            entry["error"] = "readback does not match the manifest source hash"
        results.append(entry)
    return {
        "schema_version": 1,
        "ok": all(entry["ok"] for entry in results),
        "partitions": results,
    }



