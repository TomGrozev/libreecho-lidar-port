# Phase 3 preparation

Preparation began host-only. Both hardware sessions have since run, each under its own
approval.

## State

- Restore tool: `experiments/phase-02/restore`, `python3 -m unittest -v` runs 60 tests, all
  pass. The mtkclient backend now has a write path, gated by `--allow-device-write`, and
  supports partition-relative offsets plus absolute pseudo partitions (`gpt`, `gpt_backup`).
  `--mtkclient-workdir` gives plan, apply, and verify one mtk.py working directory, so the
  resident download agent from the plan is reused by apply.
- Manifests and sources live here, not in the tool tree. They are local and must not be
  committed.
- Stock backups verified against `dumps/20261110-lidar-readback/stock-boot-chain-backup/SHA256SUMS`:
  all five files match.

## Files

| Path | Purpose |
| --- | --- |
| `manifests/drill.json` | same-byte restore drill over the stock boot chain |
| `manifests/install.json` | experimental chain install, source-built boot-chain images |
| `identity.json` | captured identity and GPT names for `--identity-json` |
| `offsets.json` | absolute bases for `gpt` and `gpt_backup` |
| `sources/expdb_kaeru_0x40000.bin` | Kaeru LK image padded with zeros to 256 KiB |
| `sources/tee1_koboreru_prefix.bin` | Koboreru image plus the stock tee1 tail, full 5 MiB |
| `sources/boot0_2019_area1.bin` | boot area 1 of the 2019 preloader, 2 MiB |

Source hashes (pinned in the manifests):

| Source | Bytes | SHA-256 |
| --- | --- | --- |
| `sources/expdb_kaeru_0x40000.bin` | 262144 | `a1eda7b56d05b184892f681c27f1374ef962a04a1aa4d0d0a463e388c98db152` |
| `sources/tee1_koboreru_prefix.bin` | 5242880 | `b41f1d64f078ddbdf60ddf9c39589b37494d78e7cce26a052dc3a6717cb091e0` |
| `sources/boot0_2019_area1.bin` | 2097152 | `fb987ad9cd2af5e4d86e6476f1f154e555795d915d247a23110b80ed0363de45` |

`tee1_koboreru_prefix.bin` keeps stock bytes from offset 1115664 onward, so the write changes
only the Koboreru prefix and stays sector aligned. The stock tee1 tail is not needed at run
time; the source is already complete.

## Addresses

| Partition | Sector | Byte address |
| --- | --- | --- |
| `tee1` | 8192 | 0x400000 |
| `expdb` | 30720 | 0xf00000 |
| `gpt_backup` | 0xe3ffdf | 0x1c7ffbe00 |

`gpt_backup` is the 33-sector backup GPT: 32 entry sectors then the header, starting 32 sectors
before the last usable LBA. Its base is supplied through `offsets.json`, because mtkclient
addresses `wo` absolutely and `r gpt_backup` does not exist.

## Session 1: same-byte restore drill

Prerequisite: the unit is in BROM mode, the host has the mtkclient checkout and its virtualenv,
and `/tmp/lidar-drill-mtkclient` is a new empty directory. Plan, apply, and verify must pass that
same directory: mtk.py only rejoins its resident download agent when `.state` is in the working
directory, and without it apply starts over at the BROM handshake before any write. With
`--identity-json`, `plan` is host-only and does not open USB. Start the first `verify` before
reconnecting the unit so it catches BROM, establishes `.state`, and compares every stored extent
before any write. The same-byte drill expects all writable targets to match. A `boot1` mismatch
needs inspection; normal bootcount changes do not justify rewriting that never-write area.

```sh
mkdir -p /tmp/lidar-drill-mtkclient
cd experiments/phase-02/restore
python3 lidar_restore.py plan \
    --manifest ../../phase-03/manifests/drill.json \
    --out /tmp/drill-plan.json \
    --backend mtkclient \
    --identity-json ../../phase-03/identity.json \
    --partition-offsets ../../phase-03/offsets.json \
    --mtkclient-workdir /tmp/lidar-drill-mtkclient

python3 lidar_restore.py verify \
    --manifest ../../phase-03/manifests/drill.json \
    --report /tmp/drill-preflight-report.json \
    --backend mtkclient \
    --identity-json ../../phase-03/identity.json \
    --partition-offsets ../../phase-03/offsets.json \
    --mtkclient-workdir /tmp/lidar-drill-mtkclient \
    --allow-device-read

python3 lidar_restore.py apply \
    --manifest ../../phase-03/manifests/drill.json \
    --plan /tmp/drill-plan.json \
    --journal /tmp/drill.journal.jsonl \
    --backend mtkclient \
    --identity-json ../../phase-03/identity.json \
    --partition-offsets ../../phase-03/offsets.json \
    --mtkclient-workdir /tmp/lidar-drill-mtkclient \
    --allow-device-read --allow-device-write --allow-write
```

Then:

```sh
python3 lidar_restore.py verify \
    --manifest ../../phase-03/manifests/drill.json \
    --report /tmp/drill-report.json \
    --backend mtkclient \
    --identity-json ../../phase-03/identity.json \
    --partition-offsets ../../phase-03/offsets.json \
    --mtkclient-workdir /tmp/lidar-drill-mtkclient \
    --allow-device-read
```

Expected: `apply` writes 6 items, `boot0` sector 0 last, every readback matches, exit 0. `verify`
reports `ok: true` with 5 checked extents and `boot1` skipped as `never_write`. Reboot and confirm
the stock device still boots.

`boot1` is never written in either session.

## Session 2: chain install

Same shape with `manifests/install.json` and a new empty `/tmp/lidar-install-mtkclient` for
`--mtkclient-workdir`. Plan, apply, and verify of this session share that directory, and it must
not be the Session 1 directory because its `.state` names the previous download agent. Order is
`expdb`, `tee1`, then `boot0` body and sector 0 last. `boot1` stays `never_write`. After it
completes, reboot into fastboot and check `fastboot getvar product`, `unlock_status`, and the
Kaeru version.

Do not overwrite `expdb` after this point. Post-install stock recovery is not authorized.

## Hardware result, 2026-11-14

The same-byte drill passed and stock booted normally. All source-built install targets verified after writing and again after a fresh BROM entry. The stock Volume Up boot-menu sequence produced no fastboot USB device, and a separate normal boot without buttons stayed dark. This rejects normal startup of the source-built chain, but does not identify the failing stage without UART. BROM recovery remains available; no post-install recovery write has been approved or attempted.

### Static root cause: wrong-target Kaeru build

Later host-side analysis found the cause without touching the device. The installed Kaeru
LK image was built for the radar model. The installed `expdb` image is 262144 bytes,
SHA-256 `63f2a7a1dacc63e791e963271e8a1defb9226b65021647a8ec2b4f977d81fded`; its Kaeru
sub-image contains the radar addresses (`0x4BD...` base) instead of the Lidar addresses
from `lidar_defconfig`. The enhanced checker exits 1 with 22 failures on that image.
`lidar_defconfig` omitted `CONFIG_FASTBOOT_INFO_ADDRESS`, `CONFIG_BOOTMODE_ADDRESS` and
`CONFIG_VIDEO_PRINTF_ADDRESS` while those configs had no Kconfig defaults, so the build
kept a stale radar autoconf. The corrected build, with `default 0x0` on those configs and
zero treated as absent, passes the checker with 45 checks. Details and the preserved
evidence live in `experiments/phase-02/notes.md` under "Wrong-target build and independent
target checks"; the evidence copy is `experiments/phase-03/logs/kaeru-wrong-target/`.

The corrected Kaeru image (`artifacts/phase-02/kaeru/lidar-kaeru.bin`, 221776 bytes,
SHA-256 `6743a0bad7e7655c366508a4d3f0b62efd1a81d7f561733c29cc3f5f004a4513`) passed the
host checks. Its 256 KiB expdb source (SHA-256
`a1eda7b56d05b184892f681c27f1374ef962a04a1aa4d0d0a463e388c98db152`) was then installed
alone and verified on the unit. The corrected chain still failed the fastboot attempt and a
separate normal boot. The wrong-target build was not the only boot blocker.

## Open approvals

- Any further write or reboot requires separate approval.
- A fresh post-reboot BROM readback is the next requested diagnostic step.

## Reference-chain fallback prepared host-only, 2026-11-14

The reference kit `reference/echo-plus-2-bootchain-v0.2.1` supplies an expdb Kaeru LK image,
a Koboreru tee1 loader, and a 4 MiB BOOT0 that covers both 2 MiB boot areas. The BOOT0 file
is the pinned `20190926_195940` image plus 2 MiB of zeros for boot area 2. Its boot area 1 is
byte-identical to the `boot0_2019_area1.bin` already installed on the unit. Area 2 has never
been written on this unit, and this plan writes it with zeros, as the reference installer does.

Sources live in `experiments/phase-03/sources`. Padding is deterministic zeros:

| Source | Bytes | Padding | SHA-256 |
| --- | --- | --- | --- |
| `reference_expdb_kaeru_prefix.bin` | 214016 | 104 zero bytes after the 213912-byte Kaeru image | `07f15dc24e862ec4f27e5ecc72d15c894049f9b3f0afe8edc0bc46863e5eada8` |
| `reference_tee1_koboreru_prefix.bin` | 1120256 | 496 zero bytes after the 1119760-byte Koboreru image | `53704bda5d544612e53e48c476d9ba5dab446557288085f6c7385e4d78661193` |
| `reference_boot0_full_4mib.bin` | 4194304 | none | `ab0869c0820131920bbbc9a4a74d754ac222e7ca232e76cc21a81b3fe4a70cd1` |

The manifest is `manifests/reference-chain.json`, SHA-256
`a6892ecdb0f9ddbe97bc2d0067d4914d9028f3832b7b127b6fb731e6a2f93839`. It names sources in
write order: expdb, tee1, boot0. The boot0 entry carries the explicit `full_boot0` policy.
That policy permits a 4 MiB source only on the boot0 entry. It also rejects a separate boot
area 2 entry in the same manifest, because one plan must not claim an area is never written
while it replaces that area.

The host-only plan is `logs/reference-chain-plan.json`, plan SHA-256
`52552e4b091ecef379b9cc9210f8bff1d5e767b946a53cda84f58dd9a672052f`, five items:

1. expdb, offset 0, length 214016
2. tee1, offset 0, length 1120256
3. boot0 area 1 body, offset 512, length 2096640
4. boot0 area 2, offset 0, length 2097152, written as boot area 2
5. boot0 area 1 sector 0, offset 0, length 512

Item 5 is the commit point of the run. The plan was built in `/tmp/lidar-reference-mtkclient`.
Preparation was host-only. The later approved hardware run used a fresh work directory and
regenerated the same plan hash.

Pending hardware procedure, after separate approval:

1. Enter BROM and confirm `lsusb -d 0e8d:0003`.
2. Create a new empty work directory, for example `/tmp/lidar-reference-hw-mtkclient`.
3. Run `verify` for this manifest with that work directory and `--allow-device-read`. It
   records the pre-write state and establishes the resident download agent.
4. Run `plan` again with the new work directory and compare the plan hash with the value above.
5. Run `apply` with `--allow-device-read --allow-device-write --allow-write`.
6. Run `verify` again and expect `ok: true` for expdb, tee1, and the full 4 MiB boot0.
7. Do not reboot automatically. Enter fastboot by the established method and check
   `fastboot getvar unlock_status` and `fastboot oem kaeru-version`.

Residual risks:

- Boot area 2 becomes zeros. The reference installer does the same, but this unit's saved
  stock area 2 differs and a later stock restore needs its own approved 2 MiB write.
- The expdb source zeroes the last 104 bytes of its final sector. The current expdb already
  has zeros there from the earlier 256 KiB write.
- The 4 MiB BOOT0 write depends on mtkclient boot area 1 and boot area 2 writes. Each is
  clamped by the DA to one 2 MiB area. The plan writes each area separately and reads each
  area back.
- Normal boot of the reference chain is not proven on this unit.

## Reference hardware result and stopping point

The full reference install ran with separate approval. All five writes completed, and the
post-write report matched reference expdb `07f15dc2...`, tee1 `53704bda...`, and full BOOT0
`ab0869c0...`. The install journal, live plan, preflight, and report are preserved in
`experiments/phase-03/logs/reference-chain*`.

The stock-LK Volume Up menu sequence did not produce fastboot. Static analysis later found
that the reference LK does not contain the active menu path. The kit's pinned Kamakiri
stages did work through a minimal script: it set the WDT fastboot flag at `0x10007024` and
rebooted without an eMMC write. The first script attempt stopped before loading a stage
because the release's relative stage path differed from upstream. A fresh BROM session
with the corrected path completed.

Fastboot then reported `product: LIDAR`, but `unlock_status: false` and rejected
`oem kaeru-version` as restricted on locked hardware. `getvar all` reported the 2023 stock
LK and preloader build descriptions. It also reported the original serial and IDME data even
though boot area 2 had verified as zeros in the install session. This does not prove that
the reference chain ran. A fresh post-reboot BROM readback is the next diagnostic step. The
owner stopped before approving that readback. No unlock, flash, or further reboot command
followed the locked-fastboot result.

All temporary session state, including mtkclient workdirs and `.state` files, plans,
journals, reports, the minimal fastboot script, and local Android tools, is preserved under
`experiments/phase-03/session-state/20261114/tmp/`. The unit was left in stock locked
fastboot. Hardware actions are paused.

## Post-power-cycle readback, 2026-11-15

The unit was powered off normally overnight, then entered BROM today with mtkclient already
listening. The read-only verify used a fresh work directory
(`/tmp/lidar-reference-readback-20261115`) and the reference manifest:

- expdb matched the reference Kaeru LK image exactly: `07f15dc2...`, 214016 bytes.
- tee1 was exactly stock: `aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e`.
- BOOT0 area 1 was exactly stock: `d5fc0bbbc89b7dfaa7ca39fc1d0bc8da0df4a66e2324f3a9742ba70c04f5e327`.
- BOOT0 area 2 was stock except 403 bytes of ordinary boot-time changes, not zeros.

So the reference install's tee1 and both BOOT0 writes did not survive a true power cycle.
Only expdb, the first write in the plan, reached nonvolatile storage. A same-session readback
and a reset without removing power can both be served by the eMMC write cache. This also
explains the stock fastboot result: the stock chain was still present. The earlier source
chain reads were not proof of persistence either.

mtkclient's normal command exit does not send the DA shutdown command; only `mtk.py reset`
calls `daloader.shutdown()`. The reference Kamakiri transport also waits five seconds before
reboot for eMMC flush. The leading explanation is therefore unflushed eMMC writes, not a
reference-chain boot failure. The next write test must end with a clean DA shutdown, a real
power removal, and a fresh BROM readback before any fastboot attempt.

Readback report and images are preserved under
`experiments/phase-03/session-state/20261115/readback/` with `SHA256SUMS`.

## Clean persistence retest, 2026-11-15

A later retest repeated the same five-item plan and used a clean DA shutdown followed by
disconnect-first power removal. The post-power-off report matched every manifest source:
expdb `07f15dc2...`, tee1 `53704bda...`, and full BOOT0 `ab0869c0...`. The fresh BROM
readback therefore proves that all three images persisted. It also rules out anti-rollback
restoring the stock sectors after power removal.

The reports are
`logs/persistence-retest-20261115/reference-persist-retest-verify.json` and
`logs/persistence-retest-20261115/reference-persist-after-poweroff-20261115.json`.
A local assertion checked both this all-match result and the earlier only-expdb mismatch.

This result proves persistence only. It does not prove that the reference chain starts
Kaeru fastboot. Any later boot test needs separate approval and another disconnect-first
restart. The restore tool still has no DA shutdown integration, so the manual shutdown and
power-removal checkpoint remains required.

## Anti-rollback disassembly, 2026-11-15

The function at `0x219a58` is SHA-1 compression. Its 80 rounds and four SHA-1 constants
end at `0x21a88c`. It is separate from the anti-rollback policy. The earlier start at
`0x219a56` included the last halfword of the preceding literal pool.

The anti-rollback routine is `0x20192c..0x201af2`. It reads a 16-byte version record from
RPMB block 0 and compares stored PL, TEE, and LK versions with the loaded images. A stored
version newer than the loaded image prints a mismatch message and enters an infinite loop.
A newer loaded image updates the record and its checksum. The only persistent write is the
16-byte RPMB record. The routine has no eMMC user-area or boot-area write call, so it cannot
restore stock tee1 or BOOT0 sectors. The Koboreru patch list disables this routine at
`0x20192c` before starting the modified chain.

A host-only Capstone check passed all 17 assertions for the function boundaries, SHA-1
rounds, anti-rollback call set, field stores, and RPMB-only write targets. These control-flow
results come from static analysis. No mismatch or hang was observed on the device.

The reference release intentionally keeps the stock LK. Its installer writes only expdb,
tee1, and BOOT0. The mixed-version chain is therefore expected and is not by itself a boot
failure. A future fastboot test would check execution after persistence, not storage.

## Reference-chain execution confirmed, 2026-11-15

The owner approved a normal-boot and fastboot execution test. After a confirmed full power
removal, the owner reconnected power without USB. Normal startup looked normal after 20
seconds.

A second confirmed power removal preceded a fresh BROM connection. The pinned Kamakiri
stage 1 and stage 2 hashes matched the release manifest. The preserved minimal script loaded
those stages, set the WDT fastboot bit at `0x10007024`, and rebooted. It did not write
eMMC, MISC, BCB, or any partition. No power removal occurred during this warm reboot because
that would clear the WDT flag.

Fastboot then reported:

- `product: LIDAR`
- `unlock_status: true`
- `kaeru v2.0.0-g8d24a1a-dirty`
- `lk_build_desc: 674eac9-20190926_195940`
- `pl_build_desc: 2b6f82c-20190926_195940`

This proves that the persisted reference chain reached unlocked Kaeru fastboot. The device
remained in fastboot. No flash or unlock command followed. The command transcript is
`logs/fastboot-execution-20261115.txt`.

## Phase 3 closeout, 2026-11-15

Phase 3 is closed as of this note. The same-byte restore drill, stock boot, repeated BROM
entry and readback, persistence retest, and the unlocked Kaeru fastboot verification all
passed on the unit, on the reference chain installed under separate approval with the
full-4-MiB BOOT0 fallback. Normal boot looked normal after a confirmed power removal.

One limitation must carry into later phases: the source-built Kaeru/Koboreru chain is not
hardware-proven. Its failed normal boot on 2026-11-14 is inconclusive because it happened
before this phase discovered the eMMC clean-shutdown/persistence issue, so it likely never
executed persisted bytes. A source-built chain must be reinstalled with a clean DA shutdown,
a disconnect-first power removal, and a fresh BROM readback before any boot verdict.
Production validation of the source-built boot-chain stages remains necessary in Phase 7.
The approved reference chain is bring-up evidence only; it does not validate the
source-built chain.

No LibreEcho kernel or system boot has been attempted. expdb was never overwritten with a
stock image after the first Kaeru install.

