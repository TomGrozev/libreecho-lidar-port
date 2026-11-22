"""Manifest parsing and the static safety guards.

The manifest describes the target identity and the partition sources for one
restore or preparation run. Loading it validates the schema, the local source
files, and every rule that does not need a backend. Backend-dependent checks
(identity comparison, partition existence) live in core.build_plan.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic import sha256_bytes, sha256_file
from .errors import GuardError, ManifestError

SCHEMA_VERSION = 1

POLICY_SECTOR0_LAST = "sector0_last"
POLICY_READBACK_VERIFY = "readback_verify"
POLICY_NEVER_WRITE = "never_write"
# Opt-in: a boot0 source covers both 2 MiB boot areas (the full 4 MiB eMMC BOOT
# partition). It is deliberately separate from the normal boot0 policy set, so
# area 2 cannot be rewritten under an existing 2 MiB entry.
POLICY_FULL_BOOT0 = "full_boot0"
POLICIES = {
    POLICY_SECTOR0_LAST,
    POLICY_READBACK_VERIFY,
    POLICY_NEVER_WRITE,
    POLICY_FULL_BOOT0,
}

# Boot-chain partition names on this board, taken from the Phase 1 GPT read
# (experiments/phase-01/brom-printgpt.log). boot0 is eMMC boot area 1 and
# boot1 is eMMC boot area 2 in MediaTek naming.
PARTITION_KINDS = {
    "boot0": "boot1",
    "boot1": "boot2",
    "gpt": "user",
    # The backup GPT copy is not a GPT entry either. It is reachable only by
    # absolute address, so an entry for it carries an explicit offset.
    "gpt_backup": "user",
    "lk_a": "user",
    "lk_b": "user",
    "tee1": "user",
    "tee2": "user",
    "expdb": "user",
    "misc": "user",
    "boot_a": "user",
    "boot_b": "user",
}

# Writing this marker to expdb on a Kaeru chain would destroy the LK stage.
# The fastboot marker belongs in misc, and even there the tool refuses it.
FASTBOOT_MARKER = b"FASTBOOT_PLEASE"

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class DeviceIdentity:
    hwcode: int
    flash_bytes: int
    boot_area_bytes: int
    sector_bytes: int

    def to_dict(self) -> dict[str, int]:
        return {
            "hwcode": self.hwcode,
            "flash_bytes": self.flash_bytes,
            "boot_area_bytes": self.boot_area_bytes,
            "sector_bytes": self.sector_bytes,
        }

    @classmethod
    def from_dict(cls, obj: Any, where: str) -> "DeviceIdentity":
        if not isinstance(obj, dict):
            raise ManifestError(f"{where}: device identity must be a JSON object")
        required = {"hwcode", "flash_bytes", "boot_area_bytes", "sector_bytes"}
        missing = required - set(obj)
        if missing:
            raise ManifestError(f"{where}: device identity is missing {sorted(missing)}")
        extra = set(obj) - required
        if extra:
            raise ManifestError(f"{where}: device identity has unknown fields {sorted(extra)}")
        return cls(
            hwcode=parse_hwcode(obj["hwcode"], f"{where}.hwcode"),
            flash_bytes=parse_positive_int(obj["flash_bytes"], f"{where}.flash_bytes"),
            boot_area_bytes=parse_positive_int(obj["boot_area_bytes"], f"{where}.boot_area_bytes"),
            sector_bytes=parse_positive_int(obj["sector_bytes"], f"{where}.sector_bytes"),
        )


@dataclass(frozen=True)
class PartitionSpec:
    name: str
    kind: str
    partition_bytes: int
    source: Path
    source_bytes: int
    sha256: str
    policies: frozenset[str]
    offset: int = 0

    @property
    def writable(self) -> bool:
        return POLICY_NEVER_WRITE not in self.policies


@dataclass(frozen=True)
class Manifest:
    path: Path
    raw_sha256: str
    device: DeviceIdentity
    chain_installed: bool
    partitions: tuple[PartitionSpec, ...]

    def partition(self, name: str) -> PartitionSpec:
        for spec in self.partitions:
            if spec.name == name:
                return spec
        raise ManifestError(f"manifest has no partition {name!r}")


def parse_hwcode(value: Any, where: str) -> int:
    if isinstance(value, bool):
        raise ManifestError(f"{where}: hwcode must be an integer or hex string")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            result = int(text, 16) if text.lower().startswith("0x") else int(text, 10)
        except ValueError as exc:
            raise ManifestError(f"{where}: cannot parse hwcode {value!r}") from exc
    else:
        raise ManifestError(f"{where}: hwcode must be an integer or hex string")
    if result < 0:
        raise ManifestError(f"{where}: hwcode must be non-negative")
    return result


def parse_positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ManifestError(f"{where}: expected a positive integer, got {value!r}")
    return value


def load_manifest(path: Path) -> Manifest:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError("manifest must be a JSON object")

    allowed = {"schema_version", "device", "chain_installed", "partitions", "description"}
    extra = set(doc) - allowed
    if extra:
        raise ManifestError(f"manifest has unknown top-level fields {sorted(extra)}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(
            f"manifest schema_version must be {SCHEMA_VERSION}, got {doc.get('schema_version')!r}"
        )
    if "device" not in doc:
        raise ManifestError("manifest is missing the device identity block")
    if not isinstance(doc.get("chain_installed", False), bool):
        raise ManifestError("chain_installed must be a boolean")
    if "description" in doc and not isinstance(doc["description"], str):
        raise ManifestError("description must be a string")

    device = DeviceIdentity.from_dict(doc["device"], "device")
    chain_installed = doc.get("chain_installed", False)

    partitions_doc = doc.get("partitions")
    if not isinstance(partitions_doc, list) or not partitions_doc:
        raise ManifestError("manifest must contain a non-empty partitions list")

    partitions: list[PartitionSpec] = []
    seen: set[str] = set()
    for index, entry in enumerate(partitions_doc):
        spec = _parse_partition(entry, f"partitions[{index}]", path.parent, device)
        if spec.name in seen:
            raise ManifestError(f"duplicate partition {spec.name!r} in manifest")
        seen.add(spec.name)
        partitions.append(spec)

    for spec in partitions:
        _static_guards(spec, device, chain_installed)
    _cross_guards(partitions)

    return Manifest(
        path=path,
        raw_sha256=sha256_bytes(raw),
        device=device,
        chain_installed=chain_installed,
        partitions=tuple(partitions),
    )


def _parse_partition(entry: Any, where: str, base: Path, device: DeviceIdentity) -> PartitionSpec:
    if not isinstance(entry, dict):
        raise ManifestError(f"{where}: partition entry must be a JSON object")
    required = {
        "name",
        "kind",
        "partition_bytes",
        "source",
        "source_bytes",
        "sha256",
        "policies",
    }
    missing = required - set(entry)
    if missing:
        raise ManifestError(f"{where}: missing fields {sorted(missing)}")
    extra = set(entry) - required - {"offset"}
    if extra:
        raise ManifestError(f"{where}: unknown fields {sorted(extra)}")

    name = entry["name"]
    if not isinstance(name, str) or not name:
        raise ManifestError(f"{where}.name: expected a non-empty string")
    kind = entry["kind"]
    if kind not in {"boot1", "boot2", "user"}:
        raise ManifestError(f"{where}.kind: expected boot1, boot2, or user, got {kind!r}")

    partition_bytes = parse_positive_int(entry["partition_bytes"], f"{where}.partition_bytes")
    source_bytes = parse_positive_int(entry["source_bytes"], f"{where}.source_bytes")
    if not isinstance(entry["source"], str) or not entry["source"]:
        raise ManifestError(f"{where}.source: expected a non-empty path string")
    source = Path(entry["source"])
    if not source.is_absolute():
        source = base / source
    source = source.resolve()
    if not source.is_file():
        raise ManifestError(f"{where}.source: {source} is not a regular file")

    declared_hash = entry["sha256"]
    if not isinstance(declared_hash, str) or not _HEX64.match(declared_hash):
        raise ManifestError(f"{where}.sha256: expected 64 hex characters")
    declared_hash = declared_hash.lower()

    policies_doc = entry["policies"]
    if not isinstance(policies_doc, list) or not all(isinstance(p, str) for p in policies_doc):
        raise ManifestError(f"{where}.policies: expected a list of strings")
    policies = frozenset(policies_doc)
    unknown_policies = policies - POLICIES
    if unknown_policies:
        raise ManifestError(f"{where}.policies: unknown policies {sorted(unknown_policies)}")

    offset = entry.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ManifestError(f"{where}.offset: expected a non-negative integer, got {offset!r}")

    return PartitionSpec(
        name=name,
        kind=kind,
        partition_bytes=partition_bytes,
        source=source,
        source_bytes=source_bytes,
        sha256=declared_hash,
        policies=policies,
        offset=offset,
    )


def _static_guards(spec: PartitionSpec, device: DeviceIdentity, chain_installed: bool) -> None:
    expected_kind = PARTITION_KINDS.get(spec.name)
    if expected_kind is None:
        raise GuardError(
            f"unknown partition {spec.name!r}: not in the Lidar boot-chain partition set "
            f"{sorted(PARTITION_KINDS)}"
        )
    if expected_kind != spec.kind:
        raise GuardError(
            f"partition {spec.name!r} must use kind {expected_kind!r}, manifest says {spec.kind!r}"
        )

    actual_size = spec.source.stat().st_size
    if actual_size != spec.source_bytes:
        raise GuardError(
            f"source size mismatch for {spec.name!r}: manifest says {spec.source_bytes} bytes, "
            f"{spec.source} is {actual_size} bytes"
        )
    if spec.source_bytes > spec.partition_bytes:
        raise GuardError(
            f"partition {spec.name!r} is too small: source is {spec.source_bytes} bytes, "
            f"partition is {spec.partition_bytes} bytes"
        )
    if spec.offset % device.sector_bytes:
        raise GuardError(
            f"partition {spec.name!r} has offset {spec.offset}, which is not a multiple of the "
            f"{device.sector_bytes}-byte sector"
        )
    if spec.offset + spec.source_bytes > spec.partition_bytes:
        raise GuardError(
            f"partition {spec.name!r} is too small for its extent: offset {spec.offset} plus "
            f"source {spec.source_bytes} reaches past {spec.partition_bytes} bytes"
        )
    if spec.offset and spec.kind in {"boot1", "boot2"}:
        raise GuardError(
            f"partition {spec.name!r} is a boot area and must start at offset 0, "
            f"manifest says {spec.offset}"
        )
    actual_hash = sha256_file(spec.source)
    if actual_hash != spec.sha256:
        raise GuardError(
            f"source hash mismatch for {spec.name!r}: manifest says {spec.sha256}, "
            f"file hashes to {actual_hash}"
        )

    if POLICY_FULL_BOOT0 in spec.policies and not (
        spec.name == "boot0" and spec.kind == "boot1"
    ):
        raise GuardError(
            f"'{POLICY_FULL_BOOT0}' is only valid on the boot0 boot-area-1 entry, "
            f"not {spec.name!r} ({spec.kind})"
        )

    if spec.kind == "boot1":
        # MediaTek BOOT0 is boot area 1 plus boot area 2. The manifest item
        # must stay inside area 1 so a BOOT0 write can never touch the
        # identity store, unless it explicitly opts into the full 4 MiB
        # target with POLICY_FULL_BOOT0.
        if spec.name != "boot0":
            raise GuardError(f"boot area 1 partition must be named 'boot0', got {spec.name!r}")
        if POLICY_FULL_BOOT0 in spec.policies:
            if spec.partition_bytes != 2 * device.boot_area_bytes:
                raise GuardError(
                    f"full_boot0 partition_bytes must equal both boot areas "
                    f"({2 * device.boot_area_bytes}), got {spec.partition_bytes}"
                )
            if spec.source_bytes != spec.partition_bytes:
                raise GuardError(
                    f"full_boot0 source must cover the whole "
                    f"{2 * device.boot_area_bytes}-byte BOOT0, got {spec.source_bytes} bytes"
                )
        else:
            if spec.partition_bytes != device.boot_area_bytes:
                raise GuardError(
                    f"boot0 partition_bytes must equal device.boot_area_bytes "
                    f"({device.boot_area_bytes}), got {spec.partition_bytes}"
                )
            if spec.source_bytes > device.boot_area_bytes:
                raise GuardError(
                    f"boot0 source spans {spec.source_bytes} bytes, beyond the "
                    f"{device.boot_area_bytes}-byte boot area 1; a BOOT0 write must never "
                    "include boot area 2"
                )
        # Not a manifest preference: a new boot header over a partially written
        # body boots nothing. Every BOOT0 write defers sector 0 to the end.
        if spec.writable and POLICY_SECTOR0_LAST not in spec.policies:
            raise GuardError(
                f"a writable boot0 must carry '{POLICY_SECTOR0_LAST}' so the boot "
                "header is written after the body"
            )

    if spec.kind == "boot2":
        if POLICY_NEVER_WRITE not in spec.policies:
            raise GuardError(
                f"boot area 2 ({spec.name!r}) is the identity store and must carry the "
                "'never_write' policy"
            )
        if POLICY_SECTOR0_LAST in spec.policies:
            raise GuardError(f"'sector0_last' is not valid for boot area 2 ({spec.name!r})")

    if POLICY_SECTOR0_LAST in spec.policies:
        if spec.kind != "boot1":
            raise GuardError(f"'sector0_last' is only valid for boot area 1, not {spec.name!r}")
        if spec.source_bytes <= device.sector_bytes:
            raise GuardError(
                f"'sector0_last' requires more than one sector of source data for {spec.name!r}"
            )
        if POLICY_READBACK_VERIFY not in spec.policies:
            raise GuardError(
                f"'sector0_last' requires 'readback_verify' for {spec.name!r}"
            )

    if spec.writable and POLICY_READBACK_VERIFY not in spec.policies:
        raise GuardError(
            f"writable partition {spec.name!r} must declare 'readback_verify'; "
            "per-write verification is mandatory for this tool"
        )

    if spec.name == "expdb" and chain_installed and spec.writable:
        raise GuardError(
            "refusing to write expdb: the manifest marks a Kaeru chain as installed, and "
            "expdb holds the LK stage after installation"
        )

    if spec.name in {"expdb", "misc"}:
        payload = spec.source.read_bytes()
        if FASTBOOT_MARKER in payload:
            raise GuardError(
                f"refusing to write {spec.name}: source contains the ASCII marker "
                f"{FASTBOOT_MARKER.decode()!r}"
            )


def _cross_guards(partitions: list[PartitionSpec]) -> None:
    full = [spec for spec in partitions if POLICY_FULL_BOOT0 in spec.policies]
    if not full:
        return
    # A full BOOT0 write already replaces both areas. A second entry for boot
    # area 2 would either address it twice or claim it is never written while
    # the same plan overwrites it, so neither is accepted.
    boot2 = [spec.name for spec in partitions if spec.kind == "boot2"]
    if boot2:
        raise GuardError(
            f"'full_boot0' covers both boot areas; remove the separate boot-area-2 "
            f"entry {boot2!r} from the manifest"
        )
    if len(full) != 1:
        raise GuardError("'full_boot0' may appear on exactly one boot0 entry")

