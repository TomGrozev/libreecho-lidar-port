# Phase 5: LibreEcho-Platform and recovery on Lidar

This directory holds Phase 5: the design, the host tooling records and the hardware test
procedure.
`PLAN.md` Phase 5 sets the scope and the gate. `boot-shape-decision.md` records the
accepted boot shape: one 16 MiB LibreEcho boot image in `boot_a` or `boot_b`, chosen by the
stock LK through the Amazon BCB at `misc` 0x360.

Status: complete, 2026-11-21. I ran steps 1 to 7 on hardware; step 6 passed on run 7 and
step 7 passed (see the procedure below). The Phase 5 gate is closed (`PLAN.md`, "Gate
passed, 2026-11-21").

## Design

### Profile

`repos/LibreEcho-Platform/tools/mt8167-arm64/` is a thin profile. It holds the Lidar target
table, the ARM64 boot image builder and verifier, the Lidar DTB verifier and the install
tooling. The ARM32 userspace (init, updater, `libreecho-bootctl`, BusyBox, adbd) is the same
code the MT8163 profile ships. The Lidar builder imports the staging code and sources from
`tools/mt8163-arm32/` instead of copying them, so one fix reaches both boards. The runtime
tells the boards apart by the partition layout and `/etc/libreecho/target`, never by `uname`.

### Storage contract

The live GPT (`experiments/phase-01/brom-printgpt.log:123-142`) gives these partitions, in
512-byte sectors. The partition number is the GPT index.

| p | name | sectors | written by LibreEcho |
|---|---|---|---|
| 1 | kb | 2048 | never |
| 2 | dkb | 2048 | never |
| 3 | lk_a | 2048 | never |
| 4 | tee1 | 10240 | never |
| 5 | lk_b | 2048 | never |
| 6 | tee2 | 10240 | never |
| 7 | expdb | 20480 | never (holds the Kaeru LK stage) |
| 8 | misc | 1024 | BCB at 0x360 only |
| 9 | persist | 32768 | never |
| 10 | boot_a | 32768 | image slot A |
| 11 | boot_b | 32768 | image slot B |
| 12 | swdl | 65536 | never |
| 13 | system_a | 2506752 | never (Fire OS firmware source) |
| 14 | system_b | 2506752 | never |
| 15 | cache | 65536 | never |
| 16 | userdata | 9647071 | ext4 `LIBREECHO_DATA` |

The MT8163 `misc` is 1025 sectors and its p12 is `recovery`, so `libreecho-bootctl` can tell
the two layouts apart before it writes anything. The Lidar userdata size is inside the
existing floor rule (2137088 to 33554432 sectors), so `libreecho-init` accepts it once the
label is `LIBREECHO_DATA`.

### Boot control

Later (2026-11-21): the hardware test settled this. The chain is true A/B with an LK
tries fallback from B to A, and `androidboot.slot_suffix` is reported for both
slots; `misc[0:32]` is inert. Evidence is in "Reboot to fastboot" below and
`hw-20261118/`, and PLAN.md Phase 5 records the same result. I kept the hypothesis
paragraph that follows as I wrote it at the time.

`libreecho-bootctl` gets a third layout, `lidar`. It starts as `boot_store_mode=slotted`:
slot A loads `boot_a` (p10) and slot B loads `boot_b` (p11). This is a hypothesis. No
recorded boot shows `androidboot.slot_suffix=_b`. The recorded A to B change came from a
priority change, not from a tries fallback: both slots had the success bit set
(`experiments/phase-04/notes.md:470-500`). The first hardware test measures it: two different
images in the two slots, a switch to B, and a check of the running image identity. A
`fixed-a` result changes one table entry.

### Reboot to fastboot

The `misc[0:32]` bootloader message is inert on Lidar. The route I proved is the watchdog
flag: bit 2 of TOPRGU `0x10007024` (NONRST2) survives a watchdog reset, and stock LK then
enters fastboot (`experiments/phase-04/notes.md:690-735`). The kernel exposes it as the reboot mode
`bootloader` through `syscon-reboot-mode`. `libreecho-bootctl reboot-bootloader` on the
`lidar` layout calls `reboot(LINUX_REBOOT_CMD_RESTART2, "bootloader")` and writes nothing to
`misc`. The manual route stays the Action button held at power-on.

### Install and recovery

The unit has no TWRP and no `recovery` partition. Stock LK cannot load a third image.
Kaeru fastboot is the recovery floor: it can flash and read back partitions, and it cannot
`boot` an image.

The host installer talks to Kaeru fastboot. It checks the product and every partition size
against the storage contract before any write. It flashes only `boot_a`, `boot_b` and
`userdata`; `misc` is written only for an explicit BCB reset. It never writes `system_a` or
`system_b`. Every boot slot write gets a full readback through `fetch`.

Userdata gets its first format from the host: the installer flashes a sparse ext4 image
labelled `LIBREECHO_DATA`. The filesystem fills the 1205883 whole 4096-byte blocks that fit in
the partition and leaves the last 3584 bytes unused; `libreecho-init` checks the partition
size and the label, not the filesystem size. Stock Android formats userdata over fastboot the
same way, and it keeps format code out of the booted image, which by design never formats.

### Kernel

`CONFIG_LIBREECHO_DEV_RECOVERY_MARKER` stays out of the Lidar kernel, and the Lidar builder
refuses a kernel config that sets it.

## Size budget

The Lidar builder and verifier measure this (`components.md`). The 16 MiB slot holds the
MediaTek envelope, the gzip kernel (4,603,491 bytes), the 19 stock DTBs plus the Lidar DTB
(1,024,374 bytes) and the xz initramfs.

| Image | xz initramfs | Left in 16 MiB |
|---|---|---|
| development, diagnostic, UI | 2,897,876 | 8,247,296 |
| ota, production, UI, mDNS | 5,382,724 | 5,761,024 |

The boot shape fits with 5.5 MiB to spare.

## Hardware test procedure

Images and bundles are in `artifacts/phase-05/images/` and `artifacts/phase-05/ota/`. Logs
and readbacks go to `experiments/phase-05/hw-<date>-<step>/` and `dumps/<date>-lidar-phase5/`.
Every write and reboot below needs your approval before the session; the stock backup in
`dumps/20261110-lidar-readback/` stays untouched, and BOOT1 is never written.

1. Fastboot entry and baseline (read-only). Power cycle with Action held. Run
   `lidar_install.py check` and `bcb show`, and fetch `boot_a`, `boot_b` and `misc` into the
   dump directory.
2. Install (writes `boot_a`, `boot_b`, `userdata`, `misc`). `install --boot
   boot-lidar-v1.img --boot-b boot-lidar-dev.img --userdata userdata-plain.simg --yes`, then
   `bcb reset`. The tool reads back both slots and the userdata prefix.
3. Boot slot A (reboot). Expect `/proc/cmdline` with `androidboot.slot_suffix=_a` and
   `libreecho.lab=v1`, `/data` mounted, and after the health rounds
   `libreecho-bootctl status` showing `slot_a_success=1`. Save the boot log and pstore.
4. Slot B and fallback (reboots). `libreecho-bootctl activate b`, reboot. Expect `_b` and
   `libreecho.lab=dev`. The development image never confirms, so record the BCB tries after
   each reboot until LK returns to slot A. This answers true A/B against `fixed-a` and how LK
   spends tries.
5. Reboot to fastboot (reboot). From slot A, `libreecho-bootctl reboot-bootloader`. Expect
   Kaeru fastboot (`getvar kaeru-version` answers) and `misc[0:32]` unchanged. Then
   `fastboot reboot`.
6. OTA v1 to v2 (writes `boot_b` and `misc` from the device, then reboot). Follow
   `ota/README.md` with `artifacts/phase-05/ota/lab-v2/` and transaction
   `txn-066a320ff6fab7e41606de1d` (bundle `lidar-lab-v0.2.6.ota.tar`). Expect slot B with
   `libreecho.lab=v2`, a confirmed slot and `libreecho-update status` naming that generation.
   The bundle and transaction named here date from when this procedure was written; the
   failed runs below led to rebuilt bundles, so the passing run used later versions.

   **Result: PASS on run 7 (2026-11-21).** Evidence in `hw-20261118/step6-ota-run7/`. The
   device ran the v1 bundle `lidar-lab-v0.2.11.ota.tar` (transaction
   `txn-65c78379f4bb2fced5b2249a`, `artifacts/phase-05/ota/lab-v1/`) and installed the v2
   bundle `lidar-lab-v0.2.12.ota.tar` (transaction `txn-508529626fbd711fdbf6bf1c`,
   `artifacts/phase-05/ota/lab-v2/`). `events.log`: install at 10:05:16
   (`verify_rc=0 ota_manifest_signature=PASS UPDATE_READY slot=b version=0.2.12`), booted
   `_b` at 10:05:29 (`libreecho.lab=v2 androidboot.slot_suffix=_b`), confirmed at 10:08:46
   (`slot_b_success=1`). `confirmed-state.log`: `slot_b_success=1`, `state=installed`,
   `current=txn-508529626fbd711fdbf6bf1c` (the current generation),
   `features_state=ready`, and `/run/libreecho/startup-ready` present. Boot image hashes are
   the 2026-11-19 rebuild in `artifacts/phase-05/images/SHA256SUMS`.

   Runs 1 to 6 failed before confirm; each failure produced a gate now in the images:

   | Run | Failure | Cause | Fix |
   |---|---|---|---|
   | 1 | `agentd` needs the audio socket | assistant service required `audio.sock` with no audio profile on Lidar | audio-profile gate: a target without `/etc/libreecho/audio-profile` neither requires nor starts the local assistant |
   | 2, 3 | startup-ready never reported | the esphome probe blocked readiness, and the last-try slot check ran outside its window | `esphome_service_ready` integration-bit gate; `read_bcb` last-try window fix |
   | 4, 5 | init health check failed | init health required `agent.sock`, which the audio gate keeps absent | init health no longer requires `agent.sock` on targets without an audio profile |
   | 6 | `waked` blocked startup | wake word needs mic calibration before it can run | wake word gated on the audio profile, so it stays off with no audio profile |

   Assistant and wake word stay off on Lidar until Phase 6 audio work
   (`PLAN.md` Phase 6 item); the feature catalog still reports both payloads as
   `effective=present`.

   Known issue: after the successful confirm, `libreecho-update status` still shows the
   stale `restart_record=1`, `reason=ota-health-confirm-failed` from the pre-install state
   and `ota_transaction_state=rollback`, even though `state=installed` and the slot is
   confirmed. Tracked in `notes.md`.
7. Reinstall from the recovery floor (writes `boot_a`, `boot_b`). Power cycle with Action
   held, then `install --boot boot-lidar-v1.img --boot-b boot-lidar-v2.img --yes` without
   userdata; check that `/data/libreecho` survives the next boot.

   **Result: PASS (2026-11-21).** Evidence in `hw-20261118/step7-reinstall/`. `install.out`
   flashes v1 to `boot_a` and v2 to `boot_b`, with both readbacks matching the source
   hashes (`9da8886c...`, `7e73d1b8...`). `bcb-before-reboot.out` shows the BCB selecting
   slot b with `slot_a_success=1` and `slot_b_success=1`. `before-data.log` and
   `after-data.log` show `/data/libreecho` unchanged across the reinstall: the config and
   generation files are byte-identical, and the only differences are the mtimes and the
   rolling contents of `update/boot-count`, `boot-history`, `boot-health`, `rolled-back` and
   the new `authority-provenance-cache`. `after-state.log` shows the device booted slot `_b`
   with `libreecho.lab=v2`, `/data` mounted, `state=installed`,
   `features_state=ready` and `/run/libreecho/startup-ready` present (it also shows the
   known stale `ota_transaction_state=rollback` and the unexamined
   `/run/libreecho/wifi-worker-failed`). `web-ui.png` is the web UI served from the device
   on port 8080 through an adb forward. The gate is closed.

The gate closes when steps 2 to 7 produce the expected evidence. If a step fails, I record
it as a result.

## Files

| File | Content |
|---|---|
| `boot-shape-decision.md` | accepted boot shape and when to revisit it |
| `components.md` | ARM32 component and toolchain build record |
| `build_components.sh` | component builds, one target per call |
| `build_images.sh` | builds and verifies the dev, v1 and v2 images |
| `host-tests.md` | how the shell test suites run on this host |
| `notes.md` | working state, open issues, next steps |
| `ota/` | lab OTA emitter, asset fetcher and the adb delivery route |
| `research/` | scout reports with `file:line` evidence at the base commits |
