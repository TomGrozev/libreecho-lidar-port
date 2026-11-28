# Lidar boot image packager

Host-side tool and hardware bring-up record for Phase 4. The packager reads the stock boot
image read-only and writes a development image with a new ARM64 `Image`, a new Lidar DTB and
the stock ARM32 ramdisk. It does not boot, flash, reboot or push a device, makes no
bootability or hardware-support claim, and produces no signature.

This is the condensed record: it keeps the findings, the evidence that established them and
the working commands, and drops the superseded probe-by-probe runs. The raw captures stay in
the `hw-*/` run directories and `artifacts/phase-04/` in the private workspace.

## Build target and inputs

The `lidar` target builds `arch/arm64/boot/Image` and
`arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb`. The packager takes those two files and
the stock image.

| Input | Size | SHA-256 |
| --- | --- | --- |
| `dumps/20261110-lidar-readback/boot_a.bin` | 16 777 216 | `eec8da659fd81352c62e22eb9e2fac174efd180ab03e5ab6c88e1f0135df090c` |
| Stock appended DTB index 4, PVT | 54 016 | `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f` |
| Stock ramdisk gzip | 4 117 193 | `ab2e6a4a4c9174eef2acfdf4e34914a5c71694aa0f1d26a04c7140febe44c2c1` |
| Stock kernel section | 6 227 381 | `e02a41c9817afe97b8116babbed09dc0b6b1de23c5413ee564798c199434389e` |
| Stock trailer certificate | 1 077 | `2f4dbaed1afb3ae78d8362a0f5ef411ab52f5568f4b4fbc2e203fddbf0541ce6` |

Key development images, in chronological order. The first build's DTB is unchanged later;
the first `boot_a` flash used `3d2997`.

| Image | SHA-256 | Use |
| --- | --- | --- |
| `boot-lidar-development.img` (first) | `3d2997e6fe33c00e76632d1a2c59ed675c0e77d469a9de5e5d5440d0f5975c16` | first slot write |
| `boot-lidar-development.img` (revised) | `b2e01eb5bc7db3f783760a97c90a40840852751e03ea0f7c020e640da9b2e2a9` | USB config fix |
| `boot-lidar-lk-slot-source.img` | `7284abc588ac5ab0b1bb8928b5aba105c7854f609c285bfb1bf4adb659a03fce` | Phase 4 gate |
| `boot-lidar-peripherals-3.img` | `2e387bbe` | last Phase 4 image, all peripherals probe |

The packager prints input and image SHA-256 values on every pack and verify run.

## Stock layout

The tool checks these values before it writes anything.

| Item | Value |
| --- | --- |
| Page size | 2 048 |
| `kernel_addr` | `0x40080000` |
| `ramdisk_addr` | `0x44000000` |
| `second_addr` | `0x40f00000` |
| `tags_addr` | `0x4e000000` |
| `header_version` | 0 |
| `second_size` | 0 |
| MTK header | 512 bytes, magic `0x58881688`, name `KERNEL` |
| Stock kernel section | `0x800` to `0x5f0db5` |
| Stock gzip kernel | starts `0xa00`, 5 167 882 bytes |
| Stock appended DTBs | 19 blobs, `0x4ee50a` to `0x5f0db5`, no gaps |
| PVT blob | index 4, `0x523472`, 54 016 bytes |
| Stock ramdisk | starts `0x5f1000`, gzip, 4 117 193 bytes |
| Stock trailer | DER blob at `0x9de800`, zeros to the 16 MiB end |

The Android v0 id field holds a 20 byte SHA-1 over the kernel section, kernel size,
ramdisk, ramdisk size and a zero second size. The tool recomputes it.

## Host build

The verified run used local Clang 23.1.5, LLD and DTC 1.8.1 under
`/tmp/lidar-arm64-tools/root`; it installed no system packages. Run from the project root;
the kernel output directory is separate from the source tree.

```sh
cd repos/LibreEcho-Linux
export PATH=/tmp/lidar-arm64-tools/root/usr/bin:$PATH
export LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 olddefconfig
make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 Image dtbs -j8
cd ../..
mkdir -p artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek
cp /tmp/lidar-arm64-build/arch/arm64/boot/Image \
  artifacts/phase-04/kernel-build/arch/arm64/boot/Image
cp /tmp/lidar-arm64-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb
cp /tmp/lidar-arm64-build/System.map artifacts/phase-04/kernel-build/System.map
cp /tmp/lidar-arm64-build/.config artifacts/phase-04/kernel-build/.config
```

## Package and verify

```sh
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel artifacts/phase-04/kernel-build/arch/arm64/boot/Image \
  --dtb artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --output artifacts/phase-04/boot-lidar-development.img
# the same arguments with --verify <image> instead of --output: verify: OK
```

Verify parses the image again: header, MTK header, decompressed kernel, DTB collection,
ramdisk, Android id and the zeroed trailer against the supplied inputs.

`python3 -B experiments/phase-04/test_pack_boot.py -v` (later
`python3 -m unittest experiments/phase-04/test_pack_boot.py`) builds a synthetic 16 MiB
stock image and covers the round trip, determinism, the retained stock DTBs, a changed DTB,
tampered ramdisk and trailer, malformed headers, truncation, the `bootopt` prefix, the DTB
size cap, the root-compatible check and the generated `/chosen` initrd properties. The suite
finished at 43 tests, all passing.

## Behaviour, failure and limits

The tool mirrors the stock wrapper: 2 048 byte pages, the load addresses, the MTK header,
the appended DTB collection and the 16 MiB envelope. It replaces only appended FDT index 4,
so the other 18 stock blobs stay byte-identical and the LK board-id table keeps every entry.
The new Image must carry `ARMd` at offset `0x38`; the DTB must parse as an FDT and contain
`amzn,lidar-pvt` in its root compatible list. The kernel is gzipped with a fixed header, the
trailer is written as zeros, and no stock or new signature is made.

The tool exits 2 on any unexpected layout: not exactly 16 MiB, different addresses or page
size, different MTK header, DTB count or PVT hash, unexplained trailer bytes, a kernel that
is not an ARM64 Image, a DTB without the PVT compatible, an overflow of the envelope, or an
output that fails verify. It refuses to write over the stock image or either input file.

Host-side construction cannot show that the image boots. The LK maximum DTB size check is
not modelled; the tool enforces the 16 MiB envelope only.

## Hardware bring-up, 2026-11-15 to 2026-11-17

Every write and reboot below ran under separate approval, with the stock backup intact and
`boot_b` untouched. `boot_a` was the only slot written.

### Fastboot limitations and slot control

Kaeru rejects `fastboot boot` as an unknown command, so every test wrote `boot_a` and cold
booted. A first failed A boot let the BCB fall back to B; later A flashes then did not run
until the BCB was repaired. The repair changed only two bytes in `misc` (priority above
tries for slot `a`), and the readback matched. Rule for every A test: confirm A is selected
before the flash; after a B fallback, repeat the verified BCB repair first. Fastboot also
warned that the reported `boot_a` size was zero and skipped the AVB footer copy; partition
readback through `fastboot fetch boot_a` was used instead.

### ARM64 entry and persistent console

`experiments/phase-04/early_entry.S` masks DAIF, disables the MT8167 watchdog at
`0x10007000` and loops. With A selected, a cold boot showed a persistent blue light instead
of the stock animation. Image `b5724301…`: LK decompressed the probe and ATF entered it, so
the image format, load address and ARM64 architecture are proven through the stock chain.
This is execution proof for the probe, not for a full kernel.

Warm-RAM reads were unreliable: the BROM/DA path overwrote RAM on cold entry, and a known
`LIBREECHORAMMRK!` marker did not survive a warm reset. Conclusion: RAM marker absence is
not proof that code did not run. The dependable reachability signal became a 5-second
busy-wait plus TOPRGU reset to Kaeru fastboot, because only the diagnostic driver sets it.

Persistent console capture worked after a Kaeru `fetch ramoops` handler was added. The final
bootimg-window layout put the marker at `0x43800000` and ramoops at `0x43810000`
(size `0x60000`), inside LK's mapped bootimg window. Image
`boot-lidar-lateinit-fastboot-return-mapped-pstore-bootimg.img` (`9c837a8d…`) produced
`ramoops-438.bin` and a 116-line kernel console (`kernel-console-438.log`, `2d7396a9…`):
`ramoops: using 0x60000@0x43810000`, `pstore: Registered ramoops as persistent store
backend`, and `[LIBREECHO-LATEINIT-FASTBOOT] late_initcall_sync reached`.

The same log showed the failure set: regmap lookups returned `-ENOTSUPP` for
`/soc/topckgen@10000000`, `/soc/syscon@15000000`, `/soc/syscon@16000000` and
`/soc/mmsys@14000000`; pinctrl and `clk-mt8167-mm` deferred; `mt6577-uart`, `mtk_rng` and
`musb-mtk` failed with `-ENOENT` for missing clocks. All pointed at one clock/regmap thread.

### Syscon and initcall bisect

The `-ENOTSUPP` set had a concrete cause: the ARM64 defconfig omitted `CONFIG_MFD_SYSCON`,
so `syscon_regmap_lookup_by_phandle` compiled to stubs. The defconfig now sets
`CONFIG_MFD_SYSCON=y`, selecting `CONFIG_REGMAP_MMIO`.

The first syscon images did not return to fastboot, but that was not proof of an early
stall: the RAM markers were cleared along the BROM/DA recovery path. A matched entry-WDT
probe (same marker store and 5-second reset at `primary_entry`) returned in both builds, so
`primary_entry` executes in the syscon build. Delayed-reset probes then bounded the
ordinary init path (table: time from reboot to a fastboot device):

| Probe | No syscon | Syscon |
| --- | --- | --- |
| top of `rest_init` | 22 s | 27 s |
| before level 0 | 9 s | 8 s |
| after arch (level 3) | 27 s | 9 s |
| after fs (level 5) | not run | 9 s |
| after device (level 6) | not run | 9 s |
| after late (level 7) | not run | 9 s |

Late-item probes before items 21, 25, 27 and 28 also returned in 9 s (item 28 proves late
items 0–27 ran). The after-late return proves every ordinary initcall level completes when
the final `libreecho_lateinit_fastboot` diagnostic registration is suppressed. The original
no-return behaviour is therefore confined to the diagnostic itself or to work after the
ordinary initcalls; no claim follows that the product syscon change is at fault.

A clean syscon build (`3da28ee2…`) still showed no USB interface. A pre-userspace
delayed-reset probe (`e490d27b…`) reached the exec boundary after `do_sysctl_args()`, and an
exec-success probe (`cf22ae65…`) proved `run_init_process('/init')` returns 0. The remaining
failure is in Android init or ADB after the exec.

### Watchdog and fetchable-pstore diagnostic

A kernel with the MediaTek watchdog and ramoops at `0x43810000` produced a readable console
after the ~65 s boot-chain watchdog reset (`ramoops-after-diag.bin`, console 244 lines):

- the kernel boots, all four CPUs come up, and ramoops registers at `0x43810000`;
- `mtk-power-controller … power-domain@4: failed to power on domain: -110`; domain 4 is
  `MT8167_POWER_DOMAIN_MFG_ASYNC`, and the whole power-controller probe then fails;
- the last line is `11005000.serial: ttyS0 … ST16650V2`; `mtk_wdt`, `mtk_rng` and MUSB come
  later in `System.map`, so the watchdog driver never runs and init never starts.

An `initcall_debug` run added no `calling`/`initcall` lines: they print at `KERN_DEBUG`,
below the pstore console level. The next such run needs `ignore_loglevel` or `loglevel=8`.
The pstore placement in the product DTB stays `0x60000000`.

### USB: from MUSB probes to the ACM route

Kernel probes and a stock-layout MUSB experiment established the chain: glue probe
succeeded, `musb_init_controller()` returned 0, the gadget requested pullup, and
`MUSB_POWER_SOFTCONN` was set with DEVCTL VBUS full. The host still never enumerated the
gadget; the `0525:a4a7` observations in early runs are invalid because the g_serial product
ID is `0525:a4a6`, but the later correct-ID runs were also negative. The reference project
and LK both enumerate on the same port, so the comparison moved to LK's PHY setup.

That comparison later paid off in U-Boot: U-Boot's `mt_usb_phy_recover()` set byte `0x00`
bit 5 (`RG_USB20_INTR_EN`) and squelch `SQTH=6`, while LK runs with `INTR_EN=0` and
`SQTH=2`. Applying LK's tuning made U-Boot enumerate at high speed and serve fastboot.

The course change on 2026-11-17 dropped ADB: the failure is below ADB, and the debug channel
became a USB CDC ACM root shell (getty on `ttyGS0`), an optional NCM network link, and
pstore/ramoops readback after a warm reboot. The kernel stays on Linux 6.1.178 on
`feature/lidar-support`; upstream 6.1 USB code was restored and the probe/PHY patches saved
under `experiments/phase-04/pre-clean-control/`.

### Second-stage U-Boot

Upstream U-Boot v2026.10 was built as a second-stage image that never writes storage. The
first clang/ld.lld build placed `.bss` at address 0 (`__bss_start` = 0), so U-Boot cleared
non-DRAM and stopped before console or USB. An aarch64 GCC 16.2.0 build put `.bss` after
`.rela.dyn` and made a positive `image_size`.

Breadcrumb runs showed LK entering U-Boot and U-Boot reaching USB, but with `-71` control
transfer failures on the host: SOF tokens arrived, SETUP packets never did. Register
comparison against live Kaeru fastboot identified the PHY difference above. The fifth
diagnostic (`u-boot-usbdiag5-lkphy.img`, `f46d46ad…`) applied LK's `INTR_EN=0` and `SQTH=2`;
the host enumerated `0bb4:0c01` (`Manufacturer: LibreEcho`, `Product: USB download gadget`)
about 10 s after reboot, `fastboot getvar version` returned `0.4`, and a watchdog kick in the
fastboot poll loop kept the session alive. U-Boot USB fastboot works on this unit.

`lidar_bootimg` rejected the unaligned appended DTBs (`FDT_ERR_ALIGNMENT`) and did not copy
the ramdisk; `uboot_manual_boot.sh` instead staged an image and used `oem run` with `booti`.
K1 (`boot-lidar-console-wdt-k1.img`, `5e090868…`) RAM-booted: the gadget enumerated 5 s
after `booti`, `mtk-wdt` probed, the 240 s autoreboot fired, and pstore kept console and
pmsg. The ACM shell initially only echoed because busybox `cttyhack` reopened the console
tty; starting the ttyGS0 shell with `setsid -c` fixed it. The repacked image
`boot-lidar-console-wdt-k1-acm.img` (`77bcf0f3…`) gave `uname -a`
(`Linux (none) 6.1.178+ … aarch64`), `/proc/cmdline`, four Cortex-A35 cores (`0xd04`) in
`/proc/cpuinfo`, full `dmesg` (`Machine model: LibreEcho Lidar`), the marker
`LIDAR_PSTORE_MARK_1432` written to `/dev/kmsg`, and that marker in the pstore readback
after `reboot -f`.

### LK slot boot: initrd and uart0

The same `77bcf0f3` image booted from `boot_a` through LK showed no USB interface and no
reset. Two faults explained it:

1. LK passes no initrd. In `lk_a.bin` it writes `linux,initrd-start`/`linux,initrd-end` only
   for IDME bootmode 2 or `0x61`, while it copies the ramdisk to `ramdisk_addr` on every
   boot and contains no `fdt_delprop`. The kernel therefore waits forever for
   `root=/dev/dm-0` after `populate_rootfs` returns without unpacking.
2. The uart0 probe stalls when uart0 is not a console: `mtk8250_runtime_suspend` polls
   `MTK_UART_DEBUG0` without a bound (`8250_mtk.c:426`), and after LK the register never
   reads zero. With `mtk-wdt` running, the board never resets and the RAM log is lost.

The working image `3b5d3d93` keeps uart0 disabled and adds the `/chosen` initrd properties
(`0x44000000`, end = start + ramdisk length). It booted from `boot_a` through LK: the gadget
enumerated, `acm-diagnostics.log` held `uname -a`, the LK `/proc/cmdline`, `/proc/cpuinfo`
and `dmesg` with `Unpacking initramfs...` and `Run /init as init process`, and a warm-reboot
pstore fetch contained the marker `LIDAR_LK_SLOT_PSTORE_MARK_1757` and
`reboot: Restarting system`. An in-Linux readback also showed `console-ramoops-0` and
`pmsg-ramoops-0` with a fresh marker.

### LK slot initrd fix in source

`pack_boot.py` now parses and rewrites the FDT itself (`parse_fdt`, `serialize_fdt`,
`FdtNode`, `FlatFdt`) and adds the initrd properties from the stock `ramdisk_addr` plus
ramdisk length; stock appended DTBs stay byte-identical and `--verify` recomputes them.
Kernel `feature/lidar-support` carries:

| Commit | Change |
| --- | --- |
| `b96322d5faf0` | uart0 disabled; ramoops at `0x43810000` size `0x60000` |
| `22e6c3324ab8` | `CONFIG_DEBUG_FS=y` |
| `6276a30b0db9` | no-PMIC layout, `core_power` 1.15 V, `sdio_fixed_3v3` on GPIO24 |

The CPU rail is a Richtek RT5738 buck on i2c1 at `0x57`, always on, vsel GPIO9; Linux 6.1
has no driver or binding, so the node stays out. Build branch `experiment/lidar-lk-slot-source`
starts at `24a9de47`, tip `79d8d10e`; image `7284abc5…`, DTB `0ed145b0…`, kernel
`91b4209f…`. `dt-validate` gives the same five warnings before and after the rails change.

### Gate run with the source-built image

`boot-lidar-lk-slot-source.img` (`7284abc5`) was flashed to `boot_a` and read back, then
cold-booted through the stock LK. The ACM captures in `hw-20261117-lk-slot-source/` hold:

- `uname -a` `6.1.178+ #2 SMP Tue Nov 17 18:20:01 AEDT 2026 aarch64`, the LK
  `/proc/cmdline`, four Cortex-A35 cores (`CPU part 0xd04`), `/proc/partitions` (p1–p16,
  boot0, boot1), the regulator and clock summaries, and `dmesg` with `Unpacking initramfs...`;
- the marker `LIDAR_SOURCE_PSTORE_MARK_1827` written to `/dev/kmsg`, then after a warm reboot
  `console-ramoops-0` holding that marker.

The gate passed with this image. `feature/lidar-support` was then aligned with it:
`a47db1334a3c` restored upstream v6.1.178 MUSB/gadget code, and `d4e78e5f1bc3` enabled the
MediaTek TOPRGU watchdog; `git diff` against the experiment branch is empty. The rebuilt
Image (`4d1cae76…`) differs from the archived gate image `91b4209f…` because of
`KBUILD_BUILD_VERSION` shifting the UTS banner and `.rodata`; an exact byte reproduction was
not completed, and the booted image reports `#2`, so the explanation remains unverified.

### Peripherals

Kernel `feature/lidar-support`, base `d4e78e5f1bc3`:

| Commit | Change |
| --- | --- |
| `0c21b83d7854` | gpio-keys on GPIO7/12/42/108 and the GPIO18 `EV_SW` privacy switch |
| `306226d8fbb3` | i2c0 IS31FL3236 at `0x3f` (36 channels, GPIO4 SDB) |
| `5dc5c43a8c55` | mmc2/mmc1 SDIO for the MT7668 combo, `reg_sdio_3v3`, msdc2 clock fix |
| `feb02cdf4e12` | TLV320AIC32x4 DAC on i2c2, four TLV320ADC3101 on i2c0, optional shared reset |
| `fcb422ec7924` | DTS scope comment; missing `NEW_LEDS` and `SOUND` parent symbols |

`make savedefconfig` keeps every requested symbol. Host build only: kernel `277e852d…`,
DTB `866ae7a5…`, image `8333baa4…`; the DTC step for the Lidar DTB produced no warnings.

### Hardware runs, 2026-11-17

Each image was flashed to `boot_a` from Kaeru, read back, and cold-booted. Logs are in
`hw-20261117-peripherals/`.

| Image | SHA-256 | Result |
| --- | --- | --- |
| `boot-lidar-peripherals.img` | `8333baa4` | gpio-keys bound; `is31fl32xx` failed `-22` (ADC nodes nested in the LED node); `11170000.mmc` failed `-19` (missing `uhs` pinctrl); eMMC came up as `mmc2` |
| `boot-lidar-peripherals-2.img` | `09285ac9` | fixed LED nesting, added `state_uhs` and aliases; 36 LEDs, four ADCs, eMMC on `mmc0`, MT7668 enumerated; DAC `2-0018` returned `-ENXIO` |
| `boot-lidar-peripherals-3.img` | `2e387bbe` | restored the 1 ms wait after DAC reset release; every peripheral probes |

Evidence from image 3 (kernel `6.1.178+ #2 SMP Tue Nov 17 20:27:41 AEDT 2026`):

- I2C: `is31fl32xx` at `0-003f`, `tlv320adc3xxx-codec` at `0-0018` through `0-001b`,
  `tlv320aic32x4` at `2-0018`, every probe returning 0.
- LEDs: 36 entries in `/sys/class/leds`; the ring glowed dim red at brightness 16 and
  changed to full brightness. A full-brightness run dropped the USB link with `EPROTO`
  (cause unknown); no flicker was seen.
- SDIO: `mmc1: new ultra high speed SDR104 SDIO card`, with `mmc1:0001:1` (`037a:7608`,
  WLAN, no driver) and `mmc1:0001:2` (`037a:7668`, bound to `btmtksdio`). Bluetooth fails
  as expected: `Direct firmware load for mediatek/mt7668pr2h.bin failed with error -2`.
- Sound: `/proc/asound/cards` reports no soundcards, as expected for 6.1.
- Buttons: 16-byte compat `input_event` records in order `KEY_VOLUMEDOWN` (114),
  `KEY_HELP` (138), `KEY_VOLUMEUP` (115), `KEY_MICMUTE` (248), then `SW_MUTE_DEVICE` = 1,
  each with a release. The unit has no separate privacy switch: the mic-mute button sets
  the hardware latch GPIO18 reports.

Hardware disputes: the action key is `KEY_HELP` (138 = stock `0x8a`), not the reference's
`KEY_PROPS` (whose comment calls 130 `0x8a`); stock puts action on GPIO3 and mute on GPIO18,
while the DTS follows the hardware-verified GPIO42/GPIO108 mapping. The four ADC3101 share
one reset line on GPIO2, so only the `0x18` node owns `reset-gpios` and the driver treats it
as optional. `mmc2` has no infracfg reset bank in this tree.

Fix commits on `feature/lidar-support`: `2066d8c0` (DTS: LED node closed, `state_uhs`,
i2c and `mmc0` aliases) and `7594c578` (TLV320AIC32x4: 1 ms after reset release; `abd2f555`
had moved the upstream delay).

## Session end state

`boot_a` holds the last Phase 4 image `boot-lidar-peripherals-3.img` (`2e387bbe`), with
`lidar.autoreboot=240` on the command line; `boot_b` was never written by these runs and
stays stock. The Phase 4 hardware gate passed on 2026-11-17 with the source-built
`7284abc5` image (see "Gate run with the source-built image"). The open items at the end
were the unbounded 8250 runtime-suspend wait before uart0 can come back under LK, the
`MFG_ASYNC` power-domain `-110` on both boot paths, and the open explanation for the
rebuilt Image hash difference. `PLAN.md` records the handoff to Phase 5.
