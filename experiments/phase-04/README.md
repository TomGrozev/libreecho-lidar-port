# Phase 4: LibreEcho-Linux kernel and DTB

This directory records Phase 4. [PLAN.md](../../PLAN.md) marks it complete with its
gate passed on 2026-11-17. `notes.md` is the detailed chronological log with the exact
commands, hashes and captures; this README indexes the directory so a reader can find
the right file.

## Prose documents

| File | Covers |
| --- | --- |
| `notes.md` | The 2,300-line chronological log of the whole phase: every host build, pack, flash, run and capture, with commands and hashes. |
| `plan-phase-4-journal.md` | The dated status journal `PLAN.md` carried while Phase 4 ran, frozen at the phase close (2026-11-17); a record, not instructions. |
| `fastboot-boot-research.md` | Read-only disassembly of the stock `cmd_boot` in the Lidar LK (`lk_a.bin`): the body is not in the image, only orphaned `.rodata`, so `fastboot boot` cannot be registered in Kaeru. |
| `lk-kernel-handover-research.md` | Why some Lidar images never reach `primary_entry`: analysis of the LK → kernel handover contract and the entry-probe results, ranking the experiments that would separate the hypotheses. |
| `no-uart-research.md` | Whether the boot chain can replace a serial console: Kaeru's `oem mem` read/write, the proven watchdog-reset-into-fastboot path, and the corrected `pstore_blk` run. |
| `usb-enumeration-research.md` | Primary-source research on USB gadget/UDC probe succeeding while the host never sees a connect, on MT8516/MT8167/MT8163, with experiments that isolate one factor at a time. |
| `lidar-mainline-comparison.md` | Comparison of our Phase 4 work with the independent lidar-mainline project; the source of the 2026-11-17 decision to drop ADB and adopt the ACM shell route. |

## Scripts and subdirectories

| File | What it does |
| --- | --- |
| `pack_boot.py` | Builds and verifies a 16 MiB development MTK/Android v0 boot image for the Lidar target from the stock image (read-only), a new ARM64 Image, a Lidar DTB and the stock ARM32 ramdisk; enforces the `bootopt` prefix, DTB size and initrd-property guards. Run as a host tool; see its docstring for options (`--ramdisk`, `--cmdline-append`, `--verify`). |
| `test_pack_boot.py` | Unit tests for the packager, no device access; invoked as `python3 -m unittest experiments/phase-04/test_pack_boot.py` per `../PLAN.md`. |
| `build_early_entry_probe.py` | Builds and verifies the minimal ARM64 LK-entry probe image: assembles `early_entry.S` and packs it with the stock image via `pack_boot.py`. |
| `acm_shell.py` | Host client for the USB CDC ACM root shell (`/dev/ttyACM*`): waits for the node, runs one command at a time with end markers, appends output to a log; `--usbfs` drives the gadget's ACM interface via raw usbfs instead. |
| `fb.sh` | `fb.sh <timeout-s> <args...>`: fastboot with the `LD_LIBRARY_PATH` of a saved android-tools build. The build itself is lab workspace material and is not archived. |
| `observe_usb.sh` | `observe_usb.sh <seconds> <logfile>`: reboots from fastboot, then timestamps every change in Lidar-related USB IDs and `ttyACM*` nodes. |
| `pstore_readback.sh` | `pstore_readback.sh <out.raw>`: waits for the Lidar U-Boot fastboot device, RAM-boots the pstore U-Boot image, and drains `pstore display` (all ramoops zones) into `<out.raw>`. |
| `uboot_manual_boot.sh` | `uboot_manual_boot.sh <log> <image> [boot]`: RAM-boots a `pack_boot.py` Linux image through a running U-Boot without `lidar_bootimg` (whose DTB pick fails on unaligned FDTs); stages the image, sets bootargs, and with `boot` jumps via `booti`. |
| `early_entry.S`, `early_entry_ram_marker.S`, `early_entry_ram_marker_reset.S` | Assembly sources for the early-entry probe images; `build_early_entry_probe.py` assembles `early_entry.S`. |
| `initramfs/` | The ARM32 test-initramfs build: `build_initramfs.sh` (full build, writes `artifacts/phase-04/initramfs`) and `repack_initramfs.sh <old.cpio.gz> <out.cpio.gz>` (repack with a new `./init` without rebuilding the toolchain). |
| `uboot/` | Second-stage U-Boot (arm64 Image packed as a boot image; never writes storage): `README.md` documents base, output and usage; `pack_uboot.py` does the packing; `dt-compare/` holds DTS diffs. |
| `pre-clean-control/` | Holds `full-worktree.patch`, the saved uncommitted probe/PHY patches from the USB clean control. |

## Hardware run directories

The `hw-YYYYMMDD-*` directories hold the captured logs and raw captures from each hardware
run, one directory per run; they are the hardware evidence. `hw-20261117-peripherals/`
holds the ACM shell captures for the peripheral bring-up image (`uname -a`, input devices,
I2C/LED probes in `acm-probe*.log`, `acm-buttons*.log`). `hw-20261117-lk-slot-source/` holds
the gate run of the source-built image: ACM diagnostics, the pstore marker (`marker.txt`,
`acm-mark.log`), a warm-reboot pstore readback and reboot logs. `hw-20261117-k1-fetch-diag/`
holds fastboot fetch/flash logs for the K1 image family, including the lk-slot-source fetch
and retries. The remaining `hw-20261117-uboot-*` and `*-wdt*`/`*-diag` directories hold
reboot-observe, host-dmesg and flash logs from the U-Boot and watchdog diagnostic runs.

## Evidence versus scratch

Evidence: everything in the `hw-*` run directories, the SHA-256 hashes and readback results
recorded in `notes.md`, and the built images in `artifacts/phase-04/` (with their
`.sha256` files). The regenerable scratch (the `build/` kernel tree and the `__pycache__/`
directories) was removed on 2026-11-17. The phase-4 boot images themselves now live in
`artifacts/phase-04/`; images superseded by later builds are under
`artifacts/phase-04/superseded/`.
