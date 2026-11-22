# Phase 5 boot shape decision

Date: 2026-11-17. Scope: documentation only. Nothing was built, flashed or run. All facts below
come from source reads and from earlier logs; none is new hardware evidence.

## Decision

The product path is Platform-native. Each LibreEcho image is one 16 MiB boot image in `boot_a`
or `boot_b`. Its initramfs carries the whole ARM32 userspace. The stock LK chooses the slot
through the Amazon BCB at `misc` offset 0x360, which `libreecho-bootctl` already writes.

The second-stage U-Boot (`repos/u-boot`, branch `lidar-fastboot-stage2`) stays a development
tool. It is flashed to a boot slot only during development, to RAM-boot candidate images with
`fastboot boot` and to read logs with `fastboot oem console`. It has no flash, erase or
environment support, and it is not part of a product image or an installation.

The owner accepted this recommendation on 2026-11-17.

## Inputs

| Source | Fact | Evidence |
|---|---|---|
| LibreEcho-Platform | A tools profile is a `tools/<soc-arch>/` directory plus a target table; there is no profile registry | `repos/LibreEcho-Platform/tools/mt8163-arm32/libreecho_platform_targets.py:31-45` |
| LibreEcho-Platform | Boot control is the 7-byte Amazon BCB at `misc` 0x360; the running slot comes from `androidboot.slot_suffix` | `tools/mt8163-arm32/ota/libreecho_bootctl.c`, `tools/mt8163-arm32/initramfs/libreecho-init` |
| LibreEcho-Platform | Install and recovery run from TWRP; the OTA bundle carries only `boot.img` | `tools/mt8163-arm32/recovery-install/README.md:3-40`, `tools/mt8163-arm32/ota/README.md` |
| LibreEcho-Platform | The dev kernel driver `echo_fastboot_marker.c` (`CONFIG_LIBREECHO_DEV_RECOVERY_MARKER`) resets both BCB slots to success=0 on every boot | `drivers/misc/mediatek/echo_fastboot_marker.c` |
| LibreEcho-Platform | A pinned ARM32 dropbear bundle exists | `tools/mt8163-arm32/ssh/` |
| Our unit | LK fell back from slot A to slot B through the BCB after a failed boot | `experiments/phase-04/notes.md:471-499` |
| Our unit | LK passes `androidboot.slot_suffix=_a` on a `boot_a` boot | `experiments/phase-04/hw-20261117-lk-slot-source/acm-diagnostics.log:19` |
| Our unit | The GPT has no `recovery` partition | `experiments/phase-01/brom-printgpt.log:125-140` |
| Our unit | Kaeru fastboot rejects `fastboot boot` | `experiments/phase-04/lidar-mainline-comparison.md` |
| Our unit | Our U-Boot enumerates USB fastboot and RAM-boots our kernel | `experiments/phase-04/notes.md`, U-Boot sections from line 1759 |
| lidar-mainline `4eac822` | The OS slot on ext4 holds only `/boot`; the userspace is still an initramfs | `reference/lidar-mainline/tools/mk-testimg.sh:247-272` |
| lidar-mainline `4eac822` | The Wi-Fi service copies firmware from Fire OS on `system_a` at every boot | `reference/lidar-mainline/tools/mk-testimg.sh:211-219` |
| lidar-mainline `4eac822` | U-Boot fastboot exposes every named GPT partition; no deny-list is enforced | `reference/lidar-mainline/lidar-uboot/configs/mt8516_amazon_lidar_defconfig:64-70` |
| lidar-mainline `4eac822` | The 7 commits after `35f8ba1` change only audio and userspace services | `git log 35f8ba1..4eac822` in `reference/lidar-mainline` |

## Why Platform-native

- It reuses `libreecho-bootctl`, `libreecho-update` and the signed OTA format. The reference
  shape needs a new boot control (`fw_setenv`), a new OTA payload and a new installer.
- LK slot boot is the path that passed the Phase 4 gate.
- The reference shape adds a second boot-control layer. LK still chooses between `boot_a` and
  `boot_b` through the BCB, and U-Boot in a boot slot has no A/B of its own.
- The reference shape writes `system_a`. That destroys the Fire OS firmware source that
  `libreecho-vendor-import` and the Phase 6 Wi-Fi firmware need.

## When to revisit

Adopt the reference shape (U-Boot in a boot slot, OS on `system_a`/`system_b` through extlinux,
U-Boot bootcount) only if one of these holds:

- The ARM64 kernel, DTB and ARM32 initramfs do not fit the 16 MiB envelope.
- LK's BCB handling cannot give a safe fallback on this chain.

Preconditions if it is adopted:

- U-Boot env offset: resolved from source. With `CONFIG_ENV_MMC_SW_PARTITION="misc"`, U-Boot
  puts both copies at the top of the partition and uses `CONFIG_ENV_OFFSET` only if it cannot
  find `misc` (`repos/u-boot/env/mmc.c:145-146,172-183`). `misc` is 0x80000 bytes at 0x1900000,
  so the absolute 0x1970000/0x1960000 and the partition-relative 0x70000/0x60000 name the same
  bytes. They do not overlap `misc[0:16]` or the BCB at 0x360. Not checked on hardware.
- A fastboot deny-list for expdb, `lk_*`, `tee*`, BOOT0/BOOT1, kb and dkb that we write
  ourselves, because the reference has none.
- An import of the Fire OS Wi-Fi firmware into userdata before the first write to `system_a`.
- A rule for how the LK BCB layer and the U-Boot bootcount agree.
