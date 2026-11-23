# Phase 5 working notes

State at 2026-11-21: Phase 5 is closed. The hardware procedure ran to the end, step 6 passed
on run 7 and step 7 passed (`README.md`, "Hardware test procedure"); the gate is recorded in
`PLAN.md`, "Gate passed, 2026-11-21". The source is committed locally (see "Source state").

## Source state

All work is committed locally on `feature/lidar-support` (unpushed), 2026-11-21.

| Repo | Base commit | Phase 5 commits |
|---|---|---|
| `repos/LibreEcho-Platform` | `e917f8f95` | `620935f41d` (Lidar profile, A/B boot, audio-profile gate, OTA confirm fixes), `76608be064` (multi-target review pins) |
| `repos/LibreEcho-Linux` | `7594c5780db2` | `eef1f29ab9` (reboot mode, defconfig), `6046668bd5` (MUSB rx_kick) |
| `repos/LibreEcho` (Product) | `4f54459` | none |

The `experiment/lidar-adb-stability` and `experiment/lidar-musb-rx-kick` branches stay at
their bases; `feature/lidar-support` is the one branch that carries the Lidar work.

## Done on the host

Each line names who ran the check. "Worker" means a delegated agent reported it and Main has
not rerun it.

- Kernel (`repos/LibreEcho-Linux`): the `toprgu` node gains `syscon` and `simple-mfd` plus a
  `syscon-reboot-mode` child (offset 0x24, mask 0x4, mode-bootloader 0x4). The defconfig adds
  `SYSCON_REBOOT_MODE`, `USB_CONFIGFS_F_FS`, `BLK_DEV_LOOP`, `SQUASHFS` with LZ4, `TMPFS` and
  `IP_MULTICAST`. No `LIBREECHO_*` symbol exists. Outputs and build commands are in
  `artifacts/phase-05/kernel/` (`Image` 9ec709ff, `libreecho-lidar.dtb` eb8444d8). Worker
  build. The object directory `/tmp/lidar-p5-kbuild` is disposable.
- Shared runtime (`tools/mt8163-arm32/`): `libreecho-bootctl` has a `lidar` layout (policy
  table at `ota/libreecho_bootctl.c:88-96`, slotted) and a reboot-bootloader path that calls
  `reboot(RESTART2, "bootloader")` without touching `misc`. Init, update, target-manifest and
  update-fetch accept `lidar` with `soc=mt8167`. Vendor import reports not-applicable on
  Lidar. Worker ran these suites through `artifacts/phase-05/host-tools/run-host-tests.sh`
  (see `host-tests.md`): ota_v3_manifest 11 OK, issue_231 16 OK, ota_v3_integration 18 OK
  (with a Lidar install and confirm case), recovery_image_tools 193 OK, reboot_bootloader 11
  OK, multi_target RuntimeTargetTests 10 OK. Main ran the whole `test_multi_target` through the
  same wrapper on the working tree and on `git archive e917f8f95`: 16 failures and 1 error now,
  17 and 1 at base, and no test fails only on the working tree. The causes are the host (no
  `dtc`) and the legacy TWRP installer guard `bundle-on-userdata` rejecting the tests' staging
  path, both present at base.
- Lidar profile (`tools/mt8167-arm64/`): target table, ARM64 boot image builder and
  verifier reproducing `experiments/phase-04/pack_boot.py`, DTB verifier. Worker: 24 tests
  OK. A worker build with stand-in components passed the verifier with about 9.9 MB left in
  16 MiB; that image was deleted because its inputs were stand-ins.
- Installer (`tools/mt8167-arm64/install/`): `lidar_install.py` with `check`,
  `make-userdata`, `install`, `bcb show|set-active|reset`, `reboot`, and a fake fastboot for
  tests. Userdata is Android sparse with 4096-byte blocks covering 1205883 blocks.
  Main ran `python3 -m unittest -q` in that directory: 21 tests OK. The selftest images in
  `artifacts/phase-05/install-selftest/` use 4096-byte blocks; `evidence.txt` there records
  the 3584-byte slack, the label, the generation tree modes and `e2fsck -fn` rc 0.
- Lab OTA (`ota/`): `make_lab_ota.py`, `fetch_lab_assets.py`, and the delivery route in
  `ota/README.md` (adb push of the generation tree, then `libreecho-update install`; the
  pinned adbd has no `reverse`). Lab key in `artifacts/phase-05/ota/lab-key/`, never
  committed. Feature payloads are the published armv7 release assets, checked against that
  release's signed manifest. Worker checks: host-built verifier accepts the signature and
  rejects a one-byte change.
- Components, images and bundles (2026-11-18, Main): every `build_components.sh` target
  built, and `build_images.sh` built the dev, v1 and v2 images, each passing the Lidar
  verifier. Hashes, margins and checks are in `components.md`. The Lidar builder and
  verifier gained the UI bundle and mDNS runtime inputs (worker; 29 tests OK in
  `tools/mt8167-arm64`), which an `ota` production image needs to confirm a slot.
- Host tools: `artifacts/phase-05/host-tools/qemu/usr/bin/qemu-arm-static` (Arch
  qemu-user-static 11.1.3, signature checked; see `PROVENANCE.txt`). A static x86_64 BusyBox
  for the shell suites is under `artifacts/phase-05/host-tools/busybox/`.

## Carried to Phase 6

Open items that Phase 5 leaves behind:

- `libreecho-init:2842-2844` picks the first-install payload node from p10/p11. That is right
  for the slotted hypothesis and wrong if the hardware test shows `fixed-a`.
- PSCI `SYSTEM_RESET` (priority 129) runs before the MediaTek watchdog restart handler.
  Whether BL31 keeps the NONRST2 bit is a hardware measurement.
- Product's installer preflight (`repos/LibreEcho/tools/libreecho-install.py:988-1045`)
  assumes an exact multiple of 4096 bytes. That is Phase 7 integration work.
- After the run 7 confirm (`hw-20261118/step6-ota-run7/`), `libreecho-update status` still
  shows the stale `restart_record=1` with `reason=ota-health-confirm-failed` and
  `ota_transaction_state=rollback`, while `state=installed` and the slot is confirmed. The
  update daemon does not clear the pre-install failure record on confirm.
- Assistant and wake word stay off on Lidar until the Phase 6 audio work; the audio-profile
  gate keeps both out of the service graph without `/etc/libreecho/audio-profile`.
- `/run/libreecho/wifi-worker-failed` appeared in `after-state.log` after step 7
  (`hw-20261118/step7-reinstall/`) and has not been investigated.

## Next steps

1. Get approval for the device session in `README.md` ("Hardware test procedure") and run it.
2. Record each step's evidence, then decide on `fixed-a` handling if step 4 shows it.
3. Commit each repo once the hardware result is in, or earlier if asked.

## Research copies

`research/` holds the five scout reports from this session (platform build and runtime maps,
Lidar evidence map, Kaeru and BCB map, OTA and install contract). They cite `file:line` at the
base commits above.
