# Lidar Phase 5 evidence map

Echo Plus 2nd Gen (MediaTek MT8167, `product: LIDAR`). Compiled 2026-11-17 from the workspace
only: BROM logs, Phase 3/4 notes, `pack_boot.py` + tests, the preserved build outputs, the
initramfs build scripts, `acm_shell.py`, and the `LibreEcho-Linux` worktree. Nothing was run,
built or flashed for this report. `[INFERENCE]` marks reasoning not directly observed.

## 1. GPT as read live

Source: `experiments/phase-01/brom-printgpt.log:123-142` (same table, second read:
`experiments/phase-01/printgpt-live.log:3-22`). BROM handshake: MT8167/MT8516/MT8362, HW code
0x8167, target config 0xe5; DA `MTK_DA_V5.bin`, eMMC `Q2J95E`, USER size `0x1c8000000`
(`brom-printgpt.log:100-122`). All entries are `Type EFI_LINUX_DAYA`.

| # | Name | Start (bytes) | Start (MiB) | Length (bytes) | Size | UUID |
|---|---|---|---|---|---|---|
| 1 | kb | 0x00100000 | 1 | 0x00100000 | 1 MiB | <PARTUUID_1> |
| 2 | dkb | 0x00200000 | 2 | 0x00100000 | 1 MiB | <PARTUUID_2> |
| 3 | lk_a | 0x00300000 | 3 | 0x00100000 | 1 MiB | <PARTUUID_3> |
| 4 | tee1 | 0x00400000 | 4 | 0x00500000 | 5 MiB | <PARTUUID_4> |
| 5 | lk_b | 0x00900000 | 9 | 0x00100000 | 1 MiB | <PARTUUID_5> |
| 6 | tee2 | 0x00a00000 | 10 | 0x00500000 | 5 MiB | <PARTUUID_6> |
| 7 | expdb | 0x00f00000 | 15 | 0x00a00000 | 10 MiB | <PARTUUID_7> |
| 8 | misc | 0x01900000 | 25 | 0x00080000 | 512 KiB | <PARTUUID_8> |
| 9 | persist | 0x01980000 | 25.5 | 0x01000000 | 16 MiB | <PARTUUID_9> |
| 10 | boot_a | 0x02980000 | 41.5 | 0x01000000 | 16 MiB | <PARTUUID_10> |
| 11 | boot_b | 0x03980000 | 57.5 | 0x01000000 | 16 MiB | <PARTUUID_11> |
| 12 | swdl | 0x04980000 | 73.5 | 0x02000000 | 32 MiB | <PARTUUID_12> |
| 13 | system_a | 0x06980000 | 105.5 | 0x4c800000 | 1224 MiB | <PARTUUID_13> |
| 14 | system_b | 0x53180000 | 1329.5 | 0x4c800000 | 1224 MiB | <PARTUUID_14> |
| 15 | cache | 0x9f980000 | 2553 | 0x02000000 | 32 MiB | <PARTUUID_15> |
| 16 | userdata | 0xa1980000 | 2585 | 0x12667be00 | 4,939,301,376 B (~4.6 GiB) | <PARTUUID_16> |

- Disk: `0x1c8000000` bytes, `0xe40000` sectors (`brom-printgpt.log:142`). Userdata ends at
  `0x1c7ffbe00`; the remaining `0x4200` bytes are the backup-GPT area.
- There is **no `recovery` and no `preloader` GPT entry**. `preloader` appears only in fastboot
  `getvar all` (`partition-size:preloader: 40000`), i.e. from the boot-area/BCB view, not GPT.
- Fastboot agrees with the GPT and adds fs types
  (`experiments/phase-04/hw-20261117-k1-acm-flash/getvar-before.log:19-43`):
  `userdata 12667be00 ext4`, `cache 2000000 ext4`, `system_a/b 4c800000 ext4`,
  `persist 1000000 ext4`, `boot_a/b 1000000 raw`, `misc 80000 raw`, `expdb a00000 raw`,
  `tee1/tee2 500000 raw`, `lk_a/lk_b 100000 raw`, `kb/dkb 100000 raw`, `swdl 2000000 raw`.
  `max-download-size: 0x8000000` (128 MiB).
- `boot_a` and `boot_b` are exactly 16 MiB, so the decided 16 MiB boot envelope leaves no slack
  in the partition itself.

## 2. BCB / boot control: what the live evidence actually shows

### 2.1 The fallback and the repair (`notes.md:471-499`)

- First failed A boot (image `3d2997…`, no USB after reboot): LK subsequently selected B.
  Later `fastboot flash boot_a` writes plus reboots did not select A, so every later "normal
  boot" or "missing USB" observation is qualified: the device may have booted stock B
  (`notes.md:471-481`, `notes.md:446-451`).
- The A/B control path itself is unsupported by fastboot on this unit: `oem print-bcb` returns
  unknown-command, host `--set-active` says the device has no slots, raw `set_active:a` returns
  FAIL, `set_active:_a` timed out twice (`notes.md:482-484`).
- A fresh `misc` read held `00 41 42 42 01 8e 8f` at `misc+0x360` (`notes.md:488-490`). The
  owner changed exactly two bytes, `+0x365 8e→8f` and `+0x366 8f→8e`, producing
  `misc-slot-a.bin` SHA-256 `9248bd41…`; the read-back was byte-identical (`notes.md:493-495`).
- After that repair, BCB reads stayed `00 41 42 42 01 8f 8e 00` across several A boots
  (`notes.md:529-533`, `notes.md:553-555`, `notes.md:658`). No per-boot decrement of tries and
  no success-bit transition was observed. A is active and no A/B fallback happened in those
  runs.
- `boot_b` was never written by us (`notes.md:498-499`). It did change between 2026-11-10 and
  2026-11-15: kernel 6,227,391 B / ramdisk 4,118,507 B versus stock 6,227,381 / 4,117,193
  (`notes.md:236-241`). Cause unknown; "normal userspace automatic update" is offered as a
  possibility, not established. There is **no observed boot_b boot** and no `slot_suffix=_b`
  anywhere in the logs.

### 2.2 Decoding the bytes (correction to the notes' field labels)

`repos/kaeru/include/lib/bcb_amzn/bcblib.h:24-52` is authoritative for the struct:
`BCB_OFFSET 0x360`, `BCB_MAGIC 0x42424100` (bytes `00 41 42 42`), `version` at `+0x364`,
then a packed `struct bcb { uint32 magic; uint8 version; bcb_slot_metadata_t slot[2]; }` with
`{priority:4, tries:3, success:1}`. Therefore:

| Byte | Field | Value in `…01 8e 8f` | Value in `…01 8f 8e 00` |
|---|---|---|---|
| +0x365 | slot A metadata | 0x8e = prio 14, tries 0, success 1 | 0x8f = prio 15, tries 0, success 1 |
| +0x366 | slot B metadata | 0x8f = prio 15, tries 0, success 1 | 0x8e = prio 14, tries 0, success 1 |

Selection follows `bcblib_bcb_get_active_slot()` (`repos/kaeru/lib/bcb_amzn/bcblib.c:32-72`):
highest priority wins; success short-circuits; tries are consumed only when success is 0; the
other slot is used only if allowed. So the pre-repair bytes select **B** (priority 15 > 14) and
the repaired bytes select **A**. `[INFERENCE]` This fully explains the observed A→B fallback and
the A repair; it also means the notes' phrasing "priority 0x8e at +0x365, tries 0x8f at +0x366"
is a mislabel of two per-slot metadata bytes, not two fields of one slot. Kaeru also marks a
slot successful on BCB load when both slots are failed
(`repos/kaeru/board/amazon/board-mt8516-common.c:133-160`) and prints the same per-slot
priority/tries/success (`:66-73`).

`androidboot.slot_suffix=_a` is present in every live diagnostics cmdline captured on a
`boot_a` boot (`experiments/phase-04/hw-20261117-lk-slot-source/acm-diagnostics.log:19`, also
`hw-20261117-k1-lk-slot-initrd/acm-diagnostics.log:14`). No `_b` value exists in the workspace.

### 2.3 Not yet evidenced (Phase 5 must not assume)

1. Any actual `boot_b` boot or `androidboot.slot_suffix=_b`; therefore whether LK emits the
   slot suffix from the BCB selection at all, or always `_a`.
2. True A/B versus `fixed-a`: no update has flipped slots under our control, and no `system`
   slot has been selected/observed.
3. Whether this LK decrements tries on a failed boot, when it clears/sets success, and whether
   it writes the BCB back after a successful boot. The bytes never changed in our runs, but
   every observed slot had `success=1` already.
4. Boot from an invalid/empty slot, and the fallback order with both slots failing.
5. `misc[0:16]` / `misc[0:32]` as a fastboot command channel: **zero** evidence. Kaeru's
   fastboot reboot path is `device_fastboot_cmd_reboot` plus the WDT fastboot flag, and the
   stock `reboot`, `reboot-bootloader` and `set_active` registrations are NOPed in this board
   port (`experiments/phase-04/no-uart-research.md:77-83`). No code or log writes a command
   string at the start of `misc`.
6. BCB behaviour under a real OTA/`libreecho-bootctl` write; only manual byte editing is proven.

## 3. Kaeru fastboot on this unit

Entered by: holding the Action button, applying mains while held, then connecting USB with the
host listener already running (`experiments/phase-03/FASTBOOT.md:30-48`,
`experiments/phase-04/notes.md:286-289`). A USB-only warm reboot loses fastboot. Warm return
from Linux is proven via the stage-2 watchdog sequence: set `WDT_NONRST` bit 2 at
`0x10007024`, kick `0x1971`, write mode `0x22000014`, `SWRST 0x1209`; fastboot answered
~12–20 s later (`notes.md:672-680`, `no-uart-research.md:6-13`). **No misc marker is involved.**

Live-supported commands, with evidence:

| Command | Evidence |
|---|---|
| `getvar product` / `getvar all` / `getvar peek` | `hw-20261117-k1-acm-flash/getvar-before.log:1-48`; `notes.md:766` |
| `flash boot_a` | `hw-20261117-k1-fetch-diag/flash-peripherals-3.log:2-3`; `hw-20261117-k1-acm-flash/flash.log` |
| `oem fetch-enable`, `fetch boot_a` (16 × 1 MiB reads) | `hw-20261117-k1-fetch-diag/flash-only.sh:18-19`, `fetch-peripherals-3.log:2-18`; readback matched the flashed image |
| `oem peek <addr>` + `getvar peek` | `notes.md:766-769`, `:799` |
| `oem kaeru-version` | `getvar-before.log:47`; `notes.md:684` |
| `reboot` | `notes.md:207-208` and many flash logs |
| `oem mem read/write` | command exists and answers info, but live reads disconnected or hung; closed, do not retry (`notes.md:681-685`, `:736-740`) |
| `oem partitions`, `oem flags`, `oem idme`, `oem append-cmdline`, `oem reboot-recovery`, `oem reboot-wmfk` | registered strings only (`no-uart-research.md:77-79`); not exercised live here |
| `erase` | not seen used live; not relied on |

Rejections observed:

- `fastboot boot <img>` → `FAILED (remote: 'unknown command')`; device stayed in fastboot, no
  write, no boot (`notes.md:192-199`). LK rejected a later planned transient `fastboot boot` the
  same way (`notes.md:1095`). This is why every experiment is a `boot_a` flash + reboot.
- `oem print-bcb` → unknown command (`notes.md:482`).
- `set_active:a` → FAIL; `set_active:_a` → timeout; host `--set-active` → "no slots"
  (`notes.md:482-484`); `current-slot` is empty (`notes.md:198`).
- `oem mem` is unreliable on DRAM addresses (`notes.md:681-685`).

U-Boot's fastboot (development only) is the one that supports `boot`, `stage`, `oem run` and
`oem console` (`experiments/phase-04/uboot/README.md`, `notes.md:1920-1928`); do not confuse the
two.

## 4. `pack_boot.py`: the proven stock ARM64 envelope

`experiments/phase-04/pack_boot.py` (1204 lines). Header docstring `:1-33`; constants `:49-97`;
CLI `:1160-1204`. What a Phase 5 builder must reproduce:

### 4.1 Container

- Output exactly `IMAGE_SIZE = 16 * 1024 * 1024` (`:50`), `PAGE_SIZE = 2048` (`:49`).
- Android v0 header, `BOOT_HEADER_SIZE = 1632` (`:51`), magic `ANDROID!` (`:52`), header
  `header_version = 0`, `second_size = 0` (`:162-183`).
- Fixed addresses: kernel `0x40080000`, ramdisk `0x44000000`, second `0x40F00000`, tags
  `0x4E000000`, `os_version 0x0E04119C` (`:68-72`). These are validated, not derived (`:162-183`).
- Layout: header page, kernel section at page 1, ramdisk at
  `PAGE_SIZE + align_up(kernel_size, PAGE_SIZE)`, zero trailer
  (`:925-965`, `:998-1005`).
- Kernel section = stock 512-byte MTK header + deterministic gzip kernel + appended DTB
  collection. MTK header: `0x58881688`, size field = `kernel_size - 512`, name `KERNEL\0\0`,
  zero to `0x28`, `0xff` filler to 512 (`:61-64`, `:296-320`).
- Kernel input is a **raw ARM64 `Image`**, required to carry `ARMd` at `+0x38` (`:65-66`,
  `:404-410`). There is no `Image.gz` input path; the tool gzips the Image itself with a fixed
  header (`1f 8b 08 00`, mtime 0, XFL 2, OS 255), deflate level 9 (`:360-380`). Deterministic on
  the same host/zlib.
- `bootopt` prefix: the effective command line (cmdline + extra_cmdline joined as a bootloader
  would) must start with `bootopt=64S3,32N2,64N2`; LK needs it to pick the AArch64 handover
  (`:80-82`, `:240-255`). The stock header already has it; `--cmdline-append` appends one space
  plus text and keeps the prefix (`:206-232`).
- DTB: 19 appended blobs, stock index 4 replaced; all others byte-identical (`:74-75`,
  `:784-840`, `:1080-1100`). Stock index 4 must hash to `b5302d9e…` and be a Lidar PVT tree
  (`:76-79`, `:820-830`). New DTB must parse as FDT, its **first** root compatible must start
  with `amzn,lidar-`, and the list must contain `amzn,lidar-pvt` (`:82-83`, `:650-700`, `:900-915`).
  Every DTB blob must be ≤ `MAX_DTB_SIZE = 0x80000` because LK copies the selected DTB to
  `TAGS_ADDR` and fails beyond that (`:84`, `:753-760`).
- Initrd properties: `/chosen/linux,initrd-start` and `linux,initrd-end` are written as 8-byte
  big-endian (two-cell 64-bit) values derived from `ramdisk_addr` and the **actual ramdisk
  size** (`:653-700`). Rationale: LK copies the ramdisk to `0x44000000` on every boot but writes
  those properties only for IDME bootmode 2/0x61, so the image must publish them (`:24-28`).
  Verify requires them to match the header exactly (`:702-737`).
- Android id (`:257-268`): SHA-1 over kernel section, its size, ramdisk, ramdisk size, and a
  zero second size; recomputed on build and checked on verify.
- Trailer: deliberately zero; the stock DER certificate is not copied, no signature is made
  (`:998-1004`, `:1140-1150`).
- `--ramdisk FILE` requires one complete gzip stream whose newc archive has exactly one
  regular, executable `init` (`:390-410`); otherwise the stock ramdisk is copied unchanged.
- Size limits enforced: kernel section ≤ 0xFFFFFFFF field; `PAGE_SIZE + kernel_size ≤ 16 MiB`;
  `ramdisk_end ≤ 16 MiB`; each DTB ≤ 0x80000 (`:925-945`).
- Safety: refuses `--output` equal to the stock image or an input file (`:1130-1140`).

### 4.2 CLI

`--stock` (stock 16 MiB `boot_a.bin`, required), `--kernel` (raw ARM64 Image), `--dtb`,
either `--output` or `--verify IMAGE`, optional `--ramdisk`, `--cmdline-append`,
`--expected-pvt-sha256`. Exit 2 on any `PackError`. Host-only; it never touches hardware
(`:1160-1204`).

### 4.3 Test coverage (`test_pack_boot.py`, 999 lines, 43 tests from `:245`)

No device access; builds a synthetic 16 MiB stock image. Categories:

- Round trip; stock image unmodified; deterministic output; stock certificate dropped
  (`:319-374`).
- CLI pack/verify; CLI with `--ramdisk`; CLI with `--cmdline-append`; refuses to overwrite stock
  (`:375-480`).
- Default cmdline byte-identical; append across the 512-byte boundary; exact capacity and
  overflow; empty/NUL suffixes; verify detects missing/wrong suffix (`:482-613`).
- Ramdisk replacement and verify; ramdisk == stock produces identical bytes; missing `init`;
  `init` must be regular+executable; non-gzip rejected; verify detects tamper (`:615-823`).
- `/chosen` initrd properties derived from header; DTB already carrying them unchanged; verify
  rejects wrong `initrd-end` / missing `initrd-start` (`:653-743`).
- Retained trailer detected; changed DTB detected; wrong kernel; bad kernel magic; oversized
  kernel; malformed DTB; wrong compatible; first-compatible rule; oversized DTB; missing
  `bootopt`; `bootopt` survives append; wrong PVT hash; MTK filler at literal `0x28`
  (`:824-950`).
- Malformed stock headers; truncated stock; nonzero padding (`:951-999`).

Notes: `notes.md:129-160` states the tests cover a round trip, determinism, dropped certificate,
retained DTBs, tampered ramdisk/DTB/trailer, bad kernel magic, oversized kernel, malformed DTB,
wrong compatible, wrong PVT hash, malformed headers, truncation and nonzero padding.

### 4.4 Phase 5 builder checklist (from the above)

1. Keep 2 KiB pages, 16 MiB image, v0 header, one MTK `KERNEL` header and the fixed addresses.
2. gzip the raw ARM64 Image deterministically; never accept an already-gzipped kernel.
3. Keep all 19 stock appended DTBs and replace only index 4; enforce the `0x80000` cap.
4. Enforce `bootopt=64S3,32N2,64N2` at the head of the effective cmdline.
5. Force first root compatible `amzn,lidar-*` plus `amzn,lidar-pvt`.
6. Publish `/chosen linux,initrd-start/end` from `ramdisk_addr` + real ramdisk length.
7. Recompute the Android id; zero the trailer; verify every retained byte.

## 5. Kernel build and `LibreEcho-Linux`

### 5.1 Source state

- `repos/LibreEcho-Linux` HEAD: `.git/HEAD` → `refs/heads/feature/lidar-support`,
  `0x7594c5780db2ff3bc35083223c93d7926ebb4124` (matches PLAN's `7594c578`).
- Lidar DTS: `repos/LibreEcho-Linux/arch/arm64/boot/dts/mediatek/libreecho-lidar.dts`
  (`model = "LibreEcho Lidar"` `:26`; `compatible = "amzn,lidar-pvt", "amzn,lidar",
  "mediatek,mt8167"` `:32`; `/chosen { stdout-path = "serial0:921600n8" }` `:44-47`; ramoops
  `0x43810000` `:79-90`; memory `0x40000000..0x7f9c0000` `:59-63`; PMU disabled `:96-100`).

### 5.2 Recorded build (`notes.md:73-89`, unchanged since)

```sh
export PATH=/tmp/lidar-arm64-tools/root/usr/bin:$PATH
export LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 olddefconfig
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 Image dtbs -j8
```

Toolchain: Arch clang/lld/llvm-ar and dtc 1.8.1 (clang 23.1.5). For the later gate and
peripheral builds the command is the same with `-j16`/`-j12`
(`notes.md:2042-2044`, `:2107-2108`, `:2185-2186`).

### 5.3 Archived outputs

`artifacts/phase-04/kernel-build/`:

| File | Observed size | Notes |
|---|---|---|
| `arch/arm64/boot/Image` | ~8.0 MB (directory listing; byte count not recorded anywhere) | Not one of the recorded gate kernels |
| `arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb` | 13.5 KB | matches `kernel-build/libreecho-lidar.dtb` 13.4 KB |
| `System.map` | 1.3 MB |  |
| `.config` | 73.1 KB | resolved config for the archived build |
| `Image.gz` | absent | the tool gzips `Image` itself |

Recorded sizes of other Phase 4 kernels: gate images 9,380,352 B
(`notes.md:2072`, `:2114`), first peripherals image 5,577,329 B (`notes.md:2194`). The
archived generic `Image` (~8.0 MB) therefore **does not match the gate or peripherals kernels**;
treat it as a generic build artifact and rebuild for Phase 5. `[INFERENCE]`

### 5.4 Rebuild feasibility

- Yes, from the recorded commands, in a fresh `O=` directory: the source, defconfig, DTS and
  Makefiles are present and HEAD is the recorded commit.
- The preserved clang tree is
  `artifacts/phase-04/tmp-20261115/lidar-arm64-tools/root/usr/bin` (clang 23.1.5, dtc 1.8.1,
  Android tools). It contains **no `ld.lld` and no `llvm-*`** binaries; `LLVM=1` therefore
  needs the host `/usr/bin` `ld.lld`, `llvm-ar`, `llvm-nm`, `llvm-objcopy`, which exist on this
  workstation. `tmp-20261115/README.md:8-28` gives the exact resume sequence.
- The dtschema venv and stock/current DTS copies are preserved
  (`tmp-20261115/lidar-dtschema`, `libreecho-stock-lidar.dts`, `libreecho-stock-pvt.dts`).
- The Phase 4 build trees were deleted on 2026-11-17 (`artifacts/phase-04/README.md:20-38`);
  /tmp currently still holds `lidar-periph-build`, `lidar-lk-slot-source-build`,
  `lidar-feature-align`, etc., but do not depend on them.

### 5.5 Defconfig contents (`arch/arm64/configs/mt8167_arm64_defconfig`, 120 lines)

Set: `BLK_DEV_INITRD` (:9), `COMPAT` (:14), `ARM64_VA_BITS_39` (:16), `DEVTMPFS` +
`DEVTMPFS_MOUNT` (:27-28), 8250/MT6577 console (:31-33), `MFD_SYSCON`/`COMMON_CLK_MT8167`/
`PINCTRL_MT8167` (:36-39), input/gpio-keys (:42-44), I2C (:47-49), LEDs (:52-54), sound
codecs (:58-63), `MMC`/`MMC_MTK` (:66-68), MUSB + configfs ACM/NCM (:71-80), `PHY_MTK_TPHY`
(:81), regulators (:84-87), pstore ram/console/pmsg (:90-94), watchdog (:97-99), `EXT4_FS`
(:101).

Not set / absent: **`CONFIG_LIBREECHO_DEV_RECOVERY_MARKER` and every other `CONFIG_LIBREECHO_*`**,
squashfs, overlayfs, f2fs, modules. XZ is not named in the defconfig but the resolved
`.config` enables `CONFIG_RD_XZ=y` (:152) and `CONFIG_XZ_DEC=y` (:2585); `CONFIG_OVERLAY_FS` is
not set (:2165), `CONFIG_SQUASHFS` not set (:2218), `CONFIG_MODULES` not set (:609),
`CONFIG_INITRAMFS_SOURCE=""` (:148). Consequence for Phase 5: an xz initramfs is readable by
the current kernel, but squashfs/overlay userspace images are not supported without a config
change.

## 6. Test initramfs

### 6.1 Build

`experiments/phase-04/initramfs/build_initramfs.sh` (host-only, pinned sources, sha256 aborts):

- Toolchain: stock Arch clang/lld/llvm-ar 23 (no ARM gcc, no sudo) (`:1-13`, `:20-33`).
- musl 1.2.5 cross-built as `armv7a-linux-musleabihf`, `--disable-shared --enable-static`
  (`:65-80`); compiler-rt builtins built from matching llvm-project 23.1.5, only `lib/builtins`
  (`:96-119`); a `armv7-gcc` wrapper drives `clang -fuse-ld=lld -nostdlib` with musl crt/libc/
  libm plus builtins, `-idirafter /usr/include` for UAPI headers (`:124-143`).
- BusyBox 1.37.0, `CONFIG_STATIC=y`, `CONFIG_CTTYHACK=y`, `CONFIG_DEVMEM=y`, PIE off
  (`:168-190`, config `busybox-1.37.0.config`).
- Packaging: staged root → kernel tree `usr/gen_init_cpio -t 0 initramfs.list` → `gzip -n -9`
  (`:192-206`); checks the ELF is ARM EABI5 hard-float, no interpreter, and 53 applets
  (`:208-240`). Outputs `artifacts/phase-04/initramfs/*.cpio.gz` + `MANIFEST.txt`.

### 6.2 Contents

`initramfs.list`: dirs `/bin /dev /dev/pts /proc /sys /tmp(01777) /pstore-prev`; `file /init
0755`; `file /bin/busybox 0755`; nodes `/dev/console c5,1 0600`, `/dev/null c1,3 0666`; ~65
applet symlinks (sh/ash, mount, ip, setsid, cttyhack, getty, hexdump, devmem, dmesg, etc.).

`init` (busybox ash, PID 1): mounts proc/sys/devtmpfs/devpts/configfs/pstore, copies prior
`/sys/fs/pstore/*` to `/pstore-prev` (`:30-50`); builds configfs gadget `g1` `1d6b:0104`,
bcdUSB 0x0200, `acm.usb0` + `ncm.usb0` linked into `c.1`, MaxPower 250, serial from
`/proc/device-tree/serial-number` with fallback `LIDAR0001`, retries 30 s for a UDC (`:52-100`);
brings up `usb0`, keeps IPv6 link-local, adds `169.254.42.1/16` (`:102-130`); spawns a
respawned root shell on `/dev/ttyGS0` with `setsid -c sh` and an optional `/dev/console` shell,
optionally arms `reboot -f` after `lidar.autoreboot=<s>` from the cmdline, then reaps forever
(`:132-175`). `getty` is only a symlink; the shell is started directly.

### 6.3 Sizes and hashes

| Artefact | Bytes | SHA-256 |
|---|---|---|
| first build `lidar-test-initramfs.cpio.gz` | 682,342 | `7b4a7c85…` (`notes.md:1627`) |
| control repack `lidar-test-initramfs.cpio.gz` | 682,618 | `07f6b9b8…` (`MANIFEST.txt`, `notes.md:1916`) |
| `lidar-test-initramfs-setsid.cpio.gz` | ~682.7 K (file 666.7 KiB) | `fcbf9cb2…` (`notes.md:1916`) |
| uncompressed cpio | ~1.1 MB (`/tmp/lidar-irf/initramfs.cpio`) | not recorded |
| static busybox | 1.1 MB | `81f1db89…` (`MANIFEST.txt`) |

Compression is gzip `-n -9` over `gen_init_cpio` newc output with epoch-0 mtimes; two
consecutive builds are byte-identical (`notes.md:1629-1631`). The `setsid` archive exists
because the first init used `cttyhack` on ttyGS0 and the shell only echoed; `init` now uses
`setsid -c` (`notes.md:1908-1918`).

### 6.4 Local ARM32 toolchain

- No ARM GCC is installed. The only local ARM32 toolchain is the ephemeral work dir
  `/tmp/lidar-irf/`: `sysroot/usr/lib/libc.a` (2.2 MB musl), crt objects, `wrappers/armv7-gcc`,
  `armv7-ld`, llvm-tool symlinks, `builtins-arm/lib/linux/libclang_rt.builtins-armhf.a`
  (173.8 KB), `busybox-out/busybox` (1.1 MB), sources and pinned downloads.
- It is **not** under `artifacts/`; a reboot of the workstation loses it, but
  `build_initramfs.sh` recreates it from the pinned tarballs with host clang/lld.
- Host tools present: `/usr/bin/clang`, `ld.lld`, `llvm-ar`, `llvm-nm`, `llvm-objcopy`.

## 7. ACM shell and the development link

`experiments/phase-04/acm_shell.py` (285 lines):

- Waits for `/dev/serial/by-id/*` or `/dev/ttyACM*` (`:73-90`), opens it raw
  (`O_NOCTTY|O_NONBLOCK`, `tty.setraw`, speed 115200 which the gadget ignores) (`:146-170`).
- Protocol: writes `"<cmd>; echo __ACM_END_<n>__\n"`, reads until the marker appears twice
  (gadget echo) or once plus 2 s silence, appends everything to `--log` (`:190-235`).
- Default commands: `uname -a`, `/proc/cmdline`, `/proc/cpuinfo`, `dmesg`, pstore listings and
  contents (`:36-41`).
- `--usbfs` fallback drives CDC ACM through raw usbfs ioctls (claim interface class 02/02 and its
  paired data interface, bulk IN/OUT, `SET_CONTROL_LINE_STATE` DTR|RTS), used because the host
  kernel has no `cdc_acm` module; access via a udev rule (`notes.md:1925`).
- CLI: `--device`, `--usbfs`, `--log`, `--wait` (default 120 s), `--timeout` (30 s), positional
  commands (`:240-285`).
- Dev link as built: configfs `acm+ncm` gadget `1d6b:0104`, root shell on `ttyGS0`, NCM
  `usb0` with IPv6 link-local plus `169.254.42.1/16`. Only the ACM shell was actually used in
  the successful captures; NCM/SSH was prepared but not exercised on this unit
  (`notes.md:1620-1645`, `:1920-1932`).

## 8. Direct answers to the planning questions

1. **GPT**: table above; userdata `0x12667be00` (~4.94 GB, ext4); boot slots 10/11, misc 8.
2. **BCB**: A→B fallback observed, repair proven, `_a` only, no boot_b boot; per-slot metadata
   decode corrected; tries/success semantics and `misc[0:16]/[0:32]` remain unevidenced.
3. **Fastboot**: getvar/flash/fetch/fetch-enable/oem peek/kaeru-version/reboot work;
   `fastboot boot` rejected; entry is Action+mains, warm return is WDT bit 2; no misc marker.
4. **Envelope**: rules and builder checklist in §4.
5. **Kernel**: HEAD `7594c578…`; defconfig has compat/ext4/devtmpfs, no marker/squashfs/
   overlay; archived Image ~8.0 MB is not the gate kernel; rebuild is feasible with preserved
   clang + host lld.
6. **Initramfs**: musl/clang/busybox static, gzip -n -9, ~682 KB compressed / ~1.1 MB
   uncompressed; ARM32 toolchain only in `/tmp/lidar-irf`.
7. **ACM**: ttyGS0 root shell + usbfs/tty helper; NCM link built but unused.
