# Lidar boot-chain backup set

Date: 2026-11-24. Host-only. No device read, write or reboot was performed for
this note; the sizes and offsets come from the existing lab evidence below.

## The set

`LibreEcho-Platform tools/mt8167-arm64/install/lidar_backup_set.py` holds the
set as data. Names match the Phase 3 restore-drill manifest so a backup can be
verified now and used by the same repair path later.

| Entry | Kind | Absolute offset | Bytes | Source |
| --- | --- | --- | --- | --- |
| `boot0` | eMMC boot area 1 (`boot1` in mtkclient) | 0 | 0x200000 | `private/lab/phase-03/manifests/drill.json:68-78`; `private/lab/phase-01/manifest.json:3-7` |
| `boot1` | eMMC boot area 2 (`boot2`) | 0 | 0x200000 | `drill.json:57-66`; `phase-01/manifest.json:8-12`; `brom-printgpt.log:123-142` (each boot area 0x200000) |
| `gpt` | primary GPT, not a GPT entry | 0 | 0x16000 | `phase-01/manifest.json:30-34`: mtkclient `r gpt`, LBA0, header at 512, entries LBA 2 |
| `gpt_backup` | backup GPT, not a GPT entry | 0x1C7FFBE00 | 0x4200 | `phase-01/manifest.json:35-40`; `phase-03/notes.md` "Addresses" (LBA 0xE3FFDF-0xE3FFFF) |
| `lk_a` | GPT `lk_a` | 0x300000 | 0x100000 | `brom-printgpt.log:127` |
| `lk_b` | GPT `lk_b` | 0x900000 | 0x100000 | `brom-printgpt.log:129` |
| `tee1` | GPT `tee1` | 0x400000 | 0x500000 | `brom-printgpt.log:128`; drill `...:46-55` |
| `tee2` | GPT `tee2` | 0xA00000 | 0x500000 | `brom-printgpt.log:130` |
| `expdb` | GPT `expdb` | 0xF00000 | 0xA00000 | `brom-printgpt.log:131`; drill `...:35-44`; `PLAN.md` "Boot-chain safety" |
| `misc` | GPT `misc` | 0x1900000 | 0x80000 | `brom-printgpt.log:132`; Kaeru marker is `misc[0:16]`, `PLAN.md` "Boot-chain safety" |
| `persist` | GPT `persist` | 0x1980000 | 0x1000000 | `brom-printgpt.log:133`; `private/dumps/stock/persist.bin` (16 MiB) |

The board has **no `nvram` partition** in its GPT (`brom-printgpt.log:123-142`),
so none is in the set; `persist` is the device-specific store that exists.

Excluded on purpose: `boot_a`/`boot_b` (the normal installer rewrites and
hashes them back), `kb`, `dkb`, `swdl`, `system_a`, `system_b`, `cache`,
`userdata`. The primary GPT read is 0x16000 bytes, not the stock dump's 0x4200
bytes, because that is the read the Phase 1 backup and the restore drill used;
the backup GPT is 33 sectors.

## What the module verifies

`verify_backup_set(backup_dir, manifest)` checks, per entry: presence, exact
byte size, and a freshly computed sha256 against the manifest pin. It returns
findings (`missing`, `size`, `sha256`) in set order; `require_complete_backup`
raises. Manifest validation refuses a missing/unknown entry, a size that
differs from the measured area, wrong device geometry, and unsafe file names.
There is no device I/O in the module or its tests.

Tests: `python3 -m unittest discover -s tools/mt8167-arm64/install -p
'test_lidar_backup_set.py'` (15 tests).

## What the preparation command must still do

The preparation command does not exist yet; this ticket deliberately stops at
the reusable data and verifier. It still must:

1. Enter BROM (`0e8d:0003`, hwcode `0x8167`) and read exactly these areas over
   mtkclient, producing one file per entry plus a manifest in this schema.
2. Write the backup outside the live dump directory, run
   `require_complete_backup`, and record the manifest sha256 before any chain
   write. The Phase 2 rule applies: use an immutable backup copy as a restore
   source, never the live partition file.
3. Perform the pre-install same-byte restore drill and stock-boot check, then
   install the owner-access chain.
4. Check `expdb[0:16]` for the MTK magic `88 16 88 58` before any flash write
   (Platform `AGENTS.md`), and never write or erase `expdb` after Kaeru is
   installed.
5. Keep `boot1` (boot area 2) `never_write`; only the explicit `full_boot0`
   fallback may write it, with a separate approval.
6. Be reviewed for licensed components and source-built Kaeru/Koboreru before
   it is called production. No hardware run is claimed here.
