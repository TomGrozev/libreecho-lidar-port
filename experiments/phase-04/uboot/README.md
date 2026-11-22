# Second-stage U-Boot for Amazon Echo Plus (2nd gen), "lidar"

A U-Boot built as an arm64 Linux Image, packed into an Android boot image that
the stock Amazon LK (with Kaeru 2.0.0 patches) loads from `boot_a` exactly like
a kernel.  It exposes USB fastboot with RAM boot of our Linux boot images and
`reboot`, and never writes storage.

## Base

| | |
|---|---|
| Upstream | https://source.denx.de/u-boot/u-boot.git (GitHub mirror) |
| Tag | `v2026.10` |
| Commit | `5508406582f6f7120dce0c4b3059819a41788db2` |
| Branch | `lidar-fastboot-stage2` |
| Build tree | `repos/u-boot` |

See `BASE.md` for how the tree was obtained.

## Output

`artifacts/phase-04/uboot/u-boot-boot.img` (16 MiB, boot_a layout)

```
3840afb63303f02e02210ee5a0c9743aded06a87cb2d66340b182866405dea86
```

`SHA256SUMS` holds the same digest.  The image is *not* a signed FIT and
contains no ramdisk of its own: it reuses the stock ramdisk and cmdline.

Current diagnostic image (RAM breadcrumbs, GCC build):

```
artifacts/phase-04/uboot/u-boot-boot-gcc-crumbs.img   16 MiB
e9dfc9edaeba0faf41be2cd245a40528a024b246c08d01813fa9991e6ea0d578
```

The earlier clang image (`u-boot-boot.img`) and the first GCC image
(`u-boot-boot-gcc.img`) are kept for reference; the crumbs image supersedes
them for the next hardware test.

## Build

The host has clang/LLD but no aarch64 GCC.  U-Boot's arm64 port is
`ARCH=arm`; `ARCH=arm64` is a kernel-ism and fails on `asm/config.h`.
`CROSS_COMPILE=aarch64-linux-gnu-` is needed because U-Boot only derives
clang's `--target` from it (Makefile:650-666).  `fdtoverlay` is built in the
output tree, so that directory must be on `PATH`.

```sh
cd repos/u-boot
make O=/tmp/lidar-uboot-build3 ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- \
  CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy \
  OBJDUMP=llvm-objdump STRIP=llvm-strip READELF=llvm-readelf HOSTCC=cc \
  mt8516_lidar_defconfig

PATH=/tmp/lidar-uboot-build3/scripts/dtc:$PATH \
make O=/tmp/lidar-uboot-build3 ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- \
  CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy \
  OBJDUMP=llvm-objdump STRIP=llvm-strip READELF=llvm-readelf HOSTCC=cc \
  KCFLAGS="-fintegrated-as -fno-stack-protector \
           -Wno-incompatible-function-pointer-types \
           -Wno-deprecated-non-prototype" \
  KAFLAGS="-fintegrated-as -fno-stack-protector" \
  -j16
```

The `KCFLAGS` workarounds are host-toolchain only: U-Boot hard-codes
`-no-integrated-as` and clang 23 turns a missing external assembler into a
hard failure; clang 23 also rejects an upstream `const`-qualified MediaTek clk
ops initializer and the K&R prototypes in `lib/zlib`.  `-fno-stack-protector`
avoids `__stack_chk_guard`, which U-Boot does not provide.

Outputs: `u-boot-nodtb.bin` starts with the arm64 Image header
(`text_offset` 0x80000, `ARM\x64` at 0x38); `u-boot.bin` is
`u-boot-nodtb.bin + u-boot.dtb` (CONFIG_OF_SEPARATE).  The packer consumes
`u-boot-nodtb.bin` and `u-boot.dtb` separately so the control DTB is inside
the gzip stream once.

## Pack

```sh
python3 experiments/phase-04/uboot/pack_uboot.py \
  --uboot-bin /tmp/lidar-uboot-build3/u-boot-nodtb.bin \
  --uboot-dtb /tmp/lidar-uboot-build3/u-boot.dtb \
  --stock dumps/stock/boot_a.bin \
  -o artifacts/phase-04/uboot/u-boot-boot.img
```

Layout produced (Android boot v0, page 2048):

```
header: kernel_addr 0x40080000, ramdisk_addr 0x44000000,
        tags_addr 0x4e000000, second_size 0, header_version 0
kernel field: 512-byte MTK header (magic 0x58881688, "KERNEL")
              + gzip(u-boot-nodtb.bin + u-boot.dtb)
              + u-boot.dtb          # LK's backwards FDT scan finds this
ramdisk: stock boot_a ramdisk, unmodified
cmdline: stock boot_a cmdline
sha1 id: computed over kernel, ramdisk, second
```

Verified on the host: MTK magic and sizes, gzip round-trips to
`u-boot-nodtb.bin + u-boot.dtb` (481176 bytes), appended DTB byte-identical,
first root compatible `amzn,lidar-pvt`, ramdisk byte-identical to stock.
`pack_boot.py` and its default output are unchanged.

## Breadcrumb log and the GCC diagnostic image

The first GCC flash (`u-boot-boot-gcc.img`) produced no USB and a warm reset
at ~67 s.  To separate "LK never jumped" from an early U-Boot hang, the image
now writes a crash-surviving ASCII log to `0x43810000..+0x60000`, the window
Kaeru reads back as `ramoops`.

GCC 16.2 (`aarch64-linux-gnu-gcc`, now installed) is the working builder for
this image; `.bss` is at 0x400e4558 and the Image header `image_size` is sane
(0xe4558).  The clang build linked `.bss` at 0 and produced a negative header
size, so it is no longer the diagnostic build.

```sh
cd repos/u-boot
make O=/tmp/lidar-uboot-gcc-crumbs ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- \
  mt8516_lidar_defconfig
PATH=/tmp/lidar-uboot-gcc-crumbs/scripts/dtc:$PATH \
make O=/tmp/lidar-uboot-gcc-crumbs ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- -j16

python3 experiments/phase-04/uboot/pack_uboot.py \
  --uboot-bin /tmp/lidar-uboot-gcc-crumbs/u-boot-nodtb.bin \
  --uboot-dtb /tmp/lidar-uboot-gcc-crumbs/u-boot.dtb \
  --stock dumps/stock/boot_a.bin \
  -o artifacts/phase-04/uboot/u-boot-boot-gcc-crumbs.img
```

Log format (little endian): bytes 0..3 `LUBT`, u32 write offset at 4, u32
marker sequence at 8, u32 version at 12; ASCII from byte 16.  Markers look
like `@LIDAR <tag> v=0x... pc=0x...`.  The first marker is written by
`save_boot_params` in `board/libreecho/lidar/lowlevel.S` in assembly, before
U-Boot has a stack, MMU or caches; it clobbers only x9-x13 to preserve LK's
x0 (DTB) and cleans one cache line.  Later markers and console text are
appended by `crumbs.c`; the used range is cleaned from the dcache after every
marker and newline.

Expected marker order when everything runs:

```
@LIDAR SAVE_BOOT_PARAMS      LK jumped to U-Boot (assembly, earliest)
@LIDAR EARLY_INIT            board_init_f reached board_early_init_f
@LIDAR WDT_OFF | WDT_ALREADY_OFF   TOPRGU MODE read/cleared (v = old mode)
@LIDAR BOARD_INIT            after relocation
@LIDAR LATE_INIT             board_late_init
@LIDAR USB_OK | USB_FAIL     UCLASS_USB_GADGET_GENERIC probe (v = error)
@LIDAR fastboot              bootcmd hook, immediately before fastboot
```

Console and debug-UART output is interleaved: `putc()`/`puts()` call the weak
`board_console_mirror()` hook after the debug-UART early-return, and
`_printch()` in `include/debug_uart.h` calls `board_debug_uart_mirror()`, so
characters are captured once on either path.  Weak empty defaults live in
`common/console.c`, so other boards are unaffected.

Decode a fetched ramoops file:

```sh
tail -c +17 ramoops.bin | tr -d '\0' | sed 's/\r$//'
# or: dd if=ramoops.bin bs=1 skip=16 status=none | strings -n 4
```

### Early-hang findings

- The TARGET_LIDAR mem_map used `MTK_MEM_MAP_DDR_SIZE=0x40000000`, while the
  reference (`reference/lidar-mainline/lidar-uboot/configs/mt8516_amazon_lidar_defconfig:14`,
  DTS `mt8516-amazon-lidar.dts:29`) uses `0x3f9c0000`, i.e. one 1 GiB rank
  minus the top 6.25 MiB TEE carve-out.  Mapping the carve-out as normal
  memory let U-Boot read/write memory that may belong to TEE; fixed at
  `arch/arm/mach-mediatek/Kconfig:180`.  U-Boot now maps
  0x40000000..0x7f9c0000 only, so a stray access above that faults instead of
  corrupting secure memory, and relocation (`gd->ram_top`) stays below the
  carve-out.
- `0x43810000` (crumbs) and `0x43030000..0x43810000` fall inside that normal
  mapping and are inside the DTS memory node.  BL31 at
  `0x43000000..+0x30000` stays `no-map` reserved; the crumb window is added
  as `reserved-memory` so Linux/U-Boot allocation does not reuse it.  The
  existing U-Boot Image (461936 bytes decompressed, BSS end 0x40164558) and
  the relocated U-Boot near `ram_top` do not overlap it.
- `.bss` sharing the `.rela.dyn` address is intentional upstream behaviour:
  `arch/arm/cpu/armv8/u-boot.lds:157` uses
  `.bss ADDR(.rela.dyn) (OVERLAY)`.  PIE fixups consume the relocations
  before BSS is cleared, so the GCC layout (BSS 0x400e4558..0x400edf58,
  `__rel_dyn_end` 0x400eefb0) is correct, not a hang.
- The previous absence of USB is consistent with an early hang before
  `board_late_init`; the markers distinguish that from LK never entering
  U-Boot (no `SAVE_BOOT_PARAMS`).

## What was changed against upstream

`arch/arm/mach-mediatek/Kconfig`
- `TARGET_LIDAR` (selects `ARM64` and `LINUX_KERNEL_IMAGE_HEADER`).
- `SYS_VENDOR`/`SYS_BOARD`/`SYS_CONFIG_NAME` = `libreecho`/`lidar`/`lidar`.
- `MTK_MEM_MAP_DDR_SIZE` 0x40000000 for this target.
- `LNX_KRNL_IMG_TEXT_OFFSET_BASE` default 0x40000000, so the Image header's
  `text_offset` is 0x80000 relative to 0x40080000.  These two symbols have no
  prompt and are otherwise selected by SoC Kconfig, so a defconfig line for
  them is silently dropped; they must be set here.

`arch/arm/mach-mediatek/Makefile`
- build `mt8516/` for `TARGET_LIDAR` as well as `TARGET_MT8516`, giving
  `dram_init()`/`print_cpuinfo()` from the existing MT8516 init.

`arch/arm/mach-mediatek/mt8516/init.c`
- guard `reset_cpu()` with `!CONFIG_IS_ENABLED(SYSRESET)`; otherwise it
  collides with `drivers/sysreset/sysreset-uclass.c`'s strong definition.
  Our reset path is `SYSRESET_WATCHDOG` -> TOPRGU software reset.

`configs/mt8516_lidar_defconfig` (key deltas and why)
- `TEXT_BASE=0x40080000`, `POSITION_INDEPENDENT`, Image header: LK gunzips to
  that address and jumps to it; 0x40080000 passes LK's 2 MiB alignment check
  (`experiments/phase-04/lk-kernel-handover-research.md:118`).
- `BOOTCOMMAND="fastboot usb 0"`, `BOOTDELAY=0`: no autoboot, no eMMC path.
- `ENV_IS_NOWHERE`, no `CMD_SAVEENV`: environment is never persisted.
- no MMC/BLK/GPT/FS and no `FASTBOOT_FLASH`: `flash`/`erase` cannot exist, so
  nothing can write eMMC and misc/BCB is never touched.
- `FASTBOOT_BUF_ADDR=0x60100000`, `FASTBOOT_BUF_SIZE=0x10000000`: matches the
  proven stock-LK fastboot window.
- `USB_GADGET_VENDOR_NUM=0x0bb4`, `PRODUCT_NUM=0x0c01`: the IDs the owner
  expects to see.
- `USB_MUSB_GADGET`, `USB_MUSB_MT85XX`: upstream MT85xx MUSB driver, matched
  by `mediatek,mt8518-musb` in the DTS.
- `CONSOLE_RECORD` + `FASTBOOT_CMD_OEM_CONSOLE`: cheap log readback over
  `fastboot oem console`.
- `GZIP`, `SUPPORT_RAW_INITRD`, `CMD_BOOTI`, `OF_LIBFDT`: needed by
  `lidar_bootimg`.
- `WDT_MTK` + `SYSRESET_WATCHDOG` + `CMD_RESET`: `reboot` through TOPRGU.
- `TOOLS_LIBCRYPTO`/`TOOLS_KWBIMAGE` off: this host's libcrypto lacks the
  `ENGINE_*` symbols U-Boot's signing tools reference; the image is unsigned.
- `WERROR` off only because clang 23 rejects an upstream MediaTek clk
  initializer; warnings are still printed.

`arch/arm/dts/mt8516-lidar.dts`
- root compatible `amzn,lidar-pvt` (LK selects by `amzn,lidar*` prefix),
  1 GiB memory minus the 6.25 MiB LK reservation, BL31 reserved at
  0x43000000, UART0, TOPRGU watchdog, wdt-reboot sysreset, MUSB peripheral.

`include/configs/lidar.h`
- `fastboot_bootcmd=lidar_bootimg`: upstream `fastboot_boot()` runs this env
  command for `fastboot boot` instead of `bootm`, so the LK-style Android
  image is parsed by us.

`board/libreecho/lidar/lidar.c`
- `board_early_init_f` clears TOPRGU `MODE.EN` at 0x10007000 with key
  0x22000000, disarming the watchdog LK leaves running (it expires ~65 s
  after hand-off).
- `board_late_init` probes the USB gadget so fastboot is enumerated even
  though nothing autoboots.

`board/libreecho/lidar/lidar_boot.c`
- command `lidar_bootimg [addr]`: parse Android v0, skip the 512-byte MTK
  header, gunzip the arm64 Image to `kernel_addr` (bounded by RAM top,
  `ramdisk_addr`, 64 MiB), check `ARM\x64`, backwards-scan the kernel field
  for the FDT chain, prefer root compatible `amzn,lidar-pvt`, copy the DTB to
  `tags_addr`, set `bootargs` from the header cmdline, then
  `booti <kernel> <ramdisk_addr>:<size> <dtb>` (`-` when no ramdisk).

`board/libreecho/lidar/lowlevel.S`, `crumbs.c`, `crumbs.h`
- assembly `save_boot_params` writes the first `LUBT` header and
  `SAVE_BOOT_PARAMS` marker at 0x43810000 without a stack or MMU, preserving
  LK's x0 (DTB); `crumbs.c` owns the ASCII ring, later markers, dcache
  cleaning, console/debug mirrors, and the `lidar_mark` command.
- markers: `EARLY_INIT`/`WDT_OFF` in `board_early_init_f`, `BOARD_INIT`,
  `LATE_INIT`/`USB_OK`/`USB_FAIL` in `board_late_init`, and `fastboot` via
  `CONFIG_BOOTCOMMAND="lidar_mark fastboot; fastboot usb 0"`.

`common/console.c`, `include/debug_uart.h`
- weak `board_console_mirror()`/`board_debug_uart_mirror()` hooks (empty for
  other boards) tee console and debug-UART characters into the ring.

`arch/arm/dts/mt8516-lidar.dts`
- added the `crumbs@43810000` reserved-memory window so booti/Linux do not
  allocate over the log.

## Reference facts used (facts only, no code copied)

- `reference/lidar-mainline/lidar-uboot/configs/mt8516_amazon_lidar_defconfig:4`
  `CONFIG_TEXT_BASE=0x40080000`.
- same file `:65-66` fastboot buffer 0x60100000 / 0x10000000.
- same file `:94-95` USB IDs 0x0bb4:0x0c01.
- same file `:98` `CONFIG_WDT_MTK=y`, and reference tree has no
  `FASTBOOT_FLASH`/eMMC boot path.
- `experiments/phase-04/lk-kernel-handover-research.md:118` 2 MiB alignment
  of 0x40080000 (LK check).
- `experiments/phase-04/lk-kernel-handover-research.md` and
  `fastboot-boot-research.md`: LK gunzips the kernel field, backwards-scans
  it for the appended DTB, rewrites /memory, and jumps with x0 = DTB.
- The reference packs gzip(`u-boot.bin`) + appended DTB; our packer produces
  the same shape from upstream sources.

## MUSB enumeration diagnostic image

`u-boot-usbdiag.img` (sha256 `b6cb14c0...`) is packed with `pack_boot.py`
because LK enters that layout, not `pack_uboot.py`:

```sh
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel /tmp/lidar-uboot-diag-wdt/u-boot.bin \
  --dtb /tmp/lidar-arm64-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --ramdisk artifacts/phase-04/initramfs/lidar-test-initramfs.cpio.gz \
  --output artifacts/phase-04/uboot/u-boot-usbdiag.img
```

Build: the `/tmp/lidar-uboot-diag-wdt` GCC build with
`KCFLAGS="-DLIDAR_KEEP_LK_WDT=1 -DLIDAR_WDT_NEVER_STOP=1"`, which keeps the
dependency on the LK watchdog for the warm-reset crumb fetch.

Instrumentation: `cmd/fastboot.c` calls the weak
`board_fastboot_registered()` after `g_dnl_register()`; the MUSB interrupt
entry (`drivers/usb/musb-new/mt85xx.c`) calls the weak
`board_fastboot_poll()`, which `board/libreecho/lidar/lidar.c` rate-limits to
one line per second.  Each line is a crumb:

```
@LIDAR USB REG|POLL FADDR=.. POWER=.. INTRUSBE=.. DEVCTL=..
  PHY1a=.. 20=.. 21=.. 22=.. 68=.. 6a=.. 6c=.. 6d=.. 6e=..
  TOP20=........ TOP24=........ TOP3c=........
@LIDAR USB SETUP bm=.. req=.. val=.... idx=.... len=....
```

`MUSB_INTRUSB`, `MUSB_INTRTX` and `MUSB_INTRRX` are read-to-clear and are
never read by the dump.  The first diagnostic image (`u-boot-usbdiag.img`,
`b6cb14c0...`) did read `INTRUSB` at the ISR entry; that stole reset/ep0
interrupts, which matches its host log (`-71`, no SET_ADDRESS response).  It
did prove connect/HS chirp work (`POWER=0xf0`, `DEVCTL=0x98/0x99`).
`u-boot-usbdiag2.img` (`8ec68008...`) moves the poll after the real ISR,
removes all read-to-clear reads, and logs received SETUP packets (first 16).
It still got zero SETUP packets, so `u-boot-usbdiag3.img` (`df02ce75...`)
builds with `-DLIDAR_KEEP_LK_PHY=1`: all `mt_usb_phy_poweron/recover/
savecurrent/force-device` writes are skipped so LK's PHY state is preserved.
It dumps the PHY once as `PRE` before the gadget probe, adds INTRTXE/INTRRXE/
EP0 CSR0/L1INTM and cumulative ISR event counts (usb/tx/rx/L1INTS) to `POLL`,
and `lidar_crumb_printf()` now cleans only the header and the new line instead
of the whole ring, so the poll no longer stalls the ISR.
`u-boot-usbdiag4.img` (`32bbb14b...`) restores PHY power-on. L1INTS bits 8/9
are VBUSVALID/IDDIG (`mtk_musb_reg.h`); L1INTM is programmed to the core
sources TX|RX|USBCOM|DMA (0x0f) exactly as Linux `mediatek.c` and vendor
`usb20.c` do, and the handler uses `L1INTS & L1INTM`. It also forces a USB
disconnect/reconnect after registration because LK handed off already
enumerated at FADDR=0x23, so the host otherwise keeps addressing the old
device. New counters split INTRUSB reset/suspend/resume/connect/disconnect/
SOF/session/VBUS-error and log the first 32 ep0 interrupts (CSR0, LEN, state).
`u-boot-usbdiag5-lkphy.img` (`f46d46ad...`) applies Kaeru LK's analog PHY
tuning after `mt_usb_phy_recover()`: clear byte 0x00 bit 5 (`INTR_EN`) and set
HQA byte 0x18 SQTH=2, matching `dumps/20261117-lidar-kaeru-usb-regs/peek.txt`
and upstream `phy-mtk-tphy`. It dumps PHY words 0x00-0x7f at PRE, REG and
around a one-shot 20 s fallback that writes LK's golden PHY words and
reconnects; MAC words 0x60-0x7f, 0xa0-0xab, 0x600-0x6ff are dumped once at
REG. Once a SETUP is seen, every poll kicks TOPRGU `WDT_RST` with 0x1971;
before that the watchdog is left to expire so a failed run keeps the crumbs.

The hook also rewrites `MUSB_POWER.SOFTCONN` (bit 6) once after registration.
Interpretation: `POWER=0x6x` means the D+ pullup is asserted; `DEVCTL` bit 4:3
should be `0x18` (VBUS valid) and bit 7 (`BDEVICE`) set in peripheral mode.
If `POWER` is asserted but `DEVCTL` shows no VBUS, the PHY/VBUS comparator is
not seeing the host; if `TOP24` bit 13 or `TOP3c` bits 14/24/31 are clear,
the USB gate clocks are off.  `PHY 6c/6d` should carry the force-device bits
(`0x2e`/`0x3e`).

`mt85xx.c` also restores the force-device PHY bits after
`mt_usb_phy_recover()`, because `recover()` clears what `poweron()` set.

## pstore readback image

`artifacts/phase-04/uboot/u-boot-stage2-pstore.img` (16 MiB, `cf0cb0fe...`)
is the image intended for `boot_a`.  USB behaviour is usbdiag5's: LK PHY
values (`INTR_EN=0`, `SQTH=2`) after recover/force-device, WDT kick only
after the first SETUP, crumbs, and the 20 s golden-table fallback.  It adds
readback of the Linux ramoops area:

- `CONFIG_CMD_PSTORE=y` with the product layout as compile-time defaults,
  `CONFIG_FASTBOOT_OEM_RUN=y`, `CONFIG_CONSOLE_RECORD_OUT_SIZE=0x100000`.
- `lidar_pstore` in `CFG_EXTRA_ENV_SETTINGS`:
  `pstore set 0x60000000 0x100000 0x20000 0x80000 0 0x20000 0`
  (addr, len, record, console, ftrace, pmsg, ecc).  `cmd/pstore.c`
  (`pstore_set`, `pstore_display`) assumes dmesg zones first, then console,
  ftrace and pmsg, computed from the end for pmsg/ftrace/console; that is
  exactly `fs/pstore/ram.c` (`ramoops_probe`: `dump_mem_sz = size - console -
  ftrace - pmsg`, then dmesg, console, ftrace, pmsg).
- DT: `ramoops@60000000` `no-map` `reg = <0 0x60000000 0 0x100000>`.  U-Boot's
  LMB reserves it from the embedded DT (`lib/lmb.c:874` ->
  `boot_fdt_add_mem_rsv_regions`, `boot/image-fdt.c:167`).  The fastboot
  buffer starts one page later at 0x60100000 (`CONFIG_FASTBOOT_BUF_ADDR`) and
  `booti` loads only at 0x40080000/0x44000000/0x4e000000, so nothing writes
  into the ramoops window.

Host sequence: `fastboot oem run:run lidar_pstore`, then
`fastboot oem run:pstore display console`, `... pstore display pmsg`,
`... pstore display dump`, reading with `fastboot oem console`.

Limits: a fastboot INFO response is `FASTBOOT_RESPONSE_LEN = 65`
(`include/fastboot.h:31`), and `oem console` reads one line with
`sizeof(buf) - 5` = 60 bytes per call (`drivers/fastboot/fb_command.c:182`),
so `console_record_readline` returns at most 59 characters and splits longer
lines into 59-character chunks.  The host must call `oem console` until it
returns OKAY (empty buffer -> `console_record_reset()`).  If output exceeds
the 0x100000 record before being drained, `membuf_putbyte` fails and
`GD_FLG_RECORD_OVF` makes every later read fail with "Error reading console"
until reset (`common/console.c:103-123, 883-891`).  One full 0x80000 console
dump plus the command's banner therefore fits with 2x margin; draining the
record between commands is required.

## PHY bisect image (RAM boot only)

`artifacts/phase-04/uboot/u-boot-phy-bisect.img` (`3a09d383...`) is built
with the same tree plus `-DLIDAR_PHY_BISECT=1` and must only ever be started
with `fastboot boot`, never flashed.  After recover/force-device it writes
the Linux upstream values first (`INTR_EN=1`, `SQTH=2`, matching
`phy-mtk-tphy.c:475, :498`), logs `@LIDAR PHY_BISECT upstream` plus a console
line, and compiles out the golden-table fallback.  If no SETUP arrives within
20 s of gadget registration, `board_fastboot_poll()` calls
`lidar_usb_phy_lk_fallback()` once: `INTR_EN=0`, `SQTH=2`, crumbs
`PHY_BISECT lk-fallback`, console line, then the SOFTCONN drop/reconnect.
Host timing bisects the two bits: enumeration about 10 s after the jump means
the upstream values work; about 30 s means `INTR_EN=0` is required.

```sh
cd repos/u-boot
make O=/tmp/lidar-uboot-pstore ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- \
  mt8516_lidar_defconfig
PATH=/tmp/lidar-uboot-pstore/scripts/dtc:$PATH \
make O=/tmp/lidar-uboot-pstore ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- \
  KCFLAGS="-DLIDAR_KEEP_LK_WDT=1 -DLIDAR_WDT_NEVER_STOP=1" -j16
# same with O=/tmp/lidar-uboot-bisect and
# KCFLAGS="... -DLIDAR_PHY_BISECT=1"
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel /tmp/lidar-uboot-pstore/u-boot.bin \
  --dtb /tmp/lidar-arm64-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --ramdisk artifacts/phase-04/initramfs/lidar-test-initramfs.cpio.gz \
  --output artifacts/phase-04/uboot/u-boot-stage2-pstore.img
# repeat for u-boot-phy-bisect.img from /tmp/lidar-uboot-bisect
```

Both `pack_boot.py --verify` runs pass (kernel gzip round-trip, appended DTB,
ramdisk, sizes).  Disassembly: the pstore build clears bit 5 of 0x11110800 and
writes `(v & 0xf0) | 2` to 0x11110818 inside `mtk_musb_enable`; the bisect
build sets that bit instead, and `lidar_usb_phy_lk_fallback` clears it and
writes SQTH=2.  Image header: `text_offset` 0x80000, `image_size` 0xea2a8,
flags 0x0a (bit 3 set), `ARM\x64` at +0x38.

RAM-booting either image from the running U-Boot works by the same path as a
Linux image (`lidar_bootimg` -> `booti`): the Android header's kernel_addr is
0x40080000, `booti_setup()` honours flags bit 3 and computes
`ALIGN(0x40080000 - 0x80000, 2M) + 0x80000 == 0x40080000`, so nothing moves,
`images->ep` is 0x40080000, and `boot_jump_linux()` hands off with caches off
(`arch/arm/lib/image.c:62-76`, `arch/arm/lib/bootm.c:262-303`).  The earlier
U-Boot has relocated near `ram_top` (0x7f9c0000), so gunzip over 0x40080000
does not touch its live copy.  The new image uses its own embedded DTB
(`CONFIG_OF_SEPARATE`), ignoring the Linux DTB moved to 0x4e000000, and its
`board_early_init_f` does not assume LK armed the watchdog (the diagnostic
build never disables it; the LK-enable state is inherited by design).

## Unverified / risks

1. **First hardware result:** `u-boot-boot-gcc.img` (dfe755fd...) was flashed
   to boot_a: preloader at 2.2-4.9 s, no USB, warm reset with preloader again
   at 67 s.  That is consistent with either LK not jumping to U-Boot or an
   early U-Boot hang before USB init; the crumbs image (e9dfc9ed...) is built
   to distinguish those on the next run.  No agent hardware test was run.
2. **MUSB after LK.** MT8516 MUSB PHY/session state may need the same
   DEVCTL/VBUS workaround used by the phase-04 kernel; U-Boot probe is
   unverified.  If no USB device appears, this is the first suspect.
3. **Watchdog.** `board_early_init_f` clears EN, but if TOPRGU is in reset
   mode or the WDT is re-armed by LK after this point, the board resets ~65 s
   after hand-off.  U-Boot also registers wdt-mtk, whose probe stops the WDT.
4. **Image header `image_size` is negative** in this PIE build
   (`0xffffffffc0000000`, `.bss` linked at 0).  LK is not known to validate
   it; U-Boot itself only needs `text_offset`/magic here.  Documented rather
   than patched, since patching generated header bytes is riskier.
5. **DTB selection** relies on the `amzn,lidar*` first-compatible string and
   on LK's backwards scan finding our appended copy.  `fastboot boot` of a
   Linux image relies on the same parser plus `booti`.
6. **Reset** uses `sysreset_watchdog` -> TOPRGU software reset.  PSCI reset
   is deliberately disabled (no `/psci` node in this hand-off), so
   `reboot-bootloader`/`reboot` reaching Kaeru is unverified.
7. **`fastboot oem console`** requires the console-record buffer to be
   populated and the command enabled; compile-time config is present.

## Owner approval procedure for the first hardware test

No agent runs any of this.  The owner performs it after explicit approval and
with a known-good way back.

1. Record the current `boot_a` (Kaeru `fastboot getvar` / dump) and keep
   `dumps/stock/boot_a.bin` plus
   `artifacts/phase-04/boot-lidar-wdt-fetch-initcall-diag.img` available.
2. Enter Kaeru fastboot as before (hold Action during reset/power).
3. `fastboot flash boot artifacts/phase-04/uboot/u-boot-boot.img`
   (`boot_a` only; never flash anything else).
4. `fastboot reboot`.  Expected: USB device `0x0bb4:0x0c01`; then
   `fastboot getvar version` and `fastboot oem console` should answer.
5. Only then try `fastboot boot artifacts/phase-04/boot-lidar-wdt-fetch-initcall-diag.img`
   (RAM boot; no flash).  Expected: Linux boots as before.
6. Recovery if no USB appears or the board resets after ~65 s: hold Action
   during reset to re-enter Kaeru fastboot, then reflash `boot_a` with the
   previous Linux image (or `dumps/stock/boot_a.bin`).

## Not built / not changed

No eMMC, no flashing code, no environment storage, no misc/BCB access.
`experiments/phase-04/pack_boot.py` is untouched.  Work is on branch
`lidar-fastboot-stage2`, committed as `dffcf3d8` on 2026-11-17 (Phase 4
cleanup, before any hardware test).
