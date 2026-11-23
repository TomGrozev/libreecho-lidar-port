# Lidar boot-chain restore tool (experimental)

This directory holds the host tool for preparing and restoring the Echo Plus 2nd Gen
(MT8167, codename Lidar) boot chain. It is experimental. The `synthetic` backend writes
partition image files in a temporary directory. The `mtkclient` adapter reads a device and,
only when `--allow-device-write` is also passed, writes it. Without that flag every write
raises an error.

The tool does not replace the production installer. It exists to prove the identity, size, hash,
write-order, readback, and resume rules on the host before any device byte changes.

## Files

| Path | Purpose |
| --- | --- |
| `lidar_restore.py` | CLI entry point |
| `lidarrestore/manifest.py` | manifest schema and static guards |
| `lidarrestore/core.py` | plan construction, apply, verify |
| `lidarrestore/backends.py` | synthetic and mtkclient backends |
| `lidarrestore/journal.py` | append-only JSONL journal and resume validation |
| `lidarrestore/atomic.py` | temp-file, fsync, rename writes and hashing |
| `test_lidar_restore.py` | unittest suite, host only |

Run the tests from this directory:

```sh
python3 -m unittest -v
```

## Quick start

```sh
# Validate the manifest and write the ordered plan.
python3 lidar_restore.py plan \
    --manifest manifest.json \
    --out plan.json \
    --backend synthetic --root /tmp/synthetic-device

# Dry-run an existing plan. This validates everything and writes nothing.
python3 lidar_restore.py apply \
    --manifest manifest.json --plan plan.json --journal restore.journal.jsonl \
    --backend synthetic --root /tmp/synthetic-device

# Execute it against the synthetic backend.
python3 lidar_restore.py apply \
    --manifest manifest.json --plan plan.json --journal restore.journal.jsonl \
    --backend synthetic --root /tmp/synthetic-device --allow-write

# Read-only comparison of every partition source extent.
python3 lidar_restore.py verify \
    --manifest manifest.json --backend synthetic --root /tmp/synthetic-device
```

A device run adds the mtkclient flags. `--allow-write` alone is still a dry run; the write
needs both flags:

```sh
python3 lidar_restore.py apply \
    --manifest manifest.json --plan plan.json --journal restore.journal.jsonl \
    --backend mtkclient --identity-json identity.json \
    --partition-offsets offsets.json \
    --mtkclient-workdir /tmp/lidar-drill-mtkclient \
    --allow-device-read --allow-device-write --allow-write
```

## Manifest schema

The manifest is a JSON object. Schema version 1 is the only accepted version. Source paths are
relative to the manifest file unless they are absolute.

### Top level

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | Must be `1` |
| `device` | object | yes | target identity, compared with the backend |
| `chain_installed` | boolean | no | true after Kaeru is installed; blocks writable `expdb` |
| `partitions` | array | yes | non-empty list of partition entries |
| `description` | string | no | free text, not used by the tool |

### Device identity

| Field | Type | Meaning |
| --- | --- | --- |
| `hwcode` | integer or `0x` string | SoC hardware code, `0x8167` for this board |
| `flash_bytes` | integer | eMMC user area size in bytes |
| `boot_area_bytes` | integer | size of one eMMC boot area in bytes |
| `sector_bytes` | integer | logical sector size, 512 on this eMMC |

Every field must match the backend identity. A mismatch stops `plan`, `apply`, and `verify`.
The Phase 1 live read recorded `hwcode 0x8167`, boot areas of `0x200000` bytes, and a user area of
`0x1c8000000` bytes (`experiments/phase-01/brom-printgpt.log`).

### Partition entry

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | partition name, limited to the boot-chain set below |
| `kind` | string | `boot1` (boot area 1), `boot2` (boot area 2), or `user` |
| `partition_bytes` | integer | size of the target partition |
| `source` | string | local image path |
| `source_bytes` | integer | exact source file size |
| `sha256` | string | lowercase or uppercase SHA-256 of the source file |
| `offset` | integer | optional byte offset inside the target partition, default 0 |
| `policies` | array of strings | see below |

The accepted name and kind pairs are fixed for this board:

| Name | Kind |
| --- | --- |
| `boot0` | `boot1` |
| `boot1` | `boot2` |
| `gpt`, `gpt_backup` | `user` |
| `lk_a`, `lk_b`, `tee1`, `tee2`, `expdb`, `misc`, `boot_a`, `boot_b` | `user` |

`gpt` and `gpt_backup` are not GPT entries. `gpt` is the primary copy at user-area address 0,
and `gpt_backup` is the backup copy at an address the manifest supplies through `offset`. Both
are addressed absolutely and need their base in `--partition-offsets`.

- MediaTek "BOOT0" contains both eMMC boot areas. This tool names boot area 1 `boot0` and boot
  area 2 `boot1`, matching the mtkclient `--parttype` naming. A normal `boot0` entry covers boot
  area 1 only. A `boot0` entry with `full_boot0` covers both areas and must use a 4 MiB source.
  The manifest rejects that entry when a separate boot area 2 entry is also present.

### Policies

| Policy | Meaning |
| --- | --- |
| `sector0_last` | Write bytes `sector_bytes..end` first and sector 0 last, after all other partitions. Required on a writable `boot0`; valid only there. |
| `readback_verify` | Required on every writable partition. The tool always verifies each write; the policy is the explicit declaration of that requirement. |
| `never_write` | The partition is checked by `verify` and skipped by `apply`. Required on `boot1`. |
| `full_boot0` | Opt-in on `boot0` only. Requires a 4 MiB source and `partition_bytes` equal to both boot areas. The plan writes area 1, then area 2, then area 1 sector 0. A separate boot area 2 entry in the same manifest is rejected. |

### Example

```json
{
  "schema_version": 1,
  "description": "stock boot-chain restore drill, pre-Kaeru",
  "device": {
    "hwcode": "0x8167",
    "flash_bytes": 7650410496,
    "boot_area_bytes": 2097152,
    "sector_bytes": 512
  },
  "chain_installed": false,
  "partitions": [
    {
      "name": "boot0",
      "kind": "boot1",
      "partition_bytes": 2097152,
      "source": "sources/boot0.bin",
      "source_bytes": 2097152,
      "sha256": "d5fc0bbbc89b7dfaa7ca39fc1d0bc8da0df4a66e2324f3a9742ba70c04f5e327",
      "policies": ["sector0_last", "readback_verify"]
    },
    {
      "name": "boot1",
      "kind": "boot2",
      "partition_bytes": 2097152,
      "source": "sources/boot1.bin",
      "source_bytes": 2097152,
      "sha256": "4c8e02060ab820652000e4ffae90c5554d88230625edc704d269bee3efeb80f3",
      "policies": ["never_write"]
    },
    {
      "name": "tee1",
      "kind": "user",
      "partition_bytes": 5242880,
      "source": "sources/tee1.bin",
      "source_bytes": 5242880,
      "sha256": "aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e",
      "policies": ["readback_verify"]
    }
  ]
}
```

The hashes above come from `experiments/phase-01/notes.md`. The sample is illustrative. Keep real
manifests and donor images local.

## Guards

Every guard fails closed before a write. `plan` and `apply` both run the static guards and the
backend checks.

| Guard | Behaviour |
| --- | --- |
| identity mismatch | reject when any device field differs from the backend |
| source size mismatch | reject when the file size differs from `source_bytes` |
| source hash mismatch | reject when the file SHA-256 differs from `sha256` |
| partition too small | reject when `source_bytes > partition_bytes` |
| offset not aligned | reject when `offset` is not a multiple of `sector_bytes` |
| extent past the partition | reject when `offset + source_bytes > partition_bytes` |
| boot area offset | reject a nonzero `offset` on `boot0` or `boot1` |
| partition size mismatch | reject when the backend reports an actual partition size that differs from `partition_bytes`, for writable and `never_write` entries alike |
| unknown partition | reject names outside the boot-chain set, wrong name/kind pairs, and names absent from the backend |
| BOOT0 spans boot area 2 | reject a `boot0` without `full_boot0` whose `partition_bytes` differs from `boot_area_bytes`, and reject any such source larger than the boot area; reject a `full_boot0` source that is not exactly both boot areas |
| mixed boot-area entries | reject `full_boot0` with any separate boot area 2 entry in the same manifest |
| boot area 2 writable | reject a `boot2` entry without `never_write`; only a planned `full_boot0` area 2 item may write boot area 2 |
| `FASTBOOT_PLEASE` | reject a source for `misc` or `expdb` that contains the ASCII marker |
| `expdb` after install | reject a writable `expdb` when `chain_installed` is true |
| policy completeness | reject a writable entry without `readback_verify`; reject a writable `boot0` without `sector0_last`; reject `sector0_last` on anything but `boot0` |
| plan drift | reject an edited plan, a plan for another manifest, and a plan that no longer matches the sources |

## Write order

The plan follows manifest order, except that every `sector0_last` item is moved to the end of
the whole run. For a `sector0_last` partition the tool emits two plan items:

1. body: offset `sector_bytes`, length `source_bytes - sector_bytes`
2. sector 0: offset `0`, length `sector_bytes`

The sector-0 item runs only after every other partition has been written and read back, so the
boot header is the commit point of the entire restore. Each item is written, read back, and
compared before the next item starts. A mismatch raises `ReadbackError` immediately. Later
items do not run. A failure in the body therefore leaves sector 0 unchanged, which keeps a
usable boot header on the partition. A writable `boot0` without `sector0_last` is rejected.

A `full_boot0` partition emits three items: area 1 body, area 2, then area 1 sector 0. The
sector 0 item still moves to the end of the whole run. A normal `boot0` item covers boot area 1
only. No plan item targets boot area 2 unless it came from a `full_boot0` entry. The tool never
writes `expdb` after the manifest marks a chain as installed.

## Atomicity and resume

`plan`, state, and result documents are written to a temporary file in the target directory, then
fsynced, renamed over the target, and the directory entry is fsynced. A crash cannot leave a
partial JSON document at the final path.

The journal is append-only JSONL. Line 1 is a header with the manifest hash, plan hash, and
backend name. Each completed write appends one record and fsyncs it. A write that fails readback
is never recorded.

`apply` defaults to dry-run. Without `--allow-write` it validates the manifest, identity, plan,
and sources, prints the plan summary, and writes nothing.

`apply --resume` validates the journal before any new write:

- the header hashes must match this manifest and plan, and the backend name must match;
- every operation line must parse and match the plan item at that index;
- the completed records must be a prefix of the plan, with no gap, duplicate, or extra line.

A mismatch or a torn final line is refused with a nonzero exit. `--allow-write` is still required
to continue writing. If the journal is missing, `--resume` starts from zero and rewrites every
item. Whole-item rewrites are safe because a verified item is completed before the next starts.

Default companion paths are `<journal>.state.json` and `<journal>.result.json`. The state file is
informational. The journal is authoritative.

## Backends

### synthetic

The `synthetic` backend reads and writes partition image files below `--root`:

```
<root>/identity.json
<root>/boot1/<name>.bin
<root>/boot2/<name>.bin
<root>/user/<name>.bin
```

`identity.json` has the same four fields as the manifest device block. Partition files must exist
before an operation. The backend refuses to create them.

Fault simulation is available with `--faults '<json>'`:

| Field | Effect |
| --- | --- |
| `fail_after_bytes` | write that many bytes of the next write, then fail |
| `short_read_partition` | return one byte less on the next read of this partition |
| `corrupt_readback` | flip one byte on the next readback of these partitions |
| `disconnect_after_ops` | fail the Nth operation and every later one until `reconnect()` |
| `identity_override` | report a different identity block |

### mtkclient adapter

The adapter shells out to the owner's checkout at `/workspace/libreecho/mtkclient`
(default; override with `--mtkclient-root`) and its virtualenv Python (default
`<root>/.venv/bin/python`). Commands:

| Operation | Command | Gate |
| --- | --- | --- |
| identity | `python mtk.py printgpt` | `--allow-device-read` or `--identity-json` |
| partition read | `python mtk.py r <name> <file> --offset 0x<off> --length 0x<len>` | `--allow-device-read` |
| boot area read | `python mtk.py r <name> <file> --parttype boot1` (or `boot2`) | `--allow-device-read` |
| pseudo read | `python mtk.py ro 0x<abs> 0x<len> <file>` | `--allow-device-read` and `--partition-offsets` |
| partition write | `python mtk.py w <name> <file>` | both write flags |
| offset write | `python mtk.py wo 0x<abs> 0x<len> <file>` | both write flags |
| boot area write | `python mtk.py wo 0x<off> 0x<len> <file> --parttype boot1` | both write flags and `--partition-offsets` |

Both write flags means `--allow-device-write` plus `apply --allow-write`. Write access also
enables reads, because every write is read back and compared.

Addressing follows mtkclient, and the two forms differ:

- `r` adds the partition start to `--offset`, so the plan's partition-relative offsets are sent
  unchanged.
- `ro` and `wo` take an absolute user-area byte address, and a boot-area `wo` takes an offset
  from the area base. A name that must be addressed this way goes in `--partition-offsets` as
  name to base byte offset. `gpt` and `gpt_backup` use base 0.
- A boot-area write of `boot0` uses `--parttype boot1` (boot area 1). A separate boot area 2
  write is refused; boot area 2 is written only by the planned area-2 item of a `full_boot0`
  manifest entry.

Every write must be sector aligned. mtkclient zero-pads a short final sector, which would write
bytes the plan never verified, so a misaligned offset or length fails before the command runs.

Evidence for the syntax and behaviour:

- `mtk.py:140-196` defines the commands and their arguments: `r` takes `--offset`/`--length`,
  `wo` takes positional `offset length filename`, and `--parttype` is a shared option.
- `mtkclient/Library/DA/mtk_da_handler.py:329-397` shows `da_read`: the user path reads from
  `partition.sector * pagesize + offset`, the boot path ignores offset and length and reads the
  whole area, and `gpt` reads a fixed `0x16000` from address 0.
- `mtkclient/Library/DA/mtk_da_handler.py:542-583` shows `da_write`: `w` resolves the partition
  through the GPT (`gpt` maps to address 0) and `writeflash` clamps the length to the file size.
- `mtkclient/Library/DA/mtk_da_handler.py:1341-1362` shows `wo` passes its offset straight
  through as the flash address.
- `mtkclient/Library/DA/mtk_da_handler.py:542-583` and `:329-397` show `--parttype boot1`
  selects boot area 1 (`BOOT1`) and `boot2` selects boot area 2; `boot2` writes require an
  explicit plan item, which only a `full_boot0` entry produces.
- `mtkclient/Library/DA/xflash/xflash_lib.py:857-885` shows `writeflash` rounding the length up
  to 512 bytes and zero-filling the tail.

Every mtk.py command runs in the directory given by `--mtkclient-workdir`. mtkclient writes
`.state` there, and mtk.py rejoins its resident download agent only when that file is present;
without it the next command starts over at the BROM handshake. Plan, apply, and verify for one
hardware session must pass the same directory: the Phase 3 restore drill uses
`/tmp/lidar-drill-mtkclient` for the write session and a fresh empty directory such as
`/tmp/lidar-verify-mtkclient` for the cold readback after the reset and power cycle. A fresh
BROM session needs a new empty directory, because a `.state` left by an earlier cable session
names a download agent that is gone.

Without `--mtkclient-workdir` every command runs in a fresh temporary directory, so nothing is
shared between invocations. In both modes the checkout stays clean and no device image lands in
the work directory: mtkclient writes `hwparam.json` next to the output file
(`mtk_da_handler.py:1277`), and the read and write binaries stay in a per-operation temporary
directory.

### DA shutdown and power removal

The adapter has no shutdown integration: after the last `apply` or same-session `verify`, the
device still holds a live download agent, and the boot chain is only committed once the device
resets. A clean reboot is therefore part of the procedure. Change to the workdir of the session that
just finished. Its `.state` file lets `mtk.py` rejoin the resident download agent. For example:

```sh
cd /tmp/lidar-drill-mtkclient
/workspace/libreecho/mtkclient/.venv/bin/python /workspace/libreecho/mtkclient/mtk.py reset
```

The `--mtkclient-workdir` option belongs to `lidar-restore`, not `mtk.py`. `reset` calls
`daloader.shutdown()` and is a reboot and hardware action: it needs its own explicit approval
and is never bundled with a write approval.

After the approved reset, disconnect USB and board power. Wait for confirmation that the unit
is fully unplugged before reconnecting it into BROM. A USB reconnection without power removal
is not a fresh BROM session. Use a fresh empty workdir (no `.state`) for the cold readback,
which forces the BROM handshake. A same-session readback does not prove persistence because it
may reflect the eMMC write cache rather than nonvolatile storage. Only a post-power-cycle read
in a new session counts.

Identity sources:

- `--identity-json` reads a local capture without touching the device. It may include a
  `partitions` list of known GPT names.
- Without an identity file, identity comes from parsing the `printgpt` transcript (`HW code`,
  `EMMC Boot1 Size`, `EMMC USER Size`, and `Total disk size`/`sectors`).

`--allow-device-read` and `--allow-device-write` are absent by default, so a device is never
touched unless both the invocation and the transport opt in.

## CLI exit codes

| Code | Meaning |
| --- | --- |
| 0 | success; `verify` found all partitions matching |
| 1 | `verify` ran and found a mismatch |
| 2 | validation, guard, journal, backend, or readback error |

## Tests

`python3 -m unittest -v` runs 65 host tests. The suite covers the happy path, dry-run, identity
mismatch, unknown partition, source hash and size mismatch, partition too small, the
partition-size gate at planning, the entry-offset guards, a four-partition apply with the BOOT0
header written last, readback mismatch,
a partial BOOT0 write, sector 0 ordering, resume, corrupted and truncated
journals, atomic plan writes in both serialization and rename failures, plan editing, the
`expdb`/`misc`/`FASTBOOT_PLEASE` guards, idempotent verify, every fault simulator, the
`full_boot0` policy (both areas written and verified, 4 MiB source required, boot0-only, and
rejected alongside a separate boot area 2 entry), and mtkclient
command construction with a fake runner, including a fake device that answers the read, offset
read, and both write commands so a full apply and readback runs without hardware, plus the
refusal of a separate boot area 2 write and its authorization under `full_boot0`. It also
checks the CLI plan, dry-run apply, and verify exit codes.

## Limitations

- The partition name and kind set is fixed to the Lidar boot-chain partitions. It is not a
  general partition tool.
- `verify` compares each source extent only. It does not inspect the GPT, RPMB, or bytes outside
  the manifest sources.
- The mtkclient adapter verifies partition names against a captured GPT list only when
  `--identity-json` includes `partitions`. The manifest allowlist still applies.
- The size gate compares the manifest `partition_bytes` with the backend's actual partition size
  when the backend reports one. The synthetic backend does; the mtkclient adapter does not,
  because a captured GPT list carries names only, so only the manifest-side size checks run
  there.
- The tool does not check that a source path is outside the device directory. Use an immutable
  backup copy as the source, never the live partition file.
- A vendor 4 MiB BOOT0 image (boot area 1 plus boot area 2) needs an explicit `full_boot0`
  entry, a 4 MiB source, and no separate boot area 2 entry. Without that policy the tool
  rejects the image because a normal BOOT0 write must not include boot area 2.
- A hardware write path exists but has not run on a device. It is exercised only against a fake
  device in the host tests. Any device run needs its own approval, and the Phase 3 restore drill
  is the first one.
- `partition_offsets` is not read from the device. The caller supplies it, so a wrong base
  would send `wo` or `ro` to the wrong address. Use a captured GPT as the source and verify the
  base before a write.
- Donor images, serials, and identity values stay local. Do not commit a real manifest or its
  sources.
