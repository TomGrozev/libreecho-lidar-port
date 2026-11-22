"""Host tests for the Lidar boot-chain restore tool.

All tests run against temporary directories and synthetic images. Nothing here
touches a device; the mtkclient adapter is exercised with a fake command runner
that records argv and writes stand-in readback files.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lidarrestore.atomic import atomic_write_json
from lidarrestore.backends import (
    BackendWriteRefused,
    BackendError,
    Faults,
    MtkclientBackend,
    SyntheticBackend,
    parse_printgpt_identity,
)
from lidarrestore.cli import main as cli_main
from lidarrestore.core import (
    apply_plan,
    build_plan,
    load_plan,
    verify_manifest,
    write_plan,
)
from lidarrestore.errors import GuardError, JournalError, ManifestError, ReadbackError
from lidarrestore.manifest import load_manifest

BOOT_AREA = 4096
SECTOR = 512
FLASH = 1 << 20
TEE_SIZE = 8192

IDENTITY = {
    "hwcode": "0x8167",
    "flash_bytes": FLASH,
    "boot_area_bytes": BOOT_AREA,
    "sector_bytes": SECTOR,
}


def blob(seed: str, size: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out.extend(hashlib.sha256(f"{seed}:{counter}".encode()).digest())
        counter += 1
    return bytes(out[:size])


class RecordingRunner:
    """Records mtkclient argv and write payloads as they are handed over."""

    def __init__(self, readback: bytes | None = None) -> None:
        self.calls: list[list[str]] = []
        self.written: list[bytes] = []
        self.readback = readback

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        op = cmd[2]
        if op == "r":
            if self.readback is not None:
                Path(cmd[4]).write_bytes(self.readback)
        elif op == "ro":
            if self.readback is not None:
                Path(cmd[5]).write_bytes(self.readback)
        else:
            self.written.append(Path(cmd[5] if op == "wo" else cmd[4]).read_bytes())
        return subprocess.CompletedProcess(cmd, 0, "", "")


class FakeDevice:
    """Fake eMMC images behind the mtkclient command surface.

    Only the commands the adapter emits are modelled: r, w, and wo, with the
    user area addressed absolutely and boot areas addressed from their base.
    """

    def __init__(
        self, boot1: bytes, boot2: bytes, user: bytes, parts: dict[str, int]
    ) -> None:
        self.boot = {"boot1": bytearray(boot1), "boot2": bytearray(boot2)}
        self.user = bytearray(user)
        self.parts = parts
        self.calls: list[list[str]] = []

    def _flag(self, cmd: list[str], name: str, default: str) -> str:
        return cmd[cmd.index(name) + 1] if name in cmd else default

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        op = cmd[2]
        parttype = self._flag(cmd, "--parttype", "user")
        if op == "r":
            target = Path(cmd[4])
            if parttype in self.boot:
                target.write_bytes(bytes(self.boot[parttype]))
            else:
                base = self.parts[cmd[3]]
                if "--offset" in cmd:
                    offset = int(self._flag(cmd, "--offset", "0x0"), 16)
                    length = int(self._flag(cmd, "--length", "0x0"), 16)
                    target.write_bytes(bytes(self.user[base + offset : base + offset + length]))
                else:
                    target.write_bytes(bytes(self.user[base:]))
        elif op == "ro":
            offset = int(cmd[3], 16)
            length = int(cmd[4], 16)
            Path(cmd[5]).write_bytes(bytes(self.user[offset : offset + length]))
        elif op == "w":
            data = Path(cmd[4]).read_bytes()
            base = self.parts[cmd[3]]
            self.user[base : base + len(data)] = data
        elif op == "wo":
            offset = int(cmd[3], 16)
            data = Path(cmd[5]).read_bytes()
            if parttype in self.boot:
                self.boot[parttype][offset : offset + len(data)] = data
            else:
                self.user[offset : offset + len(data)] = data
        else:
            raise AssertionError(f"unexpected mtkclient command {cmd}")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")


class Fixture:
    """Temporary source and synthetic-device directory for one test."""

    def __init__(self, testcase: unittest.TestCase) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="lidar-restore-test-")
        testcase.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.device = self.root / "device"
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.device.mkdir()
        self.identity = dict(IDENTITY)
        (self.device / "identity.json").write_text(json.dumps(self.identity) + "\n")
        self.source_data: dict[str, bytes] = {}

    def add(
        self,
        name: str,
        kind: str,
        partition_bytes: int,
        source_bytes: int | None = None,
        policies: tuple[str, ...] = ("readback_verify",),
        data: bytes | None = None,
        device_data: bytes | None = None,
        on_device: bool = True,
    ) -> dict:
        size = source_bytes if source_bytes is not None else partition_bytes
        payload = data if data is not None else blob(name, size)
        (self.sources / f"{name}.bin").write_bytes(payload)
        if on_device:
            folder = self.device / kind
            folder.mkdir(parents=True, exist_ok=True)
            fill = device_data if device_data is not None else blob("device:" + name, partition_bytes)
            (folder / f"{name}.bin").write_bytes(fill)
        self.source_data[name] = payload
        return {
            "name": name,
            "kind": kind,
            "partition_bytes": partition_bytes,
            "source": f"sources/{name}.bin",
            "source_bytes": size,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "policies": list(policies),
        }

    def standard(self) -> list[dict]:
        boot1_data = blob("boot1", BOOT_AREA)
        return [
            self.add(
                "boot0",
                "boot1",
                BOOT_AREA,
                policies=("sector0_last", "readback_verify"),
            ),
            self.add(
                "boot1",
                "boot2",
                BOOT_AREA,
                policies=("never_write",),
                data=boot1_data,
                device_data=boot1_data,
            ),
            self.add("tee1", "user", TEE_SIZE),
        ]

    def manifest(self, entries: list[dict], chain_installed: bool = False, device: dict | None = None) -> Path:
        path = self.root / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "device": device or self.identity,
                    "chain_installed": chain_installed,
                    "partitions": entries,
                }
            )
            + "\n"
        )
        return path

    def backend(self, faults: Faults | None = None) -> SyntheticBackend:
        return SyntheticBackend(self.device, faults=faults)

    def device_bytes(self, name: str, kind: str) -> bytes:
        return (self.device / kind / f"{name}.bin").read_bytes()

    def apply(
        self,
        manifest_path: Path,
        plan_path: Path,
        backend: SyntheticBackend,
        allow_write: bool = True,
        resume: bool = False,
    ) -> dict:
        manifest = load_manifest(manifest_path)
        plan = load_plan(plan_path)
        return apply_plan(
            manifest,
            plan,
            backend,
            journal_path=self.root / "restore.journal.jsonl",
            state_path=self.root / "restore.state.json",
            result_path=self.root / "restore.result.json",
            allow_write=allow_write,
            resume=resume,
        )


class RestoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = Fixture(self)

    # -- happy path and write order -------------------------------------

    def test_happy_path_synthetic_restore(self) -> None:
        entries = self.fx.standard()
        manifest_path = self.fx.manifest(entries)
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()

        plan = build_plan(manifest, backend)
        self.assertEqual(
            [(item["partition"], item["purpose"], item["offset"]) for item in plan["items"]],
            [
                ("boot0", "body", SECTOR),
                ("tee1", "full", 0),
                ("boot0", "sector_zero", 0),
            ],
        )
        self.assertEqual(plan["skipped"], [{"name": "boot1", "reason": "never_write"}])

        write_plan(self.fx.root / "plan.json", plan)
        result = self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)
        self.assertEqual(result["completed_items"], 3)
        self.assertEqual(result["total_items"], 3)

        self.assertEqual(self.fx.device_bytes("boot0", "boot1"), self.fx.source_data["boot0"])
        self.assertEqual(self.fx.device_bytes("tee1", "user"), self.fx.source_data["tee1"])
        self.assertEqual(
            self.fx.device_bytes("boot1", "boot2"),
            self.fx.source_data["boot1"],
            "boot area 2 must never be written",
        )

        journal_lines = (self.fx.root / "restore.journal.jsonl").read_text().splitlines()
        self.assertEqual(len(journal_lines), 4)  # header plus three operations
        result_doc = json.loads((self.fx.root / "restore.result.json").read_text())
        self.assertEqual(result_doc["status"], "complete")

        report = verify_manifest(manifest, backend)
        self.assertTrue(report["ok"])

    def test_sector_zero_is_last_write_to_boot0(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

        boot0_writes = [call for call in backend.write_calls if call[0] == "boot0"]
        self.assertEqual([(offset, length) for _, _, offset, length in boot0_writes], [(SECTOR, BOOT_AREA - SECTOR), (0, SECTOR)])
        self.assertEqual(boot0_writes[-1][2], 0, "sector 0 must be the final write to boot0")

    def test_full_boot0_policy_writes_both_areas_and_verifies(self) -> None:
        entry = self.fx.add(
            "boot0",
            "boot1",
            2 * BOOT_AREA,
            policies=("sector0_last", "readback_verify", "full_boot0"),
            on_device=False,
        )
        payload = self.fx.source_data["boot0"]
        for folder in ("boot1", "boot2"):
            (self.fx.device / folder).mkdir(exist_ok=True)
            (self.fx.device / folder / "boot0.bin").write_bytes(blob("device:" + folder, BOOT_AREA))
        manifest_path = self.fx.manifest([entry])
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        self.assertEqual(
            [(item["purpose"], item["kind"], item["offset"], item["source_offset"]) for item in plan["items"]],
            [
                ("body", "boot1", SECTOR, SECTOR),
                ("area2", "boot2", 0, BOOT_AREA),
                ("sector_zero", "boot1", 0, 0),
            ],
        )
        write_plan(self.fx.root / "plan.json", plan)
        self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)
        self.assertEqual(self.fx.device_bytes("boot0", "boot1"), payload[:BOOT_AREA])
        self.assertEqual(self.fx.device_bytes("boot0", "boot2"), payload[BOOT_AREA:])
        self.assertEqual(backend.write_calls[-1][0:3], ("boot0", "boot1", 0))
        self.assertTrue(verify_manifest(manifest, backend)["ok"])
        (self.fx.device / "boot2" / "boot0.bin").write_bytes(blob("changed", BOOT_AREA))
        self.assertFalse(verify_manifest(manifest, backend)["ok"])

    def test_full_boot0_and_separate_boot_area_two_entry_refused(self) -> None:
        entries = self.fx.standard()
        entries[0] = self.fx.add(
            "boot0",
            "boot1",
            2 * BOOT_AREA,
            policies=("sector0_last", "readback_verify", "full_boot0"),
            on_device=False,
        )
        with self.assertRaisesRegex(GuardError, "full_boot0.*boot-area-2"):
            load_manifest(self.fx.manifest(entries))

    def test_full_boot0_policy_requires_the_whole_4mib_source(self) -> None:
        entry = self.fx.add(
            "boot0",
            "boot1",
            2 * BOOT_AREA,
            source_bytes=BOOT_AREA,
            policies=("sector0_last", "readback_verify", "full_boot0"),
        )
        with self.assertRaisesRegex(GuardError, "full_boot0 source must cover"):
            load_manifest(self.fx.manifest([entry]))

    def test_full_boot0_policy_only_on_boot0(self) -> None:
        entry = self.fx.add("boot1", "boot2", BOOT_AREA, policies=("never_write", "full_boot0"))
        with self.assertRaisesRegex(GuardError, "full_boot0.*only valid on the boot0"):
            load_manifest(self.fx.manifest([entry]))

    def test_apply_four_writable_partitions_header_last(self) -> None:
        entries = self.fx.standard()
        entries.append(self.fx.add("expdb", "user", TEE_SIZE))
        entries.append(self.fx.add("gpt", "user", TEE_SIZE))
        manifest_path = self.fx.manifest(entries)
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        result = self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

        self.assertEqual(result["completed_items"], 5)
        self.assertEqual(result["total_items"], 5)
        self.assertEqual(
            [(name, offset, length) for name, _, offset, length in backend.write_calls],
            [
                ("boot0", SECTOR, BOOT_AREA - SECTOR),
                ("tee1", 0, TEE_SIZE),
                ("expdb", 0, TEE_SIZE),
                ("gpt", 0, TEE_SIZE),
                ("boot0", 0, SECTOR),
            ],
            "every writable partition is written and the boot header is written last",
        )
        written = [call[0] for call in backend.write_calls]
        self.assertEqual(sorted(set(written)), ["boot0", "expdb", "gpt", "tee1"])
        self.assertLess(
            written.index("expdb"),
            len(written) - 1,
            "expdb must land before boot0's sector-0 item",
        )
        self.assertEqual(
            backend.write_calls[-1],
            ("boot0", "boot1", 0, SECTOR),
            "sector 0 of BOOT0 must be the last write of the run",
        )
        self.assertEqual(
            backend.write_calls[0][2] + backend.write_calls[0][3],
            BOOT_AREA,
            "the boot0 body covers sector_bytes..partition_bytes",
        )
        for name, kind in (("boot0", "boot1"), ("tee1", "user"), ("expdb", "user"), ("gpt", "user")):
            self.assertEqual(self.fx.device_bytes(name, kind), self.fx.source_data[name])

    # -- dry-run ----------------------------------------------------------

    def test_dry_run_writes_nothing(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)

        before = {p: p.read_bytes() for p in self.fx.device.rglob("*.bin")}
        result = self.fx.apply(manifest_path, self.fx.root / "plan.json", backend, allow_write=False)
        self.assertTrue(result["dry_run"])
        self.assertEqual(backend.write_calls, [])
        self.assertFalse((self.fx.root / "restore.journal.jsonl").exists())
        self.assertFalse((self.fx.root / "restore.result.json").exists())
        after = {p: p.read_bytes() for p in self.fx.device.rglob("*.bin")}
        self.assertEqual(before, after)

    # -- static guards ----------------------------------------------------

    def test_identity_mismatch_refused(self) -> None:
        entries = self.fx.standard()
        wrong = dict(IDENTITY, hwcode="0x8163")
        manifest = load_manifest(self.fx.manifest(entries, device=wrong))
        with self.assertRaisesRegex(GuardError, "identity mismatch.*hwcode"):
            build_plan(manifest, self.fx.backend())

    def test_identity_override_fault_refused(self) -> None:
        manifest = load_manifest(self.fx.manifest(self.fx.standard()))
        faults = Faults(identity_override=dict(IDENTITY, flash_bytes=FLASH + 1))
        with self.assertRaisesRegex(GuardError, "identity mismatch.*flash_bytes"):
            build_plan(manifest, self.fx.backend(faults))

    def test_unknown_partition_refused(self) -> None:
        entry = self.fx.add("system_a", "user", TEE_SIZE)
        with self.assertRaisesRegex(GuardError, "unknown partition 'system_a'"):
            load_manifest(self.fx.manifest([entry]))

    def test_partition_missing_on_backend_refused(self) -> None:
        entries = [self.fx.add("tee1", "user", TEE_SIZE, on_device=False)]
        manifest = load_manifest(self.fx.manifest(entries))
        with self.assertRaisesRegex(GuardError, "unknown partition 'tee1'.*not present"):
            build_plan(manifest, self.fx.backend())

    def test_partition_size_mismatch_refused_at_planning(self) -> None:
        entry = self.fx.add("tee1", "user", TEE_SIZE)
        entry["partition_bytes"] = TEE_SIZE + SECTOR
        manifest = load_manifest(self.fx.manifest([entry]))
        backend = self.fx.backend()
        with self.assertRaisesRegex(
            GuardError,
            f"partition size mismatch for 'tee1'.*manifest says {TEE_SIZE + SECTOR} bytes, "
            f"backend reports {TEE_SIZE} bytes",
        ):
            build_plan(manifest, backend)
        self.assertEqual(backend.write_calls, [])

    def test_source_hash_mismatch_refused(self) -> None:
        entry = self.fx.add("tee1", "user", TEE_SIZE)
        entry["sha256"] = "0" * 64
        with self.assertRaisesRegex(GuardError, "source hash mismatch"):
            load_manifest(self.fx.manifest([entry]))

    def test_source_size_mismatch_refused(self) -> None:
        entry = self.fx.add("tee1", "user", TEE_SIZE, source_bytes=TEE_SIZE - 1)
        entry["source_bytes"] = TEE_SIZE
        with self.assertRaisesRegex(GuardError, "source size mismatch"):
            load_manifest(self.fx.manifest([entry]))

    def test_partition_too_small_refused(self) -> None:
        entry = self.fx.add("tee1", "user", TEE_SIZE // 2, source_bytes=TEE_SIZE)
        with self.assertRaisesRegex(GuardError, "too small"):
            load_manifest(self.fx.manifest([entry]))

    def test_entry_offset_must_be_sector_aligned(self) -> None:
        entry = self.fx.add("gpt", "user", TEE_SIZE, source_bytes=SECTOR)
        entry["offset"] = SECTOR // 2
        with self.assertRaisesRegex(GuardError, "not a multiple of the 512-byte sector"):
            load_manifest(self.fx.manifest([entry]))

    def test_entry_offset_plus_source_must_fit(self) -> None:
        entry = self.fx.add("gpt", "user", TEE_SIZE, source_bytes=SECTOR)
        entry["offset"] = TEE_SIZE
        with self.assertRaisesRegex(GuardError, "too small for its extent"):
            load_manifest(self.fx.manifest([entry]))

    def test_boot_area_entry_requires_zero_offset(self) -> None:
        entry = self.fx.add(
            "boot0",
            "boot1",
            BOOT_AREA,
            source_bytes=BOOT_AREA - 2 * SECTOR,
            policies=("sector0_last", "readback_verify"),
        )
        entry["offset"] = SECTOR
        with self.assertRaisesRegex(GuardError, "must start at offset 0"):
            load_manifest(self.fx.manifest([entry]))

    def test_offset_entry_writes_and_verifies_at_that_offset(self) -> None:
        entry = self.fx.add("gpt", "user", TEE_SIZE, source_bytes=SECTOR)
        entry["offset"] = 2 * SECTOR
        manifest_path = self.fx.manifest([entry])
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        self.assertEqual(plan["items"][0]["offset"], 2 * SECTOR)
        plan_path = self.fx.root / "plan.json"
        write_plan(plan_path, plan)
        self.fx.apply(manifest_path, plan_path, backend)
        device = self.fx.device_bytes("gpt", "user")
        self.assertEqual(device[2 * SECTOR : 3 * SECTOR], self.fx.source_data["gpt"])
        self.assertTrue(verify_manifest(manifest, backend)["ok"])

    # -- BOOT0 and expdb guards ------------------------------------------

    def test_boot0_must_not_span_boot_area_two(self) -> None:
        entry = self.fx.add(
            "boot0",
            "boot1",
            BOOT_AREA * 2,
            source_bytes=BOOT_AREA * 2,
            policies=("sector0_last", "readback_verify"),
        )
        with self.assertRaisesRegex(GuardError, "boot_area_bytes"):
            load_manifest(self.fx.manifest([entry]))

    def test_writable_boot0_requires_sector0_last(self) -> None:
        entry = self.fx.add(
            "boot0",
            "boot1",
            BOOT_AREA,
            policies=("readback_verify",),
        )
        with self.assertRaisesRegex(GuardError, "must carry 'sector0_last'"):
            load_manifest(self.fx.manifest([entry]))

    def test_boot_area_two_requires_never_write(self) -> None:
        entry = self.fx.add("boot1", "boot2", BOOT_AREA, policies=("readback_verify",))
        with self.assertRaisesRegex(GuardError, "identity store.*never_write"):
            load_manifest(self.fx.manifest([entry]))

    def test_fastboot_marker_in_misc_refused(self) -> None:
        payload = b"\x00" * 64 + b"FASTBOOT_PLEASE" + b"\x00" * (TEE_SIZE - 79)
        entry = self.fx.add("misc", "user", TEE_SIZE, data=payload)
        with self.assertRaisesRegex(GuardError, "ASCII marker"):
            load_manifest(self.fx.manifest([entry]))

    def test_fastboot_marker_in_expdb_refused(self) -> None:
        payload = b"\x00" * 64 + b"FASTBOOT_PLEASE" + b"\x00" * (TEE_SIZE - 79)
        entry = self.fx.add("expdb", "user", TEE_SIZE, data=payload)
        with self.assertRaisesRegex(GuardError, "ASCII marker"):
            load_manifest(self.fx.manifest([entry]))

    def test_expdb_write_after_chain_installed_refused(self) -> None:
        entry = self.fx.add("expdb", "user", TEE_SIZE)
        with self.assertRaisesRegex(GuardError, "refusing to write expdb"):
            load_manifest(self.fx.manifest([entry], chain_installed=True))

    def test_expdb_verify_only_allowed_after_chain_installed(self) -> None:
        payload = blob("expdb-stock", TEE_SIZE)
        entry = self.fx.add(
            "expdb",
            "user",
            TEE_SIZE,
            policies=("never_write",),
            data=payload,
            device_data=payload,
        )
        manifest = load_manifest(self.fx.manifest([entry], chain_installed=True))
        backend = self.fx.backend()
        self.assertEqual(build_plan(manifest, backend)["items"], [])
        self.assertTrue(verify_manifest(manifest, backend)["ok"])

    # -- readback and interruption ---------------------------------------

    def test_readback_mismatch_aborts_and_reports(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend(Faults(corrupt_readback={"boot0"}))
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)

        with self.assertRaisesRegex(ReadbackError, "readback mismatch for 'boot0'"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

        self.assertEqual(
            self.fx.device_bytes("tee1", "user"),
            blob("device:tee1", TEE_SIZE),
            "a failed readback must abort before the next partition",
        )
        self.assertEqual(
            self.fx.device_bytes("boot0", "boot1")[:SECTOR],
            blob("device:boot0", BOOT_AREA)[:SECTOR],
            "sector 0 must stay untouched after a failed readback",
        )
        journal_lines = (self.fx.root / "restore.journal.jsonl").read_text().splitlines()
        self.assertEqual(len(journal_lines), 1, "a failed write is never journaled")
        result_doc = json.loads((self.fx.root / "restore.result.json").read_text())
        self.assertEqual(result_doc["status"], "failed")
        self.assertIn("boot0", result_doc["error"])

    def test_reconnect_allows_further_operations(self) -> None:
        self.fx.add("tee1", "user", TEE_SIZE)
        backend = self.fx.backend(Faults(disconnect_after_ops=1))
        with self.assertRaisesRegex(BackendError, "injected disconnect"):
            backend.read("tee1", "user", 0, 16)
        backend.reconnect()
        self.assertEqual(len(backend.read("tee1", "user", 0, 16)), 16)

    def test_short_read_aborts(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend(Faults(short_read_partition="boot0"))
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        with self.assertRaises(ReadbackError):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)
        self.assertEqual(
            (self.fx.root / "restore.journal.jsonl").read_text().splitlines()[1:], []
        )

    def test_failure_mid_boot0_leaves_sector_zero_unchanged(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        original = self.fx.device_bytes("boot0", "boot1")
        backend = self.fx.backend(Faults(fail_after_bytes=600))
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)

        with self.assertRaisesRegex(BackendError, "injected write failure"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

        current = self.fx.device_bytes("boot0", "boot1")
        self.assertEqual(current[:SECTOR], original[:SECTOR])
        self.assertNotEqual(current[SECTOR : SECTOR + 600], original[SECTOR : SECTOR + 600])
        self.assertEqual(
            (self.fx.root / "restore.journal.jsonl").read_text().splitlines()[1:], []
        )
        result_doc = json.loads((self.fx.root / "restore.result.json").read_text())
        self.assertEqual(result_doc["status"], "failed")

    # -- resume -----------------------------------------------------------

    def test_resume_after_interruption(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        first = self.fx.backend(Faults(disconnect_after_ops=3))
        plan = build_plan(manifest, first)
        write_plan(self.fx.root / "plan.json", plan)

        with self.assertRaisesRegex(BackendError, "injected disconnect"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", first)
        journal_lines = (self.fx.root / "restore.journal.jsonl").read_text().splitlines()
        self.assertEqual(len(journal_lines), 2)  # header + body write

        second = self.fx.backend()
        result = self.fx.apply(manifest_path, self.fx.root / "plan.json", second, resume=True)
        self.assertEqual(result["completed_items"], 3)
        self.assertEqual(
            [(name, offset) for name, _, offset, _ in second.write_calls],
            [("tee1", 0), ("boot0", 0)],
            "resume must not rewrite the already-verified body",
        )
        self.assertEqual(self.fx.device_bytes("boot0", "boot1"), self.fx.source_data["boot0"])
        self.assertEqual(len((self.fx.root / "restore.journal.jsonl").read_text().splitlines()), 4)

    def test_empty_journal_is_treated_as_absent(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        plan_path = self.fx.root / "plan.json"
        plan = build_plan(load_manifest(manifest_path), self.fx.backend())
        write_plan(plan_path, plan)
        (self.fx.root / "restore.journal.jsonl").write_bytes(b"")

        result = self.fx.apply(manifest_path, plan_path, self.fx.backend())
        self.assertEqual(result["completed_items"], 3)

    def test_resume_refuses_corrupted_journal(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        first = self.fx.backend(Faults(disconnect_after_ops=3))
        plan = build_plan(manifest, first)
        write_plan(self.fx.root / "plan.json", plan)
        with self.assertRaises(BackendError):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", first)

        journal = self.fx.root / "restore.journal.jsonl"
        lines = journal.read_text().splitlines()
        record = json.loads(lines[1])
        record["partition"] = "tee1"
        lines[1] = json.dumps(record)
        journal.write_text("\n".join(lines) + "\n")

        with self.assertRaisesRegex(JournalError, "does not match plan item"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", self.fx.backend(), resume=True)

    def test_resume_refuses_truncated_journal(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        first = self.fx.backend(Faults(disconnect_after_ops=3))
        plan = build_plan(manifest, first)
        write_plan(self.fx.root / "plan.json", plan)
        with self.assertRaises(BackendError):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", first)

        journal = self.fx.root / "restore.journal.jsonl"
        journal.write_bytes(journal.read_bytes().rstrip(b"\n") + b'{"type":"op"')
        with self.assertRaisesRegex(JournalError, "partial line"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", self.fx.backend(), resume=True)

    def test_existing_journal_requires_resume(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)
        with self.assertRaisesRegex(JournalError, "already exists"):
            self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

    # -- atomicity and editing -------------------------------------------

    def test_manifest_write_is_atomic(self) -> None:
        target = self.fx.root / "atomic.json"
        target.write_text('{"old": true}\n')

        with self.assertRaises(TypeError):
            atomic_write_json(target, {"bad": object()})

        self.assertEqual(target.read_text(), '{"old": true}\n')
        self.assertEqual(list(self.fx.root.glob("atomic.json.*.tmp")), [])

        atomic_write_json(target, {"new": True})
        self.assertEqual(json.loads(target.read_text()), {"new": True})

    def test_manifest_write_survives_rename_failure(self) -> None:
        target = self.fx.root / "atomic.json"
        target.write_text('{"old": true}\n')
        with mock.patch("lidarrestore.atomic.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                atomic_write_json(target, {"new": True})
        self.assertEqual(target.read_text(), '{"old": true}\n')
        self.assertEqual(list(self.fx.root.glob("atomic.json.*.tmp")), [])

    def test_edited_plan_refused(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        plan_path = self.fx.root / "plan.json"
        write_plan(plan_path, build_plan(manifest, self.fx.backend()))
        doc = json.loads(plan_path.read_text())
        doc["items"][1]["offset"] = SECTOR * 2
        plan_path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ManifestError, "plan hash does not match"):
            load_plan(plan_path)

    def test_plan_for_other_manifest_refused(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        plan = build_plan(manifest, self.fx.backend())
        write_plan(self.fx.root / "plan.json", plan)

        other_entries = self.fx.standard()
        # Rebuild a different source of the same length to change the manifest hash.
        (self.fx.sources / "tee1.bin").write_bytes(blob("different", TEE_SIZE))
        other_entries[2]["sha256"] = hashlib.sha256(blob("different", TEE_SIZE)).hexdigest()
        other_path = self.fx.root / "manifest2.json"
        other_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "device": self.fx.identity,
                    "partitions": other_entries,
                }
            )
        )
        with self.assertRaisesRegex(GuardError, "different manifest"):
            self.fx.apply(other_path, self.fx.root / "plan.json", self.fx.backend(), allow_write=False)

    # -- verify -----------------------------------------------------------

    def test_verify_is_idempotent_and_read_only(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)

        first = verify_manifest(manifest, backend)
        second = verify_manifest(manifest, backend)
        self.assertTrue(first["ok"])
        self.assertEqual(first, second)
        self.assertEqual(len(backend.write_calls), 3, "verify must not write")

    def test_verify_detects_changed_partition(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        (self.fx.device / "user" / "tee1.bin").write_bytes(blob("changed", TEE_SIZE))
        report = verify_manifest(manifest, self.fx.backend())
        self.assertFalse(report["ok"])
        tee = [entry for entry in report["partitions"] if entry["name"] == "tee1"][0]
        self.assertFalse(tee["ok"])

    # -- CLI --------------------------------------------------------------

    def test_cli_plan_and_dry_run_apply(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        plan_path = self.fx.root / "plan.json"
        journal = self.fx.root / "journal.jsonl"
        base = [
            "--backend",
            "synthetic",
            "--root",
            str(self.fx.device),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli_main(["plan", "--manifest", str(manifest_path), "--out", str(plan_path)] + base),
                0,
            )
            self.assertEqual(
                cli_main(
                    [
                        "apply",
                        "--manifest",
                        str(manifest_path),
                        "--plan",
                        str(plan_path),
                        "--journal",
                        str(journal),
                    ]
                    + base
                ),
                0,
            )
        self.assertTrue(plan_path.is_file())
        self.assertFalse(journal.exists())
        self.assertEqual(
            self.fx.device_bytes("boot0", "boot1"), blob("device:boot0", BOOT_AREA)
        )

    def test_cli_verify_exit_codes(self) -> None:
        manifest_path = self.fx.manifest(self.fx.standard())
        manifest = load_manifest(manifest_path)
        backend = self.fx.backend()
        plan = build_plan(manifest, backend)
        write_plan(self.fx.root / "plan.json", plan)
        self.fx.apply(manifest_path, self.fx.root / "plan.json", backend)
        args = [
            "verify",
            "--manifest",
            str(manifest_path),
            "--report",
            str(self.fx.root / "report.json"),
            "--backend",
            "synthetic",
            "--root",
            str(self.fx.device),
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli_main(args), 0)
        self.assertTrue(json.loads((self.fx.root / "report.json").read_text())["ok"])

        (self.fx.device / "user" / "tee1.bin").write_bytes(blob("changed", TEE_SIZE))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli_main(args), 1)


class MtkclientAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="lidar-mtk-test-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.mtk_root = self.root / "mtkclient"
        self.mtk_root.mkdir()
        (self.mtk_root / "mtk.py").write_text("# stand-in\n")
        self.identity = {
            **IDENTITY,
            "partitions": ["boot0", "boot1", "gpt", "tee1", "expdb", "misc"],
        }

    def backend(
        self,
        runner=None,
        allow_device_read: bool = False,
        allow_device_write: bool = False,
        partition_offsets=None,
    ) -> MtkclientBackend:
        return MtkclientBackend(
            mtkclient_root=self.mtk_root,
            python_executable=Path(sys.executable),
            identity=self.identity,
            allow_device_read=allow_device_read,
            allow_device_write=allow_device_write,
            partition_offsets=partition_offsets,
            known_names=self.identity["partitions"],
            runner=runner,
        )

    def test_identity_from_captured_file(self) -> None:
        backend = self.backend()
        identity = backend.identity()
        self.assertEqual(identity.hwcode, 0x8167)
        self.assertEqual(identity.boot_area_bytes, BOOT_AREA)
        self.assertTrue(backend.known("tee1", "user"))
        self.assertFalse(backend.known("system_a", "user"))

    def test_boot_areas_and_pseudo_names_skip_the_gpt_list(self) -> None:
        backend = MtkclientBackend(
            mtkclient_root=self.mtk_root,
            python_executable=Path(sys.executable),
            identity=self.identity,
            partition_offsets={"gpt_backup": 0},
            known_names=["tee1"],
        )
        self.assertTrue(backend.known("boot0", "boot1"))
        self.assertTrue(backend.known("boot1", "boot2"))
        self.assertTrue(backend.known("gpt_backup", "user"))
        self.assertTrue(backend.known("tee1", "user"))
        self.assertFalse(backend.known("expdb", "user"))

    def test_write_is_refused_without_device_write_flag(self) -> None:
        with self.assertRaises(BackendWriteRefused):
            self.backend().write("tee1", "user", 0, b"\x00" * SECTOR)

    def test_device_reads_require_explicit_flag(self) -> None:
        with self.assertRaisesRegex(BackendError, "device reads are disabled"):
            self.backend().read("tee1", "user", 0, 16)

    def test_user_read_uses_partition_relative_offset(self) -> None:
        class FakeRunner:
            def __init__(self) -> None:
                self.calls = []

            def __call__(self, cmd, **kwargs):
                self.calls.append((cmd, kwargs))
                Path(cmd[4]).write_bytes(blob("mtk", 0x400))
                return subprocess.CompletedProcess(cmd, 0, "", "")

        runner = FakeRunner()
        backend = self.backend(runner=runner, allow_device_read=True)
        data = backend.read("tee1", "user", 0x200, 0x400)
        self.assertEqual(data, blob("mtk", 0x400))
        cmd, kwargs = runner.calls[0]
        self.assertEqual(
            cmd,
            [
                sys.executable,
                str(self.mtk_root / "mtk.py"),
                "r",
                "tee1",
                cmd[4],
                "--offset",
                "0x200",
                "--length",
                "0x400",
            ],
        )
        self.assertTrue(Path(kwargs["cwd"]).name.startswith("lidar-restore-"))
        self.assertNotEqual(Path(kwargs["cwd"]), self.mtk_root)

    def test_mtkclient_workdir_is_shared_across_invocations(self) -> None:
        # mtkclient only rejoins its resident DA when .state sits in the
        # working directory, so every command of one hardware session must
        # run in the same caller-chosen directory.
        class CwdRunner:
            def __init__(self) -> None:
                self.cwds: list[Path] = []

            def __call__(self, cmd, **kwargs):
                self.cwds.append(Path(kwargs["cwd"]))
                if cmd[2] in {"r", "ro"}:
                    Path(cmd[4] if cmd[2] == "r" else cmd[5]).write_bytes(blob("mtk", 0x400))
                return subprocess.CompletedProcess(cmd, 0, "", "")

        workdir = self.root / "mtk-session"
        workdir.mkdir()
        runner = CwdRunner()
        backend = MtkclientBackend(
            mtkclient_root=self.mtk_root,
            python_executable=Path(sys.executable),
            identity=self.identity,
            allow_device_write=True,
            known_names=self.identity["partitions"],
            runner=runner,
            mtkclient_workdir=workdir,
        )
        backend.read("tee1", "user", 0, 0x400)
        backend.write("tee1", "user", 0, blob("tee1", SECTOR))
        self.assertEqual(len(runner.cwds), 2)
        self.assertEqual({path.resolve() for path in runner.cwds}, {workdir.resolve()})
        # The session state must outlive each invocation, not just the batch.
        self.assertTrue(workdir.is_dir())

    def test_pseudo_partition_read_uses_absolute_ro(self) -> None:
        runner = RecordingRunner(readback=blob("gpt", 0x200))
        backend = self.backend(
            runner=runner, allow_device_read=True, partition_offsets={"gpt": 0}
        )
        data = backend.read("gpt", "user", 0x4000, 0x200)
        self.assertEqual(data, blob("gpt", 0x200))
        self.assertEqual(
            runner.calls[0][2:],
            ["ro", "0x4000", "0x200", runner.calls[0][5]],
        )

    def test_boot_area_read_uses_parttype_and_slices(self) -> None:
        class FakeRunner:
            def __init__(self) -> None:
                self.calls = []

            def __call__(self, cmd, **kwargs):
                self.calls.append((cmd, kwargs))
                Path(cmd[4]).write_bytes(blob("area1", BOOT_AREA))
                return subprocess.CompletedProcess(cmd, 0, "", "")

        runner = FakeRunner()
        backend = self.backend(runner=runner, allow_device_read=True)
        expected = blob("area1", BOOT_AREA)
        self.assertEqual(backend.read("boot0", "boot1", SECTOR, SECTOR), expected[SECTOR : 2 * SECTOR])
        cmd, _ = runner.calls[0]
        self.assertEqual(cmd[2:], ["r", "boot0", cmd[4], "--parttype", "boot1"])

    def test_command_failure_is_reported(self) -> None:
        class FailingRunner:
            def __call__(self, cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 1, "Error: Couldn't detect partition", "")

        backend = self.backend(runner=FailingRunner(), allow_device_read=True)
        with self.assertRaisesRegex(BackendError, "mtkclient command failed"):
            backend.read("tee1", "user", 0, 16)

    def test_user_write_uses_partition_name_at_offset_zero(self) -> None:
        runner = RecordingRunner()
        backend = self.backend(runner=runner, allow_device_write=True)
        data = blob("tee1", TEE_SIZE)
        backend.write("tee1", "user", 0, data)
        cmd = runner.calls[0]
        self.assertEqual(cmd[2:4], ["w", "tee1"])
        self.assertEqual(runner.written[0], data)

    def test_boot_area_write_uses_wo_and_area_offset(self) -> None:
        runner = RecordingRunner()
        backend = self.backend(runner=runner, allow_device_write=True)
        body = blob("boot0", BOOT_AREA - SECTOR)
        backend.write("boot0", "boot1", SECTOR, body)
        cmd = runner.calls[0]
        self.assertEqual(cmd[2:5], ["wo", hex(SECTOR), hex(len(body))])
        self.assertEqual(runner.written[0], body)
        self.assertEqual(cmd[6:], ["--parttype", "boot1"])

    def test_write_at_nonzero_offset_needs_partition_offsets(self) -> None:
        backend = self.backend(runner=RecordingRunner(), allow_device_write=True)
        with self.assertRaisesRegex(BackendError, "no base address"):
            backend.write("gpt", "user", SECTOR, blob("gpt", SECTOR))

        runner = RecordingRunner()
        backend = self.backend(
            runner=runner, allow_device_write=True, partition_offsets={"gpt": 0}
        )
        backend.write("gpt", "user", 0x4000, blob("gpt", SECTOR))
        self.assertEqual(runner.calls[0][2:5], ["wo", "0x4000", hex(SECTOR)])

        # A pseudo name is always addressed absolutely, even at offset 0.
        backend.write("gpt", "user", 0, blob("gpt", SECTOR))
        self.assertEqual(runner.calls[1][2:5], ["wo", "0x0", hex(SECTOR)])

    def test_apply_drills_gpt_extents_over_mtkclient(self) -> None:
        fx = Fixture(self)
        primary = fx.add("gpt", "user", FLASH, source_bytes=0x4200)
        backup = fx.add("gpt_backup", "user", FLASH, source_bytes=0x4200)
        backup["offset"] = 0x80000
        manifest = load_manifest(fx.manifest([primary, backup]))
        device = FakeDevice(
            boot1=blob("boot", BOOT_AREA), boot2=blob("boot2", BOOT_AREA), user=blob("user", FLASH), parts={}
        )
        backend = self.backend(
            runner=device,
            allow_device_write=True,
            partition_offsets={"gpt": 0, "gpt_backup": 0},
        )
        plan = build_plan(manifest, backend)
        result = apply_plan(
            manifest, plan, backend, journal_path=fx.root / "journal.jsonl", allow_write=True
        )
        self.assertEqual(result["completed_items"], len(plan["items"]))
        self.assertEqual(bytes(device.user[:0x4200]), fx.source_data["gpt"])
        self.assertEqual(
            bytes(device.user[0x80000 : 0x80000 + 0x4200]), fx.source_data["gpt_backup"]
        )

    def test_write_refuses_boot_area_two(self) -> None:
        backend = self.backend(runner=RecordingRunner(), allow_device_write=True)
        with self.assertRaisesRegex(BackendWriteRefused, "boot area 2"):
            backend.write("boot1", "boot2", 0, blob("boot1", SECTOR))

    def test_full_boot0_authorizes_boot_area_two_write(self) -> None:
        runner = RecordingRunner()
        backend = self.backend(runner=runner, allow_device_write=True)
        backend.write("boot1", "boot2", 0, blob("boot1", SECTOR), boot_area_2_write=True)
        self.assertEqual(runner.calls[0][2:4], ["wo", "0x0"])
        self.assertEqual(runner.calls[0][-2:], ["--parttype", "boot2"])

    def test_write_refuses_unaligned_extents(self) -> None:
        backend = self.backend(runner=RecordingRunner(), allow_device_write=True)
        with self.assertRaisesRegex(BackendError, "not 512-byte aligned"):
            backend.write("tee1", "user", 0, blob("tee1", SECTOR + 1))
        with self.assertRaisesRegex(BackendError, "not 512-byte aligned"):
            backend.write("boot0", "boot1", SECTOR // 2, blob("boot0", SECTOR))

    def test_write_failure_marker_is_reported(self) -> None:
        class FailingRunner:
            def __call__(self, cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, "Failed to write tee1 to sector 0x0", "")

        backend = self.backend(runner=FailingRunner(), allow_device_write=True)
        with self.assertRaisesRegex(BackendError, "mtkclient command failed"):
            backend.write("tee1", "user", 0, blob("tee1", SECTOR))

    def test_apply_writes_and_reads_back_through_mtkclient(self) -> None:
        fx = Fixture(self)
        manifest = load_manifest(fx.manifest(fx.standard()))
        device = FakeDevice(
            boot1=blob("device:boot0", BOOT_AREA),
            boot2=fx.source_data["boot1"],
            user=blob("user", FLASH),
            parts={"tee1": 0x20000},
        )
        backend = self.backend(runner=device, allow_device_write=True)
        plan = build_plan(manifest, backend)
        result = apply_plan(
            manifest,
            plan,
            backend,
            journal_path=fx.root / "journal.jsonl",
            allow_write=True,
        )
        self.assertEqual(result["completed_items"], len(plan["items"]))
        self.assertEqual(bytes(device.boot["boot1"]), fx.source_data["boot0"])
        self.assertEqual(bytes(device.boot["boot2"]), fx.source_data["boot1"])
        tee = bytes(device.user[0x20000 : 0x20000 + TEE_SIZE])
        self.assertEqual(tee, fx.source_data["tee1"])
        self.assertEqual(
            [call[2] for call in device.calls if call[2] in {"w", "wo"}],
            ["wo", "w", "wo"],
        )

    def test_apply_with_allow_write_refuses_without_device_write_flag(self) -> None:
        fx = Fixture(self)
        manifest = load_manifest(fx.manifest(fx.standard()))
        backend = self.backend(runner=RecordingRunner())
        plan = build_plan(manifest, backend)
        with self.assertRaises(BackendWriteRefused):
            apply_plan(
                manifest,
                plan,
                backend,
                journal_path=fx.root / "journal.jsonl",
                allow_write=True,
            )

    def test_printgpt_identity_parsing(self) -> None:
        sample = (
            "Preloader - HW code:\t\t\t0x8167\n"
            "DAXFlash - EMMC Boot1 Size: 0x200000\n"
            "DAXFlash - EMMC USER Size:  0x1c8000000\n"
            "Total disk size:0x00000001c8000000, sectors:0x0000000000e40000\n"
        )
        identity = parse_printgpt_identity(sample)
        self.assertEqual(identity.hwcode, 0x8167)
        self.assertEqual(identity.boot_area_bytes, 0x200000)
        self.assertEqual(identity.flash_bytes, 0x1C8000000)
        self.assertEqual(identity.sector_bytes, 512)

    def test_live_identity_uses_printgpt_command(self) -> None:
        class FakeRunner:
            def __init__(self) -> None:
                self.calls = []

            def __call__(self, cmd, **kwargs):
                self.calls.append(cmd)
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    (
                        "Preloader - HW code:\t\t\t0x8167\n"
                        "DAXFlash - EMMC Boot1 Size: 0x200000\n"
                        "DAXFlash - EMMC USER Size:  0x1c8000000\n"
                        "Total disk size:0x00000001c8000000, sectors:0x0000000000e40000\n"
                    ),
                    "",
                )

        runner = FakeRunner()
        backend = MtkclientBackend(
            mtkclient_root=self.mtk_root,
            python_executable=Path(sys.executable),
            allow_device_read=True,
            runner=runner,
        )
        identity = backend.identity()
        self.assertEqual(identity.sector_bytes, 512)
        self.assertEqual(runner.calls[0][2:], ["printgpt"])


if __name__ == "__main__":
    unittest.main()
