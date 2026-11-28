"""Device backends.

Two backends exist:

* SyntheticBackend operates on a directory of partition image files. It
  supports fault injection so the host tests can exercise partial writes, short
  reads, corrupt readback, disconnects, and wrong identity.
* MtkclientBackend shells out to the owner's mtkclient checkout. Reads run
  whenever device reads are enabled; writes need the separate
  allow_device_write flag, which the CLI sets only with --allow-device-write.
  The exact mtkclient commands are documented in README.md and derived from the
  checkout under mtkclient/.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .errors import BackendError, BackendWriteRefused
from .manifest import DeviceIdentity

# The workspace tools checkout; --mtkclient-root overrides.
DEFAULT_MTKCLIENT_ROOT = Path(__file__).resolve().parents[4] / "tools/mtkclient"


@dataclass
class Faults:
    """Synthetic backend fault injection.

    fail_after_bytes: write only that many bytes of the next write, then fail.
    short_read_partition: return one byte less on the next read of this name.
    corrupt_readback: flip one byte on the next read of these names.
    disconnect_after_ops: fail the Nth backend operation and every later one
        until reconnect() is called.
    identity_override: replace the identity reported by the backend.
    """

    fail_after_bytes: int | None = None
    short_read_partition: str | None = None
    corrupt_readback: set[str] = field(default_factory=set)
    disconnect_after_ops: int | None = None
    identity_override: dict[str, Any] | None = None


FAULT_FIELDS = {f.name for f in dataclasses.fields(Faults)}


def faults_from_dict(obj: Mapping[str, Any]) -> Faults:
    if not isinstance(obj, Mapping):
        raise BackendError("fault injection configuration must be a JSON object")
    unknown = set(obj) - FAULT_FIELDS
    if unknown:
        raise BackendError(f"unknown fault injection fields {sorted(unknown)}")
    data = dict(obj)
    numeric = ("fail_after_bytes", "disconnect_after_ops")
    for field in numeric:
        value = data.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise BackendError(f"fault {field} must be a non-negative integer or null")
    if data.get("short_read_partition") is not None and not isinstance(
        data["short_read_partition"], str
    ):
        raise BackendError("fault short_read_partition must be a partition name or null")
    if "corrupt_readback" in data:
        value = data["corrupt_readback"]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise BackendError("corrupt_readback must be a list of partition names")
        data["corrupt_readback"] = set(value)
    return Faults(**data)


class Backend:
    """Minimal contract shared by the synthetic and mtkclient backends."""

    name = "abstract"
    writable = False

    def describe(self) -> str:
        raise NotImplementedError

    def identity(self) -> DeviceIdentity:
        raise NotImplementedError

    def known(self, name: str, kind: str) -> bool:
        raise NotImplementedError

    def capacity(self, name: str, kind: str) -> int | None:
        """Actual partition size in bytes, or None when the backend cannot report it."""
        return None

    def read(self, name: str, kind: str, offset: int, length: int) -> bytes:
        raise NotImplementedError

    def write(
        self,
        name: str,
        kind: str,
        offset: int,
        data: bytes,
        boot_area_2_write: bool = False,
    ) -> None:
        raise NotImplementedError

    def reconnect(self) -> None:
        """Restore a disconnected backend. No-op unless a fault cut it."""


class SyntheticBackend(Backend):
    """Partition-image directory backend with deterministic fault injection.

    Files live at <root>/<kind>/<name>.bin. The identity is read from
    <root>/identity.json unless an override is supplied. Device files must
    already exist: a restore tool overwrites partitions, it does not create
    them.
    """

    name = "synthetic"
    writable = True

    def __init__(self, root: Path, faults: Faults | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise BackendError(f"synthetic backend root {self.root} is not a directory")
        self.faults = faults or Faults()
        self.write_calls: list[tuple[str, str, int, int]] = []
        self.read_calls: list[tuple[str, str, int, int]] = []
        self._ops = 0
        self._disconnected = False
        self._identity: DeviceIdentity | None = None

    def describe(self) -> str:
        return f"synthetic:{self.root}"

    def identity(self) -> DeviceIdentity:
        if self.faults.identity_override is not None:
            return DeviceIdentity.from_dict(self.faults.identity_override, "identity_override")
        if self._identity is None:
            path = self.root / "identity.json"
            try:
                doc = json.loads(path.read_bytes())
            except OSError as exc:
                raise BackendError(f"cannot read synthetic identity {path}: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise BackendError(f"synthetic identity {path} is not valid JSON: {exc}") from exc
            self._identity = DeviceIdentity.from_dict(doc, "identity.json")
        return self._identity

    def _path(self, name: str, kind: str) -> Path:
        if kind not in {"boot1", "boot2", "user"}:
            raise BackendError(f"invalid partition kind {kind!r}")
        return self.root / kind / f"{name}.bin"

    def known(self, name: str, kind: str) -> bool:
        return self._path(name, kind).is_file()

    def capacity(self, name: str, kind: str) -> int | None:
        path = self._path(name, kind)
        if not path.is_file():
            raise BackendError(f"unknown partition {name!r} on synthetic backend")
        return path.stat().st_size

    def _begin_op(self) -> None:
        if self._disconnected:
            raise BackendError("backend is disconnected; call reconnect()")
        self._ops += 1
        if self.faults.disconnect_after_ops == self._ops:
            self._disconnected = True
            raise BackendError(f"injected disconnect before operation {self._ops}")

    def read(self, name: str, kind: str, offset: int, length: int) -> bytes:
        self._begin_op()
        path = self._path(name, kind)
        if not path.is_file():
            raise BackendError(f"unknown partition {name!r} on synthetic backend")
        if offset < 0 or length < 0:
            raise BackendError("negative read offset or length")
        self.read_calls.append((name, kind, offset, length))
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
        if len(data) != length:
            raise BackendError(
                f"short read from {name!r}: wanted {length} bytes at 0x{offset:x}, got {len(data)}"
            )
        if self.faults.short_read_partition == name:
            self.faults.short_read_partition = None
            data = data[:-1]
        if name in self.faults.corrupt_readback:
            self.faults.corrupt_readback.discard(name)
            if data:
                data = bytes([data[0] ^ 0x01]) + data[1:]
        return data

    def write(
        self,
        name: str,
        kind: str,
        offset: int,
        data: bytes,
        boot_area_2_write: bool = False,
    ) -> None:
        self._begin_op()
        if kind == "boot2" and not boot_area_2_write:
            raise BackendWriteRefused(
                "boot area 2 is the identity store and is never writable without "
                "an explicit full_boot0 manifest entry"
            )
        path = self._path(name, kind)
        if not path.is_file():
            raise BackendError(f"unknown partition {name!r} on synthetic backend")
        size = path.stat().st_size
        if offset < 0 or offset + len(data) > size:
            raise BackendError(
                f"write to {name!r} at 0x{offset:x} with {len(data)} bytes exceeds the "
                f"{size}-byte partition"
            )
        self.write_calls.append((name, kind, offset, len(data)))
        fail_after = self.faults.fail_after_bytes
        if fail_after is not None and fail_after < len(data):
            # Simulate a write that dies part-way through. The bytes that did
            # land stay on disk, exactly like a real interrupted eMMC write.
            self.faults.fail_after_bytes = None
            with open(path, "r+b") as fh:
                fh.seek(offset)
                fh.write(data[:fail_after])
                fh.flush()
            raise BackendError(
                f"injected write failure after {fail_after} of {len(data)} bytes "
                f"for {name!r} at 0x{offset:x}"
            )
        with open(path, "r+b") as fh:
            fh.seek(offset)
            fh.write(data)
            fh.flush()

    def reconnect(self) -> None:
        self._disconnected = False


class MtkclientBackend(Backend):
    """Adapter over the owner's mtkclient checkout.

    Read commands:

      mtk.py printgpt
      mtk.py r <name> <file> --offset 0x<off> --length 0x<len>   (user area)
      mtk.py r <name> <file> --parttype boot1|boot2              (boot areas)

    Write commands, only with allow_device_write. That flag also enables reads,
    because every write is read back and compared; a write without readback
    could not be verified, so it is never offered:

      mtk.py w <name> <file>                                     (user area, slot 0)
      mtk.py wo 0x<abs> 0x<len> <file>                           (user area, absolute)
      mtk.py wo 0x<off> 0x<len> <file> --parttype boot1          (boot area 1)

    `w` resolves the partition through the device GPT, so a whole-partition
    write never carries a hand-computed address. `wo` takes an absolute
    user-area byte address, so a write at a nonzero offset needs that
    partition's base address from partition_offsets; `gpt` is the pseudo
    partition at address 0 and is the only such name the boot-chain set uses.

    Every write must be sector aligned. mtkclient silently zero-pads a short
    final sector, which would write bytes the plan never verified, so a
    misaligned item is refused here instead.

    mtk.py only rejoins its resident download agent when `.state` is in the
    working directory, and a failed rejoin starts over from the BROM handshake.
    Pass mtkclient_workdir to give plan, apply, and verify one directory for a
    hardware session; a fresh BROM session needs a new empty directory because
    a stale `.state` names a download agent that no longer exists. Without the
    option every command runs in a fresh temporary directory that is removed
    afterwards, so nothing is shared between invocations. In both modes the
    checkout stays clean, the caller's session directory is never deleted, and
    only the per-operation binary file is temporary.

    A captured GPT list carries partition names only, not sizes, so
    `capacity()` returns None and the planner's partition-size gate cannot run
    for this backend.
    """

    name = "mtkclient"

    def __init__(
        self,
        mtkclient_root: Path = DEFAULT_MTKCLIENT_ROOT,
        python_executable: Path | None = None,
        identity: Mapping[str, Any] | None = None,
        mtkclient_workdir: Path | None = None,
        allow_device_read: bool = False,
        allow_device_write: bool = False,
        partition_offsets: Mapping[str, int] | None = None,
        known_names: Sequence[str] | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
        timeout: int = 600,
    ) -> None:
        self.root = Path(mtkclient_root).resolve()
        self.mtk_py = self.root / "mtk.py"
        self.python = Path(python_executable) if python_executable else self.root / ".venv" / "bin" / "python"
        if not self.mtk_py.is_file():
            raise BackendError(f"mtkclient checkout not found at {self.mtk_py}")
        if not self.python.is_file():
            raise BackendError(f"mtkclient virtualenv python not found at {self.python}")
        self.workdir: Path | None = None
        if mtkclient_workdir is not None:
            workdir = Path(mtkclient_workdir).expanduser()
            if workdir.exists() and not workdir.is_dir():
                raise BackendError(f"mtkclient working directory is not a directory: {workdir}")
            try:
                workdir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise BackendError(
                    f"cannot create mtkclient working directory {workdir}: {exc}"
                ) from exc
            self.workdir = workdir.resolve()
        self.identity_doc = dict(identity) if identity is not None else None
        # A write is always read back and compared, so write access without
        # read access could only produce unverified writes.
        self.allow_device_read = allow_device_read or allow_device_write
        self.allow_device_write = allow_device_write
        self.writable = allow_device_write
        self.partition_offsets = {
            str(key): int(value) for key, value in (partition_offsets or {}).items()
        }
        self._identity_cache: DeviceIdentity | None = None
        if known_names is None and self.identity_doc is not None:
            listed = self.identity_doc.get("partitions")
            if isinstance(listed, list) and all(isinstance(item, str) for item in listed):
                known_names = listed
        self.known_names = set(known_names) if known_names is not None else None
        self.runner = runner
        self.timeout = timeout
        self.commands: list[list[str]] = []

    def describe(self) -> str:
        return f"mtkclient:{self.root}"

    def identity(self) -> DeviceIdentity:
        if self._identity_cache is not None:
            return self._identity_cache
        if self.identity_doc is not None:
            fields = {"hwcode", "flash_bytes", "boot_area_bytes", "sector_bytes"}
            self._identity_cache = DeviceIdentity.from_dict(
                {key: value for key, value in self.identity_doc.items() if key in fields},
                "identity",
            )
            return self._identity_cache
        if not self.allow_device_read:
            raise BackendError(
                "mtkclient identity is unavailable without a device read; pass an identity "
                "file or enable device reads"
            )
        with tempfile.TemporaryDirectory(prefix="lidar-restore-") as tmp:
            out = self._run([str(self.python), str(self.mtk_py), "printgpt"], cwd=self._cwd(tmp))
        self._identity_cache = parse_printgpt_identity(out.stdout or "")
        return self._identity_cache

    def known(self, name: str, kind: str) -> bool:
        # A captured GPT list covers user-area names only: boot areas are not
        # entries, and pseudo partitions are addressed by offset instead.
        if kind in {"boot1", "boot2"} or name in self.partition_offsets:
            return True
        if self.known_names is not None:
            return name in self.known_names
        # No captured GPT list: only the manifest's fixed boot-chain allowlist
        # applies, and the device itself rejects unknown names on read.
        return True

    def capacity(self, name: str, kind: str) -> int | None:
        """No size is available: a captured GPT list carries partition names only."""
        return None

    def read(self, name: str, kind: str, offset: int, length: int) -> bytes:
        if not self.allow_device_read:
            raise BackendError(
                "device reads are disabled; pass --allow-device-read to use the mtkclient backend"
            )
        if not self.known(name, kind):
            raise BackendError(f"unknown partition {name!r} for the mtkclient backend")
        if offset < 0 or length < 0:
            raise BackendError("negative read offset or length")
        with tempfile.TemporaryDirectory(prefix="lidar-restore-") as tmp:
            target = Path(tmp) / "read.bin"
            if kind in {"boot1", "boot2"}:
                # The boot path ignores offset and length and reads the whole
                # area, so the slice happens locally.
                cmd = [str(self.python), str(self.mtk_py), "r", name, str(target), "--parttype", kind]
            elif name in self.partition_offsets:
                # Pseudo partitions (gpt) are not in the GPT, and `r gpt`
                # ignores the offset; `ro` addresses the user area directly.
                base = self.partition_offsets[name]
                cmd = [
                    str(self.python),
                    str(self.mtk_py),
                    "ro",
                    hex(base + offset),
                    hex(length),
                    str(target),
                ]
            else:
                # `r` adds the partition start to this offset.
                cmd = [
                    str(self.python),
                    str(self.mtk_py),
                    "r",
                    name,
                    str(target),
                    "--offset",
                    hex(offset),
                    "--length",
                    hex(length),
                ]
            self._run(cmd, cwd=self._cwd(tmp))
            try:
                data = target.read_bytes()
            except OSError as exc:
                raise BackendError(f"mtkclient did not produce {target}: {exc}") from exc
        if kind in {"boot1", "boot2"}:
            # Only the boot path returns a whole area; the user-area commands
            # return exactly the requested extent.
            if len(data) < offset + length:
                raise BackendError(
                    f"short boot-area read from {name!r}: wanted {offset + length} bytes, "
                    f"got {len(data)}"
                )
            return data[offset : offset + length]
        if len(data) != length:
            raise BackendError(
                f"short read from {name!r}: wanted {length} bytes, got {len(data)}"
            )
        return data

    def write(
        self,
        name: str,
        kind: str,
        offset: int,
        data: bytes,
        boot_area_2_write: bool = False,
    ) -> None:
        if not self.allow_device_write:
            raise BackendWriteRefused(
                "the mtkclient backend is read-only unless --allow-device-write is set"
            )
        if kind == "boot2" and not boot_area_2_write:
            raise BackendWriteRefused(
                "boot area 2 is the identity store and is never writable without "
                "an explicit full_boot0 manifest entry"
            )
        if not self.known(name, kind):
            raise BackendError(f"unknown partition {name!r} for the mtkclient backend")
        if not data:
            raise BackendError("refusing an empty write")
        if offset < 0:
            raise BackendError("negative write offset")
        sector = self.identity().sector_bytes
        if offset % sector or len(data) % sector:
            raise BackendError(
                f"write to {name!r} at 0x{offset:x} ({len(data)} bytes) is not "
                f"{sector}-byte aligned; mtkclient would zero-pad the final sector with "
                "bytes this plan never verified"
            )
        with tempfile.TemporaryDirectory(prefix="lidar-restore-") as tmp:
            source = Path(tmp) / "write.bin"
            source.write_bytes(data)
            if kind in {"boot1", "boot2"}:
                # `wo` addresses boot areas from their own base, so the plan
                # offset is already the write address.
                cmd = [
                    str(self.python),
                    str(self.mtk_py),
                    "wo",
                    hex(offset),
                    hex(len(data)),
                    str(source),
                    "--parttype",
                    kind,
                ]
            elif offset == 0 and name not in self.partition_offsets:
                # `w` resolves the partition through the device GPT.
                cmd = [str(self.python), str(self.mtk_py), "w", name, str(source)]
            else:
                base = self.partition_offsets.get(name)
                if base is None:
                    raise BackendError(
                        f"partition {name!r} has no base address; pass it in --partition-offsets "
                        "to write at a nonzero offset"
                    )
                cmd = [
                    str(self.python),
                    str(self.mtk_py),
                    "wo",
                    hex(base + offset),
                    hex(len(data)),
                    str(source),
                ]
            self._run(cmd, cwd=self._cwd(tmp), failure_markers=("Failed to write", "Error on writeflash"))

    def _cwd(self, fallback: str) -> str:
        """The caller's session directory when configured, else a throwaway one."""
        return str(self.workdir) if self.workdir is not None else fallback

    def _run(
        self,
        cmd: list[str],
        cwd: str | None,
        failure_markers: Sequence[str] = ("Failed to dump",),
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(cmd))
        runner = self.runner or subprocess.run
        try:
            proc = runner(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except OSError as exc:
            raise BackendError(f"cannot run mtkclient: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"mtkclient timed out after {self.timeout}s") from exc
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        failed_marker = next((marker for marker in failure_markers if marker in stdout), None)
        if proc.returncode != 0 or failed_marker is not None:
            tail = (stdout + stderr).strip().splitlines()[-3:]
            raise BackendError(
                f"mtkclient command failed (exit {proc.returncode}): {' | '.join(tail)}"
            )
        return proc


_HWCODE_RE = re.compile(r"HW code:\s*(0x[0-9a-fA-F]+)")
_BOOT1_RE = re.compile(r"EMMC Boot1 Size:\s*(0x[0-9a-fA-F]+)")
_USER_RE = re.compile(r"EMMC USER Size:\s*(0x[0-9a-fA-F]+)")
_DISK_RE = re.compile(
    r"Total disk size:\s*(0x[0-9a-fA-F]+),\s*sectors:\s*(0x[0-9a-fA-F]+)"
)


def parse_printgpt_identity(text: str) -> DeviceIdentity:
    """Derive the identity block from a `mtk.py printgpt` transcript.

    mtkclient prints the BROM banner before the GPT table, so the transcript
    contains HW code and the eMMC geometry. Values are read-only observations;
    they are never persisted by the tool.
    """
    hwcode = _HWCODE_RE.search(text)
    boot1 = _BOOT1_RE.search(text)
    user = _USER_RE.search(text)
    disk = _DISK_RE.search(text)
    if not all((hwcode, boot1, user, disk)):
        missing = [
            label
            for label, match in (
                ("HW code", hwcode),
                ("EMMC Boot1 Size", boot1),
                ("EMMC USER Size", user),
                ("Total disk size/sectors", disk),
            )
            if match is None
        ]
        raise BackendError(f"printgpt output is missing {missing}; supply an identity file")
    total = int(disk.group(1), 16)
    sectors = int(disk.group(2), 16)
    if sectors == 0 or total % sectors:
        raise BackendError("printgpt total disk size is not divisible by its sector count")
    return DeviceIdentity(
        hwcode=int(hwcode.group(1), 16),
        flash_bytes=total,
        boot_area_bytes=int(boot1.group(1), 16),
        sector_bytes=total // sectors,
    )


def load_identity_file(path: Path) -> dict[str, Any]:
    """Load an identity JSON that may also list known GPT partition names."""
    try:
        doc = json.loads(Path(path).read_bytes())
    except OSError as exc:
        raise BackendError(f"cannot read identity file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BackendError(f"identity file {path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise BackendError("identity file must be a JSON object")
    if "partitions" in doc and not (
        isinstance(doc["partitions"], list)
        and all(isinstance(item, str) for item in doc["partitions"])
    ):
        raise BackendError("identity file 'partitions' must be a list of strings")
    return doc
