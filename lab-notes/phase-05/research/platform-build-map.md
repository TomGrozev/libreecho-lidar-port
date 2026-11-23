# Platform build map: Phase 5 reconnaissance

Scope: `repos/LibreEcho-Platform` (branch `feature/lidar-support`, a Linux 3.18.19
kernel tree with product tooling under `tools/mt8163-arm32/`), how
`repos/LibreEcho` (Product) drives it, and the kernel tree `repos/LibreEcho-Linux`
(6.1) that actually supplies the kernel. This is a read-only investigation; no
builds were run.

Headline: Platform has no build orchestrator and no Makefile for images. Every
image is produced by two Python CLIs (`generate_boot_envelope.py`,
`build_recovery_image.py`) and checked by a third (`verify_recovery_image.py`).
Product's `build/build.sh` is the only end-to-end driver. The only profile seam is
a string, `platform.tools_profile`, read at `LibreEcho/build/build.sh:404`. Product's
JSON schema pins that string to the constant `"mt8163-arm32"`
(`LibreEcho/release/target.schema.json:101`), so adding an ARM64 profile needs a
schema change, a descriptor change and a `build.sh` change, not just a new
directory.

---

## 1. End-to-end: how a product boot image is built today

Entry points in order. Paths are relative to `repos/LibreEcho/` unless noted.

| # | Entry point | Command / role | Inputs → outputs |
|---|---|---|---|
| 1 | `.github/workflows/build-release.yml` | `workflow_dispatch`/PR/`workflow_run`. Resolves `product_sha`/`platform_sha`/`linux_sha`/`ui_sha`; checks out Platform to `sources/platform`, Linux to `sources/linux`, UI to `sources/ui` (`:632-661`) | refs → source trees |
| 2 | `build/ci/build-public-toolchain.sh` | `build-public-toolchain.sh <out>`; builds musl-cross-make at commit `227df8b99103f9c59f6570babf892978e293082f`; emits `armv7-alpine-linux-musleabihf-*` plus `usr/lib/ld-musl-armhf.so.1` | musl-cross-make + musl 1.2.x + GNU binutils/gcc → job-local toolchain root |
| 3 | `build/ci/build-public-neural-deps.sh` | `build-public-neural-deps.sh <public-deps> <armhf-root>`; ONNX Runtime, Sherpa, RE2 and SpeexDSP go to `public-deps/neural/` | pinned sources → static ARM32 libs |
| 4 | `.github/workflows/build-release.yml:963-1020` | shared mDNS runtime: Platform `tools/mt8163-arm32/mdns/build_runtime.py`, verified by `mdns/verify_runtime.py`, smoke-tested by `mdns/test_packaged_runtime.py --init-wrapper .../initramfs/libreecho-mdnsd` | packages lock → verified runtime root + manifest sha |
| 5 | `build/ci/build-public-release.sh` | validates env, sets `LIBREECHO_PUBLIC_RELEASE=1`, then runs `exec build/build.sh --targets ... --profile ota --service-profile production --feature-policy community-noncommercial --no-publish` (`:44`) | env roots → build.sh |
| 6 | `build/build.sh` | the orchestrator (about 2856 lines). Resolves the target registry, then: toolchain/login checks → `musl/build_musl.sh` (`:759`) → `busybox/build_busybox.sh` (`:773`) → `wpa-supplicant/build_wpa_supplicant.sh` (`:790`) → connectivity staging (`:822`) → `audio-tools/build_audio_tools.sh` (`:841`) → libsodium → bootctl/update-verifier (`:1190-1200`) → adbd → UI bundle → AirPlay payloads → neural/TTS/STT → kernel → image → OTA → provenance | component archives + sources → components |
| 7 | kernel build (`build.sh:1050-1060`) | `make -C $KERNEL_SRC O=$KERNEL_OUT ARCH=arm CROSS_COMPILE=$CROSS LD=${CROSS}ld.bfd -j$JOBS zImage "$KERNEL_DTB_NAME"` with pinned `KBUILD_BUILD_USER/HOST/VERSION/TIMESTAMP` | Linux 6.1 source + `mt8163_arm32_defconfig` → `arch/arm/boot/zImage`, `System.map`, `arch/arm/boot/dts/<dtb>` |
| 8 | DTB gate (`build.sh:1067-1072`) | `python3 -B tools/mt8163-arm32/verify_${DTB_VERIFIER_ID}_dtb.py --dtb $KERNEL_DTB` | DTB → PASS/fail |
| 9 | `tools/mt8163-arm32/generate_boot_envelope.py` (`build.sh:2317-2320`) | `python3 -B $TOOLS_DIR/generate_boot_envelope.py "${TARGET_TOOL_ARGS[@]}" --output $RUN/boot-envelope.bin` | `--target`, optional `--target-descriptor-sha256` → deterministic 16 MiB envelope |
| 10 | `tools/mt8163-arm32/build_recovery_image.py` (`build.sh:2321-2354`) | about 40 flags: `--boot-envelope --zimage --expected-zimage-sha256 --system-map --expected-system-map-sha256 --dtb --expected-dtb-sha256 --busybox --musl-loader --adbd --bootctl --update-verifier --ota-public-key --audio-probe --tinyplay/--tinycap/--tinymix --iwconfig --ui-bundle --mdns-runtime --wmt-* --wpa-supplicant --wifi-config [--dropbear/--dropbearkey/--scp] --image-profile --service-profile --feature-policy --update-channel --output --ramdisk-output --manifest --target` | envelope + zImage + DTB + all component binaries → `$RUN/boot.img`, `$RUN/boot.ramdisk.cpio.xz`, `$RUN/manifest.json` |
| 11 | `tools/mt8163-arm32/verify_recovery_image.py` (`build.sh:2356-2390`) | independent re-derivation of the header, MKIMG wrapper, zImage/DTB, padding, Android ID, physical-memory ordering and the whole initramfs (manifest-driven) | the three outputs + all component hashes → `verify.log`, one `...=PASS` line |
| 12 | `tools/mt8163-arm32/ota/make_ota_bundle.py` (`build.sh:2550-2559`) | signs the boot image and feature manifests into `$RUN/libreecho-<run_id>.ota.tar` | boot.img + manifests + signing key → OTA bundle |
| 13 | `tools/mt8163-arm32/recovery-install/build_install_bundle.py` | not called by build.sh. The Product workflow ships the builder with the artifact (`.github/workflows/build-release.yml:1381-1396`) and the publisher runs it after `prepare-dev-release` | release assets → TWRP install zip |
| 14 | publish (`build.sh:2704-2856`) | writes `$RUN/provenance.txt` and `$RUN/CURRENT.candidate`, then `out/CURRENT` and the `out/current` symlink unless `--no-publish` | run dir → CURRENT pointer, `status=PREPARED_NOT_FLASHED` |

Output layout under `$LIBREECHO_BUILD_ROOT/out/runs/<run_id>/`: `boot.img`,
`boot.ramdisk.cpio.xz`, `manifest.json`, `zImage`, `System.map`,
`<dtb>`, `kernel.config`, `boot-envelope.bin`, `components/`, component
`*-source.json`, build/verify/ota logs, `provenance.txt`, `CURRENT.candidate`
(`build.sh:1130-1200` materializes components; `:2560-2856` writes provenance).

Notes for Phase 5:

- `ARCH=arm`, `zImage` and `CROSS_COMPILE=arm-linux-gnueabihf-` are hardcoded in
  build.sh (`:859`, `:879`, `:1050-1059`). `KERNEL_DEFCONFIG`, `KERNEL_DTB_NAME`,
  `DTB_VERIFIER_ID` and `TOOLS_PROFILE` come from the target descriptor via
  `build/ci/validate-targets.py`.
- `build.sh:413-416` pre-flights each tool through
  `build/ci/platform-target-args.py`, which runs the tool's `--help` and requires
  `--target` (and `--target-descriptor-sha256`) support. Any new SoC tool must
  advertise both or the multi-target build refuses.
- The kernel source is a separate tree. The LibreEcho-Linux README warns that the
  Platform tree is Linux 3.18 and "will produce incompatible DTC/build results
  when used as a 6.1 source" (`repos/LibreEcho-Linux/README.md:124-128`).
- Product's installer path today is fastboot-first (amonet/brick) per
  `repos/LibreEcho/tools/README.md:33-60`. Platform's `recovery-install/` is the
  TWRP half (`tools/mt8163-arm32/recovery-install/README.md:1-40`). There is no
  TWRP on the Lidar unit (`experiments/phase-05/boot-shape-decision.md`).

---

## 2. MT8163/ARM32 constants and rules in the builders and verifiers

### `tools/mt8163-arm32/generate_boot_envelope.py`

| Item | Line | Value |
|---|---|---|
| `ANDROID_MAGIC` | 17 | `b"ANDROID!"` |
| `IMAGE_SIZE` | 18 | `0x1000000` (16 MiB) |
| `PAGE_SIZE` | 19 | `0x800` (2048) |
| `KERNEL_ADDR` | 20 | `0x40008000` |
| `RAMDISK_ADDR` | 21 | `0x43478000` |
| `SECOND_ADDR` | 22 | `0x40F00000` |
| `TAGS_ADDR` | 23 | `0x48000000` |
| `BOOTOPT` | 24 | `b"bootopt=64S3,32N2,32N2"` (written at offset 64) |
| header pack | 29-35 | `<10I` with kernel_size=0, kernel_addr, ramdisk_size=0, ramdisk_addr, second_size=0, second_addr, tags_addr, page_size, dt_size=0, unused=0 |
| zero payload | 44-49 | refuses overwrite; prints `target=`, sha256, size |

The bytes are target-independent on purpose (`:47-50`). Both registered targets
share the envelope, and the builder plus verifier compare it byte-for-byte.

### `tools/mt8163-arm32/build_recovery_image.py` (the ARM32 image builder)

| Item | Line | Value / rule |
|---|---|---|
| `ANDROID_MAGIC` | 44 | `b"ANDROID!"` |
| `MKIMG_MAGIC` | 45 | `88 16 88 58` (0x58881688) |
| `FDT_MAGIC` | 46 | `d0 0d fe ed` |
| `PAGE_SIZE` | 47 | `0x800` |
| `MKIMG_SIZE` | 48 | `0x200` (512) |
| `RAMDISK_COMPRESSION` | 49 | `"xz-crc32-lzma2-8m"` |
| `RAMDISK_XZ_DICT_SIZE` | 50 | `8 << 20` |
| `IMAGE_SIZE` | 51 | `0x1000000` |
| `KERNEL_ADDR` | 52 | `0x40008000` |
| `RAMDISK_ADDR` | 53 | `0x43478000` |
| `RAMDISK_END_LIMIT` | 54 | `0x44400000` (ram_console start) |
| `TAGS_ADDR` | 55 | `0x48000000` |
| `ATF_START` / `ATF_END` | 56-57 | `0x43000000` / `0x43030000` |
| `EVT_SOURCE_OFFSET`/`EVT_RAW_SIZE`/`EVT_PADDED_SIZE` | 58-60 | `0x585185`, `0xC875`, `0x10000` |
| `ZIMAGE_MAGIC` | 61 | `0x016F2818` |
| pinned `STOCK_EVT_SHA256`, `RECOVERY_INIT_SHA256`, `BOOT_ENVELOPE_SHA256`, `PROVEN_ZIMAGE_SHA256`, `PROVEN_SYSTEM_MAP_SHA256` | 63-68 | default expected hashes (`--expected-zimage-sha256` defaults to `PROVEN_ZIMAGE_SHA256`, `:2877`) |
| `android_id()` | 469-477 | SHA-1 over kernel/ramdisk/second (+dt) with little-endian lengths, zero-padded to 32 |
| `elf_identity()` | 480-488 | `(EI_CLASS, e_machine)`; non-ELF → `None` |
| `readelf_contract()` | 490-513 | requires `Class: ELF32`, little-endian, `Machine: ARM`; returns `(ABI flags, interpreter, NEEDED, DYNAMIC)` |
| `require_elf_contract()` | 515-532 | identity must be `(1, 40)` = ELF32/EM_ARM; ARM flags compared exactly |
| overlay staging | 737-889 | fixed dirs `bin dev etc lib proc sbin sys system tmp`, overlay file table (mode per file), `/init` must equal audited `libreecho-init` |
| BusyBox applets | 858-880 | `qemu-arm-static -L <stage> bin/busybox --list`, at least 250 applets, symlink each into `/bin`; fixed links `lib/libc.musl-armv7.so.1 -> ld-musl-armhf.so.1`, `sbin/sh`, `sbin/ueventd`, `sbin/watchdogd`, `system/bin/sh` |
| target identity | 890-914 | `/etc/libreecho/target` from `identity_bytes()`, `/etc/libreecho/audio-profile` from the target table; rewrite `default.prop` board |
| ARM32 ELF flag values used | 413, 699, 940, 1025, 1056, 1118, 1463-1469, 1731, 2283, 2348 | `0x05000400` = EABI5 + hard-float. Static userspace: `(flags, None, (), False)`. musl-linked stt/ttsd and UI: interpreter `/lib/ld-musl-armhf.so.1`, NEEDED `libc.musl-armv7.so.1`, dynamic. AirPlay daemons are checked separately as ARMHF glibc: interpreter `/lib/ld-linux-armhf.so.3` (`:1735-1745`) |
| `validate_stage()` | 2378-2517 | every ELF in the tree must be `(1,40)` (`:2421-2423`); `sbin/adbd` must be static (`:2429-2433`); BusyBox interpreter/NEEDED contract (`:2451-2459`); shell syntax and forbidden-marker scans |
| `compress_ramdisk()` | 2519-2530 | Python `lzma` XZ, `CHECK_CRC32`, `FILTER_LZMA2`, preset `9|EXTREME`, `dict_size=8 MiB`, no BCJ filter (in-kernel `xz_dec` supports CRC32/None only) |
| `build_cpio()` | 2532-2548 | `cpio --null --create --format=newc --owner=0:0 --reproducible`, epoch 0, must start `070701` |
| `extract_or_read_dtb()` | 2550-2565 | `--dtb` is mandatory for the generated envelope; FDT magic; `totalsize` at most the file size and at most `EVT_PADDED_SIZE` |
| `padded_dtb()` | 2567-2572 | pad to `0x10000`, rewrite the big-endian `totalsize` |
| `system_map_end()` | 2574-2592 | `_text`/`_end` → `physical_end = KERNEL_ADDR + _end - _text` |
| `package_boot()` | 2594-2690 | envelope must be canonical 16 MiB (`:2597`); address/page/dt contract `(KERNEL_ADDR, TAGS_ADDR, PAGE_SIZE, 0)` (`:2602`); empty payload fields (`:2604`); `bootopt=64S3,32N2,32N2` prefix at 64..576 (`:2606`); zImage magic at `+0x24` and start/end `(0, len)` at `+0x28` (`:2609-2613`); MKIMG header (magic, name `KERNEL`, size at +4) then `zImage + 64 KiB DTB`; payload must not overlap RAMDISK_ADDR (`:2623`); decompressed kernel at most ATF_START and below RAMDISK_ADDR (`:2629-2632`); ramdisk inside `ATF_END..RAMDISK_END_LIMIT` (`:2634`); Android ID at 576 (`:2644`); 16 MiB overflow error (`:2658`) |
| `main()` | 2694-3308 | refuses overwrite; `--ramdisk-address` default `RAMDISK_ADDR`; manifest `name=libreecho-mt8163-arm32-v97-recovery`, `status=PREPARED_NOT_FLASHED` (`:3072`, `:3075`); prints `boot_image`, `boot_sha256`, `ramdisk`, `ramdisk_sha256`, `manifest` |

### `tools/mt8163-arm32/verify_recovery_image.py`

| Item | Line | Value / rule |
|---|---|---|
| constants | 24-41 | `ANDROID_MAGIC`, `RAMDISK_COMPRESSION`, `RAMDISK_XZ_MAX_DICT_SIZE = 8<<20`, `XZ_MAGIC`, `XZ_CHECK_CRC32 = 00 01`, `MKIMG_MAGIC`, `FDT_MAGIC`, `PAGE=0x800`, `MKIMG_SIZE=0x200`, `IMAGE_SIZE=0x1000000`, `KERNEL_ADDR=0x40008000`, `RAMDISK_ADDR=0x43478000`, `RAMDISK_END_LIMIT=0x44400000`, `TAGS_ADDR=0x48000000`, `ATF_START/ATF_END`, `DTB_SIZE=0x10000`, `ZIMAGE_MAGIC` |
| pinned hashes | 43-62 | zImage, System.map, connectivity importer/stock system, envelope, init |
| `validate_mkimg_header()` | 268-281 | magic, name `KERNEL`, and name byte 14 must be NUL because LK compares the name as a C string |
| `elf_info()` | 415-491 | pure-Python ELF32 parser: class, endianness, machine, PT_INTERP, DT_NEEDED |
| envelope check | 2590-2601 | length + magic, equals `generate_boot_envelope()`, sha equals `BOOT_ENVELOPE_SHA256` |
| header check | 2596-2612 | address/geometry tuple vs envelope, `bootopt=64S3,32N2,32N2` at 64..576, header equality outside payload and id fields |
| MKIMG/zImage/DTB | 2620-2652 | kernel size == `MKIMG_SIZE + payload`, zImage byte-identical, magic and start/end, DTB exactly `0x10000`, totalsize, raw DTB hash and zero padding |
| ramdisk placement | 2655-2664 | ramdisk offset `align(PAGE+kernel_size)`, byte-identical, all padding zero, Android ID match |
| physical ordering | 2667-2671 | `KERNEL+payload < runtime_end <= ATF_START < ATF_END <= RAMDISK_ADDR < ramdisk_end <= RAMDISK_END_LIMIT < TAGS_ADDR` |
| initramfs | 1297-2226 | manifest-driven: every member hash and mode, ELF class/machine, symlink graph, SSH/UI/mDNS/connectivity/payload/target-identity contracts |

### `tools/mt8163-arm32/verify_radar_puffin_dtb.py`

| Item | Line | Value |
|---|---|---|
| node paths | 21-26 | `topckgen@10000000`, `scpsys@10006000`, `pinctrl@10005000`, `mt_soc_dl1_pcm@11220000`, `audiosys@11220000`, `pwrap@1000d000/mt6323/mt6323keys` |
| action key | 28-31 | `/action_key/action@36`, GPIO 36, keycode `0x8A`; mute keycode `0x71` (line 32) |
| audio ids | 33-35 | 24M clock ID 3, power-domain ID 5, codec MCLK 9.6 MHz |
| clock/pinctrl names | 37-56 | nine AFE clock names, nine pinctrl state names |
| `verify_dtb()` | 211+ | fdtget-based; dispatch comes from `verify_target_dtb.py:13-19` (`DTB_VERIFIERS = {'radar_puffin': verify_dtb}`) |

### `tools/mt8163-arm32/build_wifi_dtb.py`

| Item | Line | Value |
|---|---|---|
| stock envelope pins | 24-31 | `SOURCE_BOOT_SIZE=0x1000000`, `SOURCE_BOOT_SHA256=c0f52a3b...`, `PAGE_SIZE=0x800`, `MKIMG_SIZE=0x200`, `EVT_PAYLOAD_OFFSET=0x585185`, `EVT_RAW_SIZE=0xC875`, `STOCK_EVT_SHA256=f44630ba...` |
| stock nodes | 33-62 | CONSYS `18070000`, INFRACFG, PWRAP/MT6323 keys, PIO `10005000`, codec `i2c@11009000/tlv320aic32x4@18`, IMGSYS, SPI `1100a000`, AFE/AUDIOSYS |
| audio/board cells | 58-93 | codec phandle 0x49, MCLK `0x927c00`, VIO18, extamp pinmux `0x7A00` (GPIO122), DAC-mux `0x7C00` (GPIO124), I2S pinmux tuples, phandles 0x4A-0x50 |

### Initramfs build rules

There is no Makefile. The rules live in the builder: overlay table and modes
(`build_recovery_image.py:737-889`), `/init` must be the audited
`libreecho-init` with sha `8206b06e...` (`:64`, `:837-851`), newc cpio at epoch 0
(`:2532-2548`), XZ CRC32/LZMA2 with an 8 MiB dict (`:2519-2530`), and an
ARM32-ELF-only tree (`:2421`).

---

## 3. How the ARM32 initramfs is built

Composition: everything is staged into a `mkdtemp` dir, then packed with cpio and
xz. Nothing persists except the outputs.

1. `add_overlay()`: static shell and shell-script tree from
   `tools/mt8163-arm32/initramfs/`. It holds `libreecho-init` (147 KB, PID 1),
   `libreecho-update`, `libreecho-update-fetch`, `libreecho-bootctl` wrapper
   scripts, `libreecho-generation*`, `libreecho-data-cleanup`,
   `libreecho-vendor-import`, `libreecho-recovery-net-{up,down}`,
   `libreecho-recovery-ap-{probe,ready}`, `libreecho-mdnsd`,
   `libreecho-reconcile-features`, `libreecho-local`, `libreecho-ping`,
   `libreecho-wifi`, `libreecho-config-migrate`, init.rc files, `default.prop`,
   `profile`, `udhcpc.script`, `regulatory.db{,.p7s}`, vendor-asset TSVs, and the
   core license bundle (`initramfs/usr/local/share/licenses/libreecho-core/`).
2. BusyBox 1.37.0 plus the musl loader, with applet symlinks generated under
   `qemu-arm-static`.
3. `sbin/adbd`: static ARM32 from AOSP `system/core` at a pinned commit. It
   requires an exported UAPI tree.
4. OTA tools: `libreecho-bootctl`, `libreecho-update-verify`, `ota-public-key.hex`,
   profile and channel files.
5. Optional payloads: audio probe plus tinyplay/tinycap/tinymix; iwconfig; UI
   bundle (`libreecho-web`, `libreecho-radiod`, and others); mDNS runtime
   (Avahi/D-Bus); AirPlay (embedded nqptp/shairport-sync/avahi/dbus or an
   external SquashFS payload); TTS/wakeword/STT/assistant payloads (external, not
   embedded); SSH (dropbear/dropbearkey/scp, opt-in); WMT connectivity helpers;
   recovery AP (hostapd/dnsmasq/iw plus `libreecho-recovery-button`);
   wpa_supplicant 2.10. All-or-nothing groups are enforced in `main()`
   (`build_recovery_image.py:2850-3070`).

Toolchains: three, all cross, none prebuilt in-tree.

| Consumer | Compiler | Evidence |
|---|---|---|
| busybox, musl loader, audio tools, OTA verifier, wpa_supplicant, sendspin/connectivity | `armv7-alpine-linux-musleabihf-*` (musl 1.2.5/1.2.6, built from source) | `musl/build_musl.sh:44-99`, `busybox/build_busybox.sh:57-99`, `build/ci/build-public-toolchain.sh:1-100` |
| adbd, recovery-AP, UI bundle, AirPlay | `arm-linux-gnueabihf-*` (glibc armhf) | `build.sh:74` (`CROSS`), `button-backport.yml:43-54`, `mt8163-arm32/recovery-ap/README.md` |
| bootctl | musl, dynamic against the staged loader | `build.sh:1188-1194` |

Pins are in each component's `SOURCE.lock` (`musl/SOURCE.lock`,
`busybox/SOURCE.lock:1-8`, and so on), and each builder hash-checks them before
use. musl is built, not downloaded: `musl/build_musl.sh` takes
`--archive FILE --output DIR --cc COMPILER` and requires the sibling
`armv7-alpine-linux-musleabihf-{gcc,ar,ranlib,ld}` files
(`musl/build_musl.sh:44-60`).

Compression: XZ with the CRC32 check, LZMA2 preset 9e, dict 8 MiB. The kernel
`xz_dec` accepts only CRC32 or None checks and needs a bounded single-call
dictionary (`build_recovery_image.py:2519-2530`).

Outputs: `$RUN/boot.ramdisk.cpio.xz`, with `cpio_size`, `ramdisk_size` and hashes
in `manifest.json`.

Recorded sizes: none for the product image. A search of Platform for
`cpio_size|ramdisk_size|MiB` finds only code. Nearest data points: the Phase 4
test initramfs is 682,618 B gzipped (`artifacts/phase-04/initramfs/MANIFEST.txt`),
the Phase 4 ARM64 `Image` is 8.0 MB uncompressed
(`artifacts/phase-04/kernel-build/arch/arm64/boot/Image`), and
`airplay/README.md:126` only asserts that payloads stay inside the fixed 16 MiB
envelope. The 16 MiB cap is enforced at `build_recovery_image.py:2658`.

Hermeticity on an x86_64 Arch host: the Python stages are hermetic. All inputs
are explicit files with hashes, staging is a temp dir, cpio uses
`--reproducible`, timestamps are epoch 0 and xz is deterministic. What is not
hermetic or runnable from the repo alone:

- the two cross toolchains (musl armv7 and glibc armhf), which must already exist;
- `qemu-arm-static` on `PATH` (default `--qemu-arm qemu-arm-static`), needed to
  inventory BusyBox applets and to run staged ARM binaries in several tests;
- `cpio`, `readelf` (binutils), `fdtget`/`dtc` (device-tree-compiler), a host
  `cc` for C contract tests, `/bin/busybox`, `mksh`, `squashfs-tools`, `nodejs`
  and `espeak-ng-data` for the platform test lane;
- AOSP `system/core`, a kernel UAPI export, and every component archive the
  Product workflow downloads.

On Arch these map to `qemu-user-static`, `cpio`, `binutils`,
`device-tree-compiler`, `squashfs-tools`, `mksh`, `nodejs` and python.
`arm-linux-gnueabihf-gcc` and an `armv7-alpine-linux-musleabihf` toolchain are
not in the official repos. They must be built (musl-cross-make as in
`build-public-toolchain.sh`) or installed from AUR [INFERENCE]. Building the musl
toolchain from source is the documented public path.

Separate and unrelated: `tools/mt8163-arm32/ota-test-vm/build-initramfs.sh` builds
an armmp/glibc QEMU test initramfs inside a `linux/arm/v7` Debian container
(`:1-8`) for the OTA matrix. Do not confuse it with the product image.

---

## 4. Consumers of `tools/mt8163-arm32/libreecho_platform_targets.py`

`TARGETS` dict (`:24-39`):

```python
TARGETS = {
    'radar_puffin': {
        'release_slug': 'radar-puffin', 'hw_profile': 'radar_puffin@1',
        'fastboot_products': ('RADAR',), 'dtb_verifier': 'radar_puffin',
        'audio': {'speaker_chain': 'radar_puffin', 'codec_profile': 'Radar',
                  'hp_driver_gain': 6, 'pre_gain_db': 0.0, 'bass_makeup_db': 0.0},
    },
    'biscuit': {
        'release_slug': 'biscuit', 'hw_profile': 'biscuit@0',
        'fastboot_products': ('BISCUIT',), 'dtb_verifier': 'radar_puffin',
        'audio': {'speaker_chain': 'biscuit', 'codec_profile': 'Flat',
                  'hp_driver_gain': 6, 'pre_gain_db': 6.0, 'bass_makeup_db': 2.5},
    },
}
```

`identity_bytes(target, digest=None)` (`:83-91`) renders ASCII key=value lines:

```
target_id=<target>
release_slug=<release_slug>
hw_profile=<hw_profile>
[descriptor_sha256=<64 lowercase hex>]
```

The image stores this as `/etc/libreecho/target` (`build_recovery_image.py:890-905`),
and `verify_recovery_image.py:1278-1296` checks it.

Import sites (`--target`, `TARGETS`, `identity_bytes`, `add_target_arguments`):

| File | Line | Uses |
|---|---|---|
| `generate_boot_envelope.py` | 15 | `add_target_arguments`, `get_target`, `validate_target_arguments` |
| `build_recovery_image.py` | 25 | plus `identity_bytes`, `audio_profile_bytes` |
| `verify_recovery_image.py` | 21 | same as the builder |
| `verify_target_dtb.py` | 8 | target → DTB verifier profile |
| `ota/make_ota_bundle.py` | 18 | target and descriptor in the signed manifest |
| `ota/feature_manifest.py` | 15 | `TARGETS`, `get_target` (board validation) |
| `recovery-install/build_install_bundle.py` | 44 | `DEFAULT_TARGET`, `get_target`, `identity_bytes` |
| `test_multi_target.py` | 99-130, 209 | parity tests |
| `airplay/test_audio_engine_sendspin.py`, `test_wide_output.py`, `test_radar_speaker_equivalence.py` | 63 / 21 / 214 | audio profile |
| `airplay/audio_engine.c` | 55 | comment: the engine reads the table's policy |
| Product `build/ci/platform-target-args.py` | n/a | probes `--help`, then passes `--target` and `--target-descriptor-sha256` |

There is no registry. A profile is a directory plus this table
(`experiments/phase-05/boot-shape-decision.md`, Inputs table). A new
`tools/mt8167-arm64/` directory must ship its own copy of
`libreecho_platform_targets.py`, because all imports are sibling-module imports
(for example `build_recovery_image.py:23-26`, with the `sys.path` insertion at
`:22-23`).

---

## 5. Test conventions

- Style: stdlib `unittest`, no pytest, no fixtures outside the file. Files are
  `test_<subject>.py` beside the code under `tools/mt8163-arm32/` (and in
  `airplay/`, `ota/`, `mdns/`, `sendspin/`, `recovery-install/tests/`). Some
  suites are scripts with their own main (`airplay/test_*.py`,
  `ota/test_dev_discovery.py`).
- Run from the tools directory, because imports are sibling-relative:
  `cd tools/mt8163-arm32 && python3 -m unittest -v test_recovery_image_tools test_build_wifi_dtb test_verify_radar_puffin_dtb test_recovery_ap`
  (`button-backport.yml:33-35`).
- Full lane (`ota-release.yml:161-200`): `python3 -m unittest -q` over
  `test_multi_target.py`, `test_build_wifi_dtb.py`,
  `test_verify_radar_puffin_dtb.py`, `test_recovery_image_tools.py`,
  `test_recovery_ap.py`, `test_local_install_adoption.py`,
  `test_issue_169_ota_health.py`, `test_early_control_plane.py`,
  `test_issue_157_ota_rollback_finalization.py`,
  `test_operator_stale_lock_recovery.py`, `mdns/test_runtime.py`,
  `test_qualification.py`, `test_ssh_runtime.py`, `test_local_services.py`,
  `test_vm_profile.py`, `test_vendor_import_compat.py`,
  `test_source_offer_tools.py`, `recovery-install/tests/test_build_install_bundle.py`,
  `.../test_installer_boot_write.py`, `.../test_direct_userdata_install.py`,
  `.../test_direct_nonce.py`, `ota/test_ota_v2_implementation.py`,
  `test_ota_v3_*.py`, `test_issue_231_fixed_boot_store.py`,
  `test_reboot_bootloader.py`, `test_issue_195_no_expdb_marker.py`,
  `test_ota_log.py`, `ota/test_{feature_provenance,service_identity,dev_discovery,release_source}.py`,
  `test_active_device_ping.py`.
- Syntax gates: `python3 -m py_compile` on the builders, `bash -n` over every
  tracked `*.sh`, and `/bin/busybox sh -n` over the initramfs scripts
  (`ota-release.yml:224-258`).
- Skips are used for missing host tools (`@unittest.skipUnless(shutil.which(...))`),
  but CI then greps the log to require specific `ok` lines for the Opus paths
  (`ota-release.yml:206-222`): a skip is a lost contract.
- `test_multi_target.py` (`:1-2`: "Multi-target contracts on public host
  fixtures; never touches real devices") is the parity suite for
  radar_puffin/biscuit. Every Product-probed tool must advertise
  `--target`/`--target-descriptor-sha256` (`:41-49`); both targets must produce
  byte-identical envelopes (`:51-70`); unknown targets must fail before inputs
  (`:72-77`); it also covers DTB dispatch, identity bytes, descriptor-digest
  format, audio profile rendering, cross-target OTA/install manifest rejection,
  bootctl partition-name layouts, staged-tree diff and recovery preflight. It is
  the template for an ARM64 parity suite.
- Product mirrors these as `repos/LibreEcho/tools/test_*.py` and
  `repos/LibreEcho/build/tests/`, including `test_target_manifest.py` and
  `test_multi_target.py` that assert `build.sh` contains the literal
  `TOOLS_DIR="$TOOLING_SRC/tools/mt8163-arm32"`
  (`repos/LibreEcho-Platform/tools/mt8163-arm32/test_recovery_image_tools.py:4254`).

---

## 6. Second SoC/arch profile today, and hardcoded `mt8163-arm32`

What exists:

- The Product descriptor has `soc`/`arch` fields, but both are `const`:
  `release/target.schema.json` pins `soc: "mt8163"`, `arch: "arm32"`,
  `kernel.defconfig: "mt8163_arm32_defconfig"`,
  `kernel.dtb: "libreecho-radar-puffin.dtb"`, `platform.tools_profile:
  "mt8163-arm32"`, `platform.dtb_verifier: "radar_puffin"`, and the target ID enum
  to `radar_puffin|biscuit`. `target_registry.py:15` hardcodes
  `KNOWN_TARGETS = (DEFAULT, "biscuit")`.
- The Linux repo already models the Lidar target: `libreecho/targets.json` has
  `lidar` = `{arch: arm64, defconfig: mt8167_arm64_defconfig, dtb:
  mediatek/libreecho-lidar.dtb, image: Image}`, and
  `libreecho/validate_targets.py:8-13` plans separate `build_arm32`/`build_arm64`
  lanes with `IMAGES = {"arm": {"zImage"}, "arm64": {"Image"}}`.
  `arch/arm64/configs/mt8167_arm64_defconfig` exists. Product does not know
  `lidar`: its registry, schema and `build.sh` (`ARCH=arm`, `zImage`) have no
  ARM64 branch.
- Platform's target table has no `soc`/`arch` field at all. It has only
  `release_slug`, `hw_profile`, `fastboot_products`, `dtb_verifier` and `audio`.
- `build.sh:404` is the single indirection point
  (`TOOLS_DIR="$TOOLING_SRC/tools/$TOOLS_PROFILE"`), fed by
  `build/ci/validate-targets.py:21`. Every other arch-specific value in build.sh
  is literal (`ARCH=arm` at `:859/:879/:1050-1058`, `zImage`, `ld.bfd`,
  `arm-linux-gnueabihf-`).

Grep counts for `mt8163-arm32|mt8163_arm32` (case-insensitive, gitignore on):

| Repo | Files matching | Key sites |
|---|---|---|
| LibreEcho-Platform | 30 | `.gitignore:54`; `README.md` (9 hits); both workflows (path filter `button-backport.yml:7`, `ota-release.yml`); `build_recovery_image.py:73,3072`; `busybox/build_busybox.sh:112`; all `COMPONENTS.json`/notices paths; every builder's `config_path`; `test_multi_target.py:576-645`; `test_recovery_image_tools.py:4254,5463`; `ui/build_ui_bundle.sh:8,297` |
| LibreEcho (Product) | 26 | `build/build.sh:54,404`; `build/ci/validate-targets.py:21`; `release/targets/{radar_puffin,biscuit}.json:28`; `release/target.schema.json:84,101`; `release/components.json:108,139`; `build-release.yml:390,963-964,1016-1019,1354-1393`; `build/check_marker_contract.sh:38-39`; `build/ci/{ota_v2_product,fetch-public-deps}.py`; `build/tests/test_multi_target.py:452`, `test_ota_v2_*`, `test_sendspin_inputs.py` |
| LibreEcho-Linux | 12 | `arch/arm/configs/mt8163_arm32_defconfig`; `README.md:129,159,216,233`; `Documentation/arm/libreecho-mt8163-defconfig.md:3-13`; `libreecho/{targets.json,parity.json,next_lts_canary.sh}`; `tools/mt8163_*_contract_test.py`; `drivers/misc/mediatek/mt8163-connectivity/test_*.py` |
| LibreEcho-Installer-Web | 4 | USB product string `MT8163-ARM32-ADB` (`NOTES.html:81`, `index.html:165`, `js/device.js:146`, `js/test_resume_28.mjs:191`). This is a device identity string, not a path |

Consequence for Phase 5: a `tools/mt8167-arm64/` profile must be added to
Platform (new directory, own target table, its own image-builder and verifier
copies with ARM64 constants), and Product must be extended (`KNOWN_TARGETS`,
schema consts, `build.sh` arch/image selection, OTA and installer target
plumbing). Product `build.sh:413-416` will refuse to build until the new tools
advertise `--target` and `--target-descriptor-sha256`.

---

## Gaps and unverified items

- No recorded product initramfs size, boot image size or 16 MiB headroom exists
  anywhere in the repos. Phase 5's size-budget task has no prior baseline.
- Hardware acceptance, LK BCB behaviour and slot fallback are outside this
  read-only map (see `experiments/phase-04/notes.md`,
  `experiments/phase-05/boot-shape-decision.md`).
- The ARM64 envelope values to reuse are in
  `experiments/phase-04/pack_boot.py:54-72`: kernel `0x40080000`, ramdisk
  `0x44000000`, second `0x40F00000`, tags `0x4E000000`,
  `bootopt=64S3,32N2,64N2`, ARM64 `ARMd` magic at Image+0x38, max DTB `0x80000`,
  page 2048, 16 MiB. These differ from every ARM32 value above, so Phase 5 must
  fork them.
