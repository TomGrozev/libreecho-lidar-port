# Lidar unit hardware checks, 2026-11-26 (read-only)

Unit: <DEVICE_IP_A>:5555 (adb, root shell). No firmware write, no reboot, no OTA, no
service start or stop. Host tools: `private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr/bin/adb`
(this adb has no `exec-out`; binary reads used `shell 'dd … | base64'`).

## Reachability and installed version

| Fact | Value | Log |
| --- | --- | --- |
| adb | `<DEVICE_IP_A>:5555  device` | `01-identity.log` |
| kernel | `6.18.64+ #1 SMP 2026-11-25 00:00:00 UTC aarch64` | `01-identity.log` |
| cmdline slot | `androidboot.slot_suffix=_a`, `verifiedbootstate=yellow`, `libreecho.lab=p6-v2` | `02-state.log` |
| installed | slot `a`, version `0.2.43`, txn `txn-161730cea4dc3b3183f4aa2e`, `update_channel=dev` | `04-ota-files.log` |
| boot health | `state=confirmed running_slot=a pending_slot=a`, boot 125 | `04-ota-files.log` |
| previous txn | `txn-6f0ab9c71209e7dd9c51e9d2` (v0.2.42), rolled back; `rolled-back` names slot `b` | `04-ota-files.log` |
| partitions | expdb=`mmcblk0p7`, misc=`p8`, lk_a=`p3`, tee1=`p4`, boot_a=`p10`, boot_b=`p11` | `07-partnames.log` |
| total flash | `14942208` sectors = 7650410496 B; userdata `9647071` sectors (matches installer contract) | `15-sysfs-sizes.log` |

The unit is not on v0.2.42. That deploy failed its confirm and rolled back, and v0.2.43 was
installed and confirmed on slot `a` afterwards. v0.2.44 exists on the host only.

## Check 1: expdb[0:16] and the MTK magic (PLAN Phase 7 "never write expdb")

Command (read-only, adb root):

```
adb shell "dd if=/dev/mmcblk0p7 bs=16 count=1 2>/dev/null | od -An -tx1 -v"
```

Result: `88 16 88 58 d0 40 03 00 4c 4b 00 00 00 00 00 00`. That is an MTK header with
payload size `0x340d0` and `LK\0` at +8, exactly the installed lab expdb source prefix in
`expdb-guard.md` ("installed" variant `… d0 40 03 00 4c 4b`), not `FASTBOOT_PLEASE`.
Feeding the same 16 bytes to `install/expdb_guard.check_expdb_prefix` returns `kaeru-v2`
(`09-expdb-guard-verdict.log`). Cross-check: `lk_a` (`mmcblk0p3`) begins with the same
MTK magic and size `0x33d38` (`08-expdb-magic.log`).

Logs: `08-expdb-magic.log`, `09-expdb-guard-verdict.log`.
Moves: the "no hardware read yet" part of the expdb item. The Kaeru-fastboot path
(`fetch:expdb:0:16`) still needs a reboot into fastboot and was **not** run.

## Check 2: GPT and backup-set geometry through the prepare command's own gate

Live reads: `gpt` (0x16000 from LBA 0) and `gpt_backup` (0x4200 at 0x1C7FFBE00), plus
`lk_a`, `lk_b`, `tee1`, `tee2`, `expdb`, `misc` (script `read-live.sh`, log
`10-live-read-hashes.log`). Each file's host sha256 equals the on-device sha256 of the
same read (transfer integrity).

`check-live-gpt.py` feeds the live GPT bytes into `lidar_prepare.parse_gpt()` and
`check_geometry()` with the Lidar identity (`hwcode 0x8167`, flash 0x1C8000000, boot area
0x200000, 512-byte sectors). Result: 16 partitions, primary and backup tables agree, every
target partition and every backup-set offset and size matches, and userdata ends at
0x1C7FFFE00 (inside the user area). `14-live-gpt-geometry.log`.

Hashes against the stock backup (`private/dumps/20261110-lidar-readback/stock-boot-chain-backup/SHA256SUMS`):

| area | live sha256 | equals stock |
| --- | --- | --- |
| gpt | `7668e74b…96b682` | yes |
| gpt_backup | `07fda82b…7210945c` | yes |
| lk_a | `e1f541d1…ff9d5c` | yes (stock `lk_a.bin`) |
| lk_b | `e1f541d1…ff9d5c` | yes (identical to stock `lk_a.bin`; no stock `lk_b.bin` dump) |
| tee1 | `ed2b085c…aecbd1` | no: Koboreru installed (expected) |
| tee2 | `aa2b9291…38ad75e` | yes (stock `tee1.bin` and `tee2.bin` share this hash) |
| expdb | `33473825…afd0ece9` | no: Kaeru LK stage installed (expected; stock `e5b844cc…`) |
| misc | `776aa664…0fd3ef0b` | no (stock `9248bd41…`); `misc` carries the bootloader BCB, so this is normal churn |
| persist | `8582bc1a…c2819def` | contents not pulled; hash only |

`lk_a` and `lk_b` hash identically and both start with the stock MTK LK header, so the LK
partitions were not replaced; Kaeru lives in `expdb`. The unit's adb link dropped during
the first pass (partial `tee2` read, `tee2` to `persist` offline) and came back; the second
pass (`finish-read.sh`, `16-finish-read.log`) completed every area with matching host and
device hashes.

## Check 3: prepare command dry run

`python3 …/prepare/lidar_prepare.py --amonet private/forks/amonet --dry-run identify`
and `… backup --backup-dir …/backup-dryrun` both exit 0 and print the reviewed amonet
read commands (identity, both GPTs, all 11 backup-set areas twice, manifest write).
No USB and no file write (`13-prepare-dryrun.log`, `prepare-*-dryrun.jsonl`).
This does not replace a BROM run.

## Check 4: Thread service

Read-only inventory of installed v0.2.43: **no** `otbr-agent` or `ot-ctl`,
no `lidar-efr32`, no `libreecho-threadd.init`, no `/data/libreecho/firmware`, and no
`radio` key in `web-config.json`. `dbus-daemon` and `avahi-daemon` do run from the base
image. `11-thread-announce-state.log`.
The Thread service is not in the installed image, so an on-device run needs a new image
(firmware write), and the RCP upload path stays deferred.

## Check 5: announce bug

`/usr/local/sbin/libreecho-esphomed` sha256 `75adde15…87ff74f`, running (pid 8388);
status `last_result: success` (epoch 1795509586). `12-esphomed-binary.log`.
The installed UI head is `972bd742` (v0.2.43) and the v0.2.44 build uses `e44b9ba`; neither
contains `0cc5507` ("ignore chunk extensions"), which lives only on fork branch
`feature/lidar-support-0.14.6`. Both deployed sources do contain `unframe()`, the upstream
PR #530 split fix. The device check as written (pink-free announce through an
extension-emitting proxy) therefore cannot pass on what is installed; it needs an image
built with `0cc5507` merged (firmware write). The plain no-pink/no-audio check
needs me to send an HA TTS announcement.

## Not run / deferred

- Kaeru fastboot `fetch:expdb:0:16`: needs `adb reboot bootloader` (reboot is a device write).
- BROM `identify`, `backup` and `drill`: need a physical power-cycle with the action button
  held. The boot areas `boot0` and `boot1` are not exposed as `/dev` nodes (`force_ro=1`),
  so reading them over adb would need `mknod` (a device write) or BROM.
- Thread service run and RCP upload: not in the installed image; RCP reflash is deferred to
  the fresh unit by my decision.
- Announce device check with `0cc5507`: needs a new OTA (deferred) plus an HA send from me.
- Everything that replaces the installed boot chain (chain install, boot0/tee1/LK writes,
  fresh install) stays deferred to the fresh unit.
