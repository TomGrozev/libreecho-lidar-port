# Lidar boot image packager

Host-side tool for Phase 4. It reads the stock boot image read-only, then writes a
development image with a new ARM64 Image, a new Lidar DTB and the stock ARM32 ramdisk.

No hardware was used for this work. The tool does not boot, flash, reboot or push a
device. It makes no bootability or hardware-support claim, and it produces no signature.

## Build target and inputs

The `lidar` target builds `arch/arm64/boot/Image` and
`arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb`. The packager takes those two files
and the stock image.

| Input | Size | SHA-256 |
| --- | --- | --- |
| `dumps/20261110-lidar-readback/boot_a.bin` | 16 777 216 | `eec8da659fd81352c62e22eb9e2fac174efd180ab03e5ab6c88e1f0135df090c` |
| Stock appended DTB index 4, PVT | 54 016 | `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f` |
| Stock ramdisk gzip | 4 117 193 | `ab2e6a4a4c9174eef2acfdf4e34914a5c71694aa0f1d26a04c7140febe44c2c1` |
| Stock kernel section | 6 227 381 | `e02a41c9817afe97b8116babbed09dc0b6b1de23c5413ee564798c199434389e` |
| Stock trailer certificate | 1 077 | `2f4dbaed1afb3ae78d8362a0f5ef411ab52f5568f4b4fbc2e203fddbf0541ce6` |

The verified host build produced these new inputs and image. These are the current
artifacts, rebuilt on 2026-11-15 after the USB config fixes described below:

| Output | Size | SHA-256 |
| --- | --- | --- |
| ARM64 `Image` (current) | 8 215 040 | `a2fd2d9ba9ceb12afbad73f5d3a9bfae41bda68ec3b6c6a3c085a3f07a04f36c` |
| `libreecho-lidar.dtb` | 13 527 | `0ccdcc0b0466743bf457e08af4051c0aa0227fd5d0c54fdf4361c84e5228f9be` |
| `boot-lidar-development.img` (current) | 16 777 216 | `b2e01eb5bc7db3f783760a97c90a40840852751e03ea0f7c020e640da9b2e2a9` |

Historical first build, 2026-11-15, before the config fixes. The DTB is unchanged; the
first `boot_a` flash used the 3d2997 image, so it remains the hardware-relevant
reference:

| Output | Size | SHA-256 |
| --- | --- | --- |
| ARM64 `Image` (first build) | 8 215 040 | `5abfde45c5037a01e4fe1f2f3ff7db1ba54d39a12475c018cc56c669e5b45406` |
| `boot-lidar-development.img` (first build) | 16 777 216 | `3d2997e6fe33c00e76632d1a2c59ed675c0e77d469a9de5e5d5440d0f5975c16` |

The packager prints the input and image SHA-256 values on every pack and verify run.

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

Run these commands from the project root. The kernel output directory is separate from
the source tree.

The verified run used local Clang 23.1.5, LLD and DTC 1.8.1 under
`/tmp/lidar-arm64-tools/root`. It did not install system packages.

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

The build writes:

- `artifacts/phase-04/kernel-build/arch/arm64/boot/Image`
- `artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb`

## Package

```sh
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel artifacts/phase-04/kernel-build/arch/arm64/boot/Image \
  --dtb artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --output artifacts/phase-04/boot-lidar-development.img
```

The output is `artifacts/phase-04/boot-lidar-development.img`. The tool creates the
`artifacts/phase-04` directory when needed.

## Verify

```sh
python3 experiments/phase-04/pack_boot.py \
  --verify artifacts/phase-04/boot-lidar-development.img \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel artifacts/phase-04/kernel-build/arch/arm64/boot/Image \
  --dtb artifacts/phase-04/kernel-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb
```

Verify parses the image again. It checks the header, MTK header, decompressed kernel,
DTB collection, ramdisk, Android id and the zeroed trailer against the supplied inputs.
It prints `verify: OK` and exits 0 on success.

## Tests

```sh
python3 experiments/phase-04/test_pack_boot.py -v
```

The tests build a synthetic 16 MiB stock image in a temporary directory. They cover a
round trip, deterministic output, a dropped certificate, retained stock DTBs, a tampered
ramdisk, a changed DTB, a retained trailer, a bad kernel magic, an oversized kernel, a
malformed DTB, a wrong compatible string, a wrong PVT hash, malformed stock headers,
truncation and nonzero padding. No device access is needed.

## Behaviour

The tool mirrors the stock wrapper. It keeps the 2 048 byte page size, the load
addresses, the MTK header, the appended DTB collection and the 16 MiB envelope. It
replaces only appended FDT index 4. The other 18 stock blobs stay byte-identical, so
the LK board-id selection table still has every entry it had before.

The new Image must carry `ARMd` at offset `0x38`. The new DTB must parse as an FDT and
must contain `amzn,lidar-pvt` in its root compatible list.

The kernel is gzipped with a fixed header: no file name, zero mtime and OS byte 255.
The deflate bytes depend on the local zlib build. Identical inputs on the same host
produce identical output. Verify compares the decompressed kernel data, so a different but
valid gzip encoding still passes.

The trailer is written as zeros. The stock DER blob is not copied, so no stock
signature remains and no new signature is made. A bootloader that requires this blob
or a verified-boot signature is outside what this tool can satisfy.

## Failure behaviour

The tool exits with status 2 and an error line for any unexpected layout. It rejects a
stock image that is not exactly 16 MiB, has different addresses or page size, has a
different MTK header, has a different DTB count or PVT hash, or has unexplained trailer
bytes. It rejects a kernel that is not an ARM64 Image, a DTB without the PVT compatible
string, a kernel and ramdisk that overflow the 16 MiB envelope, and an output that fails
verify. It refuses to write over the stock image or over either input file.

## Limits

This is host-side image construction. It cannot show that the image boots, that the
bootloader accepts the zeroed trailer, or that the new kernel runs on the device. No
hardware evidence was collected for this image. Those claims need separate hardware
evidence. The tool does not read the device `board_id`, so the existing LK selection
logic is unchanged. The LK maximum DTB size check is not modelled; the tool enforces the
16 MiB envelope only.

## Host evidence, 2026-11-15

- `make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 Image dtbs -j8` passed.
- `/tmp/lidar-arm64-build/.config` contains `CONFIG_COMPAT=y`.
- `python3 -B libreecho/test_targets.py` passed 12 tests.
- `python3 -B libreecho/validate_targets.py` validated three targets and two unique builds.
- `python3 -B libreecho/run_contract_tests.py` passed all 23 contract tests.
- `python3 experiments/phase-04/test_pack_boot.py -v` passed 19 tests.
- The pack and verify commands above passed on the real stock image and the new kernel outputs.
- Direct `dt-validate` checks cleared the Lidar board, MMC and pinctrl diagnostics. The
  remaining `syscon` and `mmsys` diagnostics also occur on the unmodified MT8167 Pumpkin DTB.
- The GitHub Actions workflow parsed as YAML and contained the `arm64_kernel` job. The CI lane
  has not run because no push is authorized.

The MTK filler starts at offset `0x28` in the stock header. A regression test uses this literal
offset because the first synthetic fixture incorrectly used `0x2c` and rejected the real image.

## Hardware gate attempt, 2026-11-15

The owner approved one fastboot boot and read-only observation. The device was already in
fastboot. This command transferred the image but did not boot it:

```sh
/tmp/lidar-arm64-tools/root/usr/bin/fastboot boot artifacts/phase-04/boot-lidar-development.img
```

Kaeru returned `FAILED (remote: 'unknown command')` for the boot request. The device remained in
fastboot and still reported `product: LIDAR`. `current-slot` was empty. No partition write or
development-kernel boot occurred. The Phase 4 gate remains open.

The owner then approved one `boot_a` write, one reboot and read-only observation. These commands
ran once:

```sh
/tmp/lidar-arm64-tools/root/usr/bin/fastboot flash boot_a artifacts/phase-04/boot-lidar-development.img
/tmp/lidar-arm64-tools/root/usr/bin/fastboot reboot
```

Fastboot reported `Writing 'boot_a' ... OKAY` and `Rebooting ... OKAY`. It also warned that the
reported `boot_a` partition size was zero while it skipped the AVB footer copy. No independent
partition readback ran. Only `boot_a` was selected for the write. `boot_b` and the boot chain were
not changed.

After the reboot, no fastboot device or other Lidar USB interface appeared. ADB did not appear
within 45 seconds. This provides no development-kernel boot evidence, so the result is
inconclusive and the Phase 4 gate is not met. No further reboot, power cycle, BROM action, slot
switch, write or stock restoration was approved or attempted.

## BROM readback, 2026-11-15

The owner approved a read-only BROM readback of `boot_a`, `boot_b` and `misc` only. The
reads used the existing da0 path and completed. No write, reboot, restore or slot switch
was approved or performed. New files under `dumps/20261115-lidar-phase4/`:

| File | SHA-256 |
| --- | --- |
| `boot_a.bin` | `3d2997e6fe33c00e76632d1a2c59ed675c0e77d469a9de5e5d5440d0f5975c16` |
| `boot_b.bin` | `3baf114f6382492e706795b229c4ff08f4fe62da6cf2172ba164830b518421b1` |
| `misc.bin` | `1c53c1f0ab54c0151c3205b986540fa4fbd8119840be973fb08bb52e90a630bd` |

Findings:

- `boot_a` is byte-identical to the first development image (3d2997), confirming the
  earlier flash reached the slot as reported and that nothing on-device overwrote it.
- `boot_b` differs from its 2026-11-10 readback
  (`e83621a9df5126a5e57e36fecfc21339ed0054a2e6776397a3ac0149b02e983a`). The new `boot_b`
  kernel and ramdisk sizes are 6 227 391 and 4 118 507 bytes, against the original stock
  `boot_a` values of 6 227 381 and 4 117 193. Normal userspace automatic update is a
  possible explanation. This is not established causation and is not proof that a kernel
  booted.
- `misc` differs from the 2026-11-10 readback in exactly two bytes, at decimal offsets
  870 and 871.

The revised image has not been flashed. On-device `boot_a` still holds the old 3d2997
image as of this readback. The Phase 4 hardware gate remains open.

## USB config gap and revised image, 2026-11-15

Root cause for the missing device-side USB interfaces: the ARM32
`mt8163_arm32_defconfig` sets `CONFIG_USB_CONFIGFS_RNDIS=y` and
`CONFIG_USB_CONFIGFS_F_FS=y`, but the ARM64 defconfig omitted both. ADB and RNDIS could
therefore not appear even if normal userspace ran. Both options are now added to
`arch/arm64/configs/mt8167_arm64_defconfig`. Separately, two `f_fs.c` diagnostics changed
`%d` to `%zd` for `ssize_t` values after ARM64 compiler warnings.

The revised image was built cleanly after these format fixes; `pack --verify` passed and
`python3 -B repos/LibreEcho-Linux/libreecho/test_targets.py` passed 12/12. Its hashes are
the current entries in the table above (Image a2fd2d, boot image b2e01e; DTB unchanged).

Next proposed step, not yet authorized: an owner-approved
`fastboot flash boot_a` of the revised b2e01e image, a reboot, and read-only lsusb/ADB
observation.

## Revised image flash and approved BROM diagnostics, 2026-11-15

The owner approved flashing the revised b2e01e image to `boot_a`. The flash and reboot ran
under separate approval:

```sh
LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib \
  /tmp/lidar-arm64-tools/root/usr/bin/fastboot flash boot_a \
  artifacts/phase-04/boot-lidar-development.img
/tmp/lidar-arm64-tools/root/usr/bin/fastboot reboot
```

Fastboot reported `Writing 'boot_a' ... OKAY` and `Rebooting ... OKAY`. It warned again that
the reported `boot_a` partition size was zero, so it skipped the AVB footer copy. No other
partition was selected.

After the reboot, no MediaTek USB interface and no ADB interface appeared. A 90-second
`adb wait-for-device` returned with `adb devices` showing no device. The development kernel
is still unproven; nothing in this session is boot evidence.

Entry conditions recorded this session: reaching fastboot required the Action button held
and mains connected before USB, with the listener running before the connection. A USB-only
warm reboot lost the fastboot state. This sequence is now documented in
`experiments/phase-03/FASTBOOT.md`. It is a property of this unit's bring-up path, not a
portable requirement.

With separate approval, BROM diagnostics read three memory regions into
`dumps/20261115-lidar-phase4-revised/`:

| File | Source | Size (bytes) | SHA-256 |
| --- | --- | --- | --- |
| `ramoops.bin` | `0x44410000` | `0xe0000` | `bc21e4a108cac296b61f7d7c64c9b0fa0637a495c4ae60959564753d8a9ffe35` |
| `expdb.bin` | expdb partition | 10 MiB | `ae61838df7cfe6ce46648189d15501bacfff511a043bfc67e0a8b2746cef5f41` |
| `ram-console.bin` | `0x44400000` | `0x10000` | separately approved read |

Findings:

- Both RAM regions contain `RAM_RW` fill patterns after cold entry. The uploaded
  `MTK_DA_V5.bin` contains the matching RAM read/write self-test strings; the DA itself
  overwrote these regions before our reads. These dumps are not evidence about whether
  Linux wrote ramoops.
- `expdb.bin` contains binary LK/Kaeru data as expected for the installed chain, but no
  readable development-kernel banner.

No boot verdict follows from the RAM reads. The Phase 4 gate remains open.

## Diagnostic ADB image, 2026-11-15

`pack_boot.py` gained an opt-in `--diagnostic-adb` mode (`experiments/phase-04/pack_boot.py:869`).
The default pack path is unchanged and still uses the stock ramdisk bytes
(`experiments/phase-04/pack_boot.py:728`). In diagnostic mode the tool decompresses the
stock ramdisk, rewrites exactly two newc cpio entries, and recompresses with the same
deterministic gzip routine (`experiments/phase-04/pack_boot.py:381`, `diagnostic_ramdisk`):

- `init.rc` gets a ConfigFS gadget setup inside `on fs`, right after the
  `/dev/usb-ffs/adb` functionfs mount, and a separate
  `on property:sys.usb.ffs.ready=1` trigger that writes the UDC
  (`experiments/phase-04/pack_boot.py:352`). The UDC write stays out of `on fs`:
  binding the gadget before FunctionFS descriptors exist leaves adbd without usable
  endpoints (`experiments/phase-04/pack_boot.py:344`). No network ADB and no RNDIS
  setup are added.
- `default.prop` gets `ro.debuggable=1` and `ro.adb.secure=0`
  (`experiments/phase-04/pack_boot.py:320`). Existing property lines are replaced in
  place; missing ones are appended.

One parser fix came out of the real stock cpio: the archive uses 4-byte name
alignment, so an entry whose 110-byte header plus name does not land on a 4-byte
boundary carries two padding bytes before its data. `parse_cpio` now aligns the data
start to 4 bytes and keeps the stock padding bytes verbatim
(`experiments/phase-04/pack_boot.py:256`). The synthetic fixture in
`experiments/phase-04/test_pack_boot.py:83` builds its cpio with the same name
alignment, and its unaligned `act` entry (110-byte header plus a 4-byte name) needs
two pad bytes, so the fixture covers that path.

Verification runs the same checks in diagnostic mode plus
`validate_diagnostic_ramdisk` (`experiments/phase-04/pack_boot.py:412`): the output
cpio must have the same entry count and order as stock, every entry other than the
two diagnostic files must be byte-identical, the two rewritten files must match the
transforms exactly, and the tail padding must be unchanged.

### Host verification

- `python3 experiments/phase-04/test_pack_boot.py -v` passed 32 tests. The diagnostic
  tests cover the two-file-only change, the property values, the ConfigFS commands
  and the deferred UDC trigger, diagnostic verify acceptance, default verify
  rejection of a diagnostic image and the reverse, tampered-entry rejection, removal
  of the UDC trigger, the missing functionfs mount error, determinism, and the CLI
  pack and verify paths.
- The real diagnostic pack to
  `artifacts/phase-04/boot-lidar-diagnostic-adb.img` and its
  `--verify --diagnostic-adb` run both passed. The base development pack and verify
  also passed, and the base image hash stayed
  `b2e01eb5bc7db3f783760a97c90a40840852751e03ea0f7c020e640da9b2e2a9`.

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/phase-04/boot-lidar-development.img` (base, unchanged) | `b2e01eb5bc7db3f783760a97c90a40840852751e03ea0f7c020e640da9b2e2a9` |
| `artifacts/phase-04/boot-lidar-diagnostic-adb.img` (diagnostic) | `244622b17b32f31ece972f1d2a8ef973f6fc8315d73ff95f23426ad3fcc4bf5a` |

The diagnostic image uses the same ARM64 `Image` (`a2fd2d9b...`) and the same DTB
(`0ccdcc0b...`) as the base image. It differs only in the ramdisk, for the reasons
above. The kernel and DTB hashes stay as recorded in the table at the top of this
file.

### Diagnostic flash and negative result, 2026-11-15

The owner approved the diagnostic flash. The image hash was checked before the
flash. These commands ran once:

```sh
LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib \
  /tmp/lidar-arm64-tools/root/usr/bin/fastboot flash boot_a \
  artifacts/phase-04/boot-lidar-diagnostic-adb.img
/tmp/lidar-arm64-tools/root/usr/bin/fastboot reboot
```

Fastboot reported `Writing 'boot_a' ... OKAY` and `Rebooting ... OKAY`, with the same
zero-partition-size AVB footer warning as the earlier flashes. No other partition was
selected.

`adb wait-for-device` timed out after 90 seconds with no output. `adb devices` showed
no device. No kernel version string and no userspace property evidence was obtained.

What this rules out and what it does not:

- The stock legacy `android0` USB setup is no longer a sufficient explanation for the
  missing ADB interface, because the diagnostic ramdisk removes that explanation and
  ADB still did not appear.
- This does not rule out every userspace problem. The diagnostic ramdisk could still
  fail for another reason before adbd starts.
- An early kernel fault before USB init is a hypothesis. It is not proven. Nothing in
  this session shows whether the kernel started at all.

No further image flashes are approved or planned without new evidence. The next
decisive diagnostic is a 3.3 V UART console on the board, which would show kernel
boot messages directly. The Phase 4 hardware gate remains open.

## Kernel-only USB and firmware-reservation tests, 2026-11-15

A separate kernel-only diagnostic enabled `CONFIG_USB_G_SERIAL=y` in the temporary
build, without changing the repository defconfig. It used the stock ramdisk and the
original development DTB. `boot-lidar-serial-diagnostic.img` SHA-256 was
`f3d44229e3ff19e46842cb7d52e5bef6cb7da8ccb31b5e6f8f3f41b713a490ed`.
Pack verification passed. After an approved `boot_a` flash and reboot, no CDC ACM
device or MediaTek USB device appeared. This makes a failure before late kernel USB
initialization more likely, but does not prove which slot ran.

Static LK analysis then ruled out an AArch32-entry hypothesis. The 64-bit boot path
uses an ATF SMC to enter at EL2, the load address is valid, and the stock boot log
confirms this path. Comparing DTBs exposed a concrete omission: the development DTB
did not reserve ATF at `0x43000000–0x4302ffff`. The DTB now also preserves the stock
RAM-console and minidump regions. The rebuilt DTB SHA-256 is
`2abaea8b814543bb4b1a0f276d660c0eacf3006f4ca2a478d6ac01a3c081f862`;
`boot-lidar-development.img` is now
`8a3ca27fbfe214d0ef66c3e0fdcee0d87398711aa377c601a9c0ae142dfdd74b`.
Its real pack verification passed. After a separately approved `boot_a` flash and
reboot, the device again looked like a normal stock boot and no development USB
interface appeared. ATF reservation was therefore not sufficient. Keep the
reservations because firmware owns that memory, but do not claim they fixed boot.

## Persistent kernel logging, 2026-11-15

The packer now accepts `--cmdline-append`, with header-boundary, overflow and verify
coverage. All 40 `test_pack_boot.py` tests passed. The ARM64 defconfig enables
`CONFIG_PSTORE_BLK=y`; logging remains inactive unless the command line opts in.

The first persistent-log candidate used the stock ramdisk, the current DTS, and a
command-line-only pstore_blk console/kmsg target at the start of `swdl` (PARTUUID
`<PARTUUID_12>`). It also added the mainline-correct
`console=ttyS0,921600n1`; the inherited `ttyMT0` name cannot bind to the 8250 driver.
`CONFIG_USB_G_SERIAL` was off. The image is
`artifacts/phase-04/boot-lidar-diagnostic-pstore.img`, SHA-256
`f2c5f4c69615d1493a7e5f68a40098abe3817b3863382f9b167bb27d29a1a731`;
its kernel is `c2f29742d364b3e589f44f7ee07e94d1e20e39c42245beca36c25c66598f38ac`.

Before the approved flash, a full read of live `swdl` matched the archived all-zero
stock image: both SHA-256 values were
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`.
Fastboot wrote only `boot_a` and rebooted successfully. A complete post-boot BROM read,
`dumps/20261115-lidar-phase4/swdl-after-pstore.bin`, had the same all-zero hash. The
The kernel therefore did not reach working pstore_blk late initialization, or could not
use the development DTB's eMMC path. This does not locate the earlier failure.
Qualified 2026-11-15, see "Slot control failure and evidence invalidation" below: after
the first failed A boot the BCB selected B, so this zero-pstore read is not evidence
that this image ran.

A second candidate keeps the same kernel and command line but substitutes the
unmodified stock PVT DTB (`b5302d9e...`). Its image SHA-256 is
`913520bbc6e2e6df56a909731bce5742addcb2acaf4b9e06490354a8a5d3c211`.
Real pack verification passed. After a separately approved `boot_a` flash and reboot,
the full read `dumps/20261115-lidar-phase4/swdl-after-stockdtb-pstore.bin` was again
all zero with the baseline SHA-256. The custom DTS therefore does not explain the
missing late initialization. Qualified 2026-11-15, see "Slot control failure and
evidence invalidation" below: slot selection was not under control at this point, so
this differential is a preserved historical result, not proof about the DTS. The next
diagnostic is a minimal ARM64 entry stage, not another full-kernel configuration trial.

## Session end state

The device is in the post-reboot state after the ATF-reserved candidate, with no
hardware command active. `boot_b` was never written. No further image trial is
justified without early-boot evidence or another concrete static mismatch. The stock
kernel configuration could not be extracted with `extract-ikconfig`. The Phase 4
hardware gate remains open.

## Slot control failure and evidence invalidation, 2026-11-15

After the first failed A boot (the 3d2997 flash, no USB after reboot), the BCB
switched to B. Later `fastboot flash boot_a` writes plus a reboot did not select A.
Every prior conclusion drawn after that point from a normal boot appearance, a missing
USB interface, or a zero-pstore read is therefore not evidence that the flashed A
image ran; the device may have booted stock B. The affected conclusions above are
qualified inline, and the history is kept rather than deleted. This applies to the
normal-looking boots after the ATF-reserved and stock-DTB candidates and to the
zero-pstore reads of both pstore candidates.

Reference LK behavior, not to be retried: `oem print-bcb` returns an unknown-command
error, the host `--set-active` path reports that the device has no slots, a raw
`set_active:a` returns FAIL, and `set_active:_a` timed out twice.

## Verified BCB repair through misc, 2026-11-15

A fresh `misc` backup showed BCB bytes `00 41 42 42 01 8e 8f` (magic `ABB`, slot
suffix `a` at +0x364, priority 0x8e at +0x365, tries 0x8f at +0x366). The owner
approved changing only two bytes: +0x365 `8e` to `8f` (priority) and +0x366 `8f` to
`8e` (tries), making priority exceed tries for slot `a`.

The repaired image is `misc-slot-a.bin`, SHA-256
`9248bd41602b598703147a39a1c235daff374354f5978714315c2f0ce5b3549f`. It was written to
the misc partition, and the read-back `misc-after-slot-a.bin` is byte-identical.

Rule for every future A test: confirm A is selected before the flash. If a B fallback
occurs, repeat this verified BCB repair before flashing the next image. `boot_b` was
never written by us and stays stock.

## ARM64 entry proven, 2026-11-15

A minimal probe proves the boot chain executes our ARM64 code:

- Source: `experiments/phase-04/early_entry.S`. Host helper:
  `experiments/phase-04/build_early_entry_probe.py`. Image SHA-256
  `b57243017f118c5a7f3c83ef571255333530cd05d8787a1df1be93b17907045c`.
- The probe image masks DAIF, disables the MT8167 watchdog at `0x10007000` with key
  `0x22000000`, and loops. Host header check, disassembly, pack and verify passed.
- With A selected and a cold boot without the Action button, the owner observed a
  persistent blue light instead of the normal stock boot animation.

The persistent blue light shows that LK decompressed our probe image and ATF entered it.
The image format, load address and ARM64 architecture are proven viable end to end
through the stock chain. This is direct execution proof for the probe image; it says
nothing about the full kernel.

## Valid pstore candidate test, 2026-11-15

The owner approved flashing the pstore candidate
`artifacts/phase-04/boot-lidar-diagnostic-pstore.img` (SHA-256
`f2c5f4c69615d1493a7e5f68a40098abe3817b3863382f9b167bb27d29a1a731`) to `boot_a`. A was
explicitly selected; the reboot returned OKAY; the owner observed the blue light. Host
`lsusb` showed no LIDAR device and `adb devices` was empty.

A BROM read of `swdl` needed one transient handshake retry, then completed as
`dumps/20261115-lidar-phase4/swdl-after-valid-pstore.bin`, SHA-256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`. All 32 MiB are
zero: no `PSIG` record and no kernel text. The post-boot `misc` read,
`misc-after-valid-pstore.bin`, SHA-256
`9248bd41602b598703147a39a1c235daff374354f5978714315c2f0ce5b3549f`, matches the
patched A-active image byte for byte; BCB reads `00 41 42 42 01 8f 8e 00`, so no A/B
fallback happened.

Interpretation: this is the first valid full-kernel run with slot selection confirmed
on both sides of the reboot. No USB or ADB interface appeared, and pstore wrote no
panic record. This is not proof of a running userspace, and it does not locate where
the kernel stopped. Next planned diagnostic: a late-init forced panic after the
pstore backend initializes. Not yet built or run.

## Forced-panic probe, 2026-11-15

A driver under `drivers/misc` behind the default-n `CONFIG_LIBREECHO_PSTORE_PANIC_PROBE`
emits `[LIBREECHO-PSTORE-PROBE]` and then panics at `late_initcall_sync`. The defconfig
enabled it only for this build and was reverted afterwards. The image is
`artifacts/phase-04/boot-lidar-pstore-panic-probe.img`, SHA-256
`10ee2b653018476cdceb83937918e315138b49c6ca4448187736ac1463ce0ceb`; `pack_boot --verify`
passed. The owner approved the flash; `boot_a` flash and reboot returned OKAY with A
selected.

`dumps/20261115-lidar-phase4/swdl-after-panic-probe.bin`, SHA-256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`, is all zero.
`misc-after-panic-probe.bin`, SHA-256
`9248bd41602b598703147a39a1c235daff374354f5978714315c2f0ce5b3549f`, reads BCB
`00 41 42 42 01 8f 8e 00`; A remains active.

This shows only that no block record appeared. It does not show whether the forced
panic ran, and it does not show whether the kernel reached late init.

## Warm RAM reads after the panic probe, 2026-11-15

A BROM-only `mtk.py peek` avoids the DA self-test that overwrote RAM in the earlier
cold-entry reads. Results:

| File | Address | Size | SHA-256 | Content |
| --- | --- | --- | --- | --- |
| `warm-ram-after-panic.bin` | `0x44400000` | 1 MiB | `30e14955ebf1352266dc2ff8067e68104607e750abb9d3b36582b8af909fcb58` | all zero |
| `warm-log-buf-after-panic.bin` | `0x4085f388` | `0x20000` | `fa43239bcee7b97ca62f007cc68487560a39e19f74f3dde7486db3f98df8e471` | all zero |

The physical log buffer address comes from `System.map`: `__log_buf` at
`ffffffc0087df388` minus `_text` at `ffffffc008000000`, plus the kernel physical base,
so `0x4085f388`, size `0x20000`. A first attempt used `0x4087df388`, which is above the
32-bit physical range; it failed before any read and was corrected.

Neither dump contains printable runs or kernel markers. This is not evidence that the
kernel reached any stage.

## RAM marker control probe, 2026-11-15

A control image writes the marker string `LIBREECHORAMMRK!` at `0x44400000`, then
disables the watchdog and loops. Source:
`experiments/phase-04/early_entry_ram_marker.S`. Image:
`artifacts/phase-04/boot-lidar-ram-marker-probe.img`, SHA-256
`be44f7113732748363b5d17b6f339b79020f3604d0b683530875fbcfd21bc8ea`; pack verify passed.
The owner approved the flash; flash and reboot returned OKAY.

Two warm BROM 16-byte peek attempts then timed out after 300 seconds without
detecting the device. The owner found and resoldered a wire that had come undone; a
third peek then completed. `dumps/20261115-lidar-phase4/warm-ram-marker.bin` holds
16 zero bytes, SHA-256
`374708fff7719dd5979ec875d56cd2286f6d3cf7ec317a3b25632aab28ec37bb`; the marker string
`LIBREECHORAMMRK!` is absent.

The warm-reset RAM route therefore did not preserve a marker that the running image
had written. The earlier all-zero RAM and log-buffer reads are consequently not usable
kernel-stage evidence. Which reset stage clears the RAM is not established here.
After the repair, host `lsusb` showed only the MediaTek BROM device `0e8d:0003` and no
USB-UART adapter; there is no `/dev/ttyUSB*` or `/dev/ttyACM*`. A physical UART
remains the next dependable console.

A requested repeat of the manual warm read was cancelled: the owner reported no device
detection, so the peek never started.

A second control variant then attempted an automatic reset. Source:
`experiments/phase-04/early_entry_ram_marker_reset.S`. It writes
`LIBREECHORAMMRK!` at `0x44400000`, waits 5 seconds using `CNTFRQ_EL0`/`CNTPCT_EL0`,
and writes WDT_SWRST_KEY `0x1209` to `TOPRGU+0x14`; the register offset and key come
from `mtk_wdt.c`. Image:
`artifacts/phase-04/boot-lidar-ram-marker-warm-reset.img`, SHA-256
`d5b11ec04812efaf4bef2126170c0a35494fdcde4242ef2255bff039afc7a8a7`; it was
disassembled and passed `pack_boot --verify`. The owner approved the flash; `boot_a`
flash returned OKAY and `fastboot reboot` was issued. The `mtk peek` listener ran
before the connection; after about 2 seconds the owner held the Action button with USB
and mains connected. The BROM device was never detected, and the peek job was
cancelled. No automatic-reset marker file or result exists.

The owner's procedure was correct: `fastboot reboot` boots normally first, and the
Action button is only to catch the automatic reset. No claim follows about whether the
marker wrote or the watchdog reset fired. The warm-reset/BROM route remains unusable
as a log channel.

## Corrected pstore configuration, 2026-11-15

A configuration audit found two errors in the earlier pstore attempts:

- The base pstore image command line used PARTUUID
  `<PARTUUID_12>` with a typo in its fourth group. The actual `swdl` GUID in
  `dumps/20261110-lidar-readback/gpt.bin` is
  `<PARTUUID_12>` (both values redacted to the same placeholder).
- The forced-panic image used a wrong PARTUUID that matched the `swdl` GUID only in its
  first group (value redacted), omitted `best_effort`, and set
  `kmsg_size`/`console_size` to 262144. The driver takes those values in KiB
  (`fs/pstore/blk.c:22-45`), so the earlier forced-panic pstore attempt was not a
  valid logging configuration.

The corrected image is
`artifacts/phase-04/boot-lidar-pstore-panic-probe-corrected.img`, SHA-256
`9e59e1d8008cb39a9076ecf031ba50a98ab696384d21f9c01baf8de135077429`. It reuses the
panic kernel `571df0df02227987b781ce6e333a0a70d6d0c89d1228ba7c51f5f942abb59c65` and
DTB `0ccdcc0b0466743bf457e08af4051c0aa0227fd5d0c54fdf4361c84e5228f9be`. The command
line is:

```
console=ttyS0,921600n1
pstore_blk.blkdev=PARTUUID=<PARTUUID_12>
pstore_blk.best_effort=y
pstore_blk.pmsg_size=0
pstore_blk.console_size=64
pstore_blk.kmsg_size=64
pstore_blk.max_reason=5
```

`pack_boot --verify` passed and the panic string is present. The owner approved the
flash; `boot_a` flash and reboot returned OKAY.

`dumps/20261115-lidar-phase4/swdl-after-corrected-pstore.bin`, SHA-256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`, is all 32 MiB
zero: no `PSIG` record and no kernel text. `misc-after-corrected-pstore.bin`, SHA-256
`9248bd41602b598703147a39a1c235daff374354f5978714315c2f0ce5b3549f`, exactly matches
the prior A-active image.

Interpretation: this was a valid corrected run, and pstore still wrote nothing. The
kernel either did not reach late init or the eMMC/pstore setup failed; the result
cannot distinguish the two. The typo was not proven to be the whole root cause.

## Fastboot return and oem mem attempts, 2026-11-15

The no-UART research is recorded in `experiments/phase-04/no-uart-research.md`.

`early_entry_ram_marker_reset.S` now uses the proven Kaeru stage2 watchdog sequence:
kick `0x1971` to `TOPRGU+0x8`, set WDT_NONRST bit 2 at `+0x24`, write MODE
`0x22000014` to `+0`, `dsb`, then SWRST `0x1209` to `+0x14`. The image is
`artifacts/phase-04/boot-lidar-ram-marker-fastboot-reset.img`, SHA-256
`9eaf50eb006bbd695fa20dc1fadb60f4bdac16427e6887ff46f4c3e0b196406e`; it was built,
disassembled, and passed `pack_boot --verify`. The owner approved the flash; flash and
reboot returned OKAY.

About 12 seconds after the reboot, `fastboot getvar product` returned `LIDAR`.
A fastboot return without BROM entry or a power cycle is therefore proven.

Subsequent read attempts failed. `oem mem read 0x44400000 len 0x100` disconnected
("Status read failed (no device)"), a shortened `0x44400000 len 8` after fastboot
re-entry failed the same way, and an `oem mem` read of the watchdog at `0x10007000`
hung. In contrast, `oem kaeru-version` returned `v2.0.0-g8d24a1a-dirty`, so the
`fastboot_info` path works. Marker persistence in RAM remains unknown; the `oem mem`
implementation or its address mapping is suspect, and there are no blind retries.

Current `boot_a` holds the fastboot-reset marker image; `boot_b` is untouched and A
is active. Two follow-up efforts are running: a full-kernel
`late_initcall_sync` fastboot-return milestone probe, and a read-only investigation
of the `oem mem` failure.

## Late-init fastboot return proven, 2026-11-15

A full-kernel milestone probe ran. The driver
`repos/LibreEcho-Linux/drivers/misc/libreecho_lateinit_fastboot.c` behind the
default-n `CONFIG_LIBREECHO_LATEINIT_FASTBOOT` (Kconfig and Makefile entries added)
logs a tag at `late_initcall_sync`, writes the marker `LIBREECHOLATEINIT!` to
physical `0x44400000` through `phys_to_virt`, then performs the exact proven fastboot
watchdog reset and loops. The defconfig in the repository is unchanged; the option is
set only in the out-of-tree build config.

Image: `artifacts/phase-04/boot-lidar-lateinit-fastboot-return.img`, SHA-256
`3deff1de654baf16ea8214a2913218e8fd3e700ed247c2b827d4f3d8ec8e9f52`; kernel
`c07213a51965e38c9549c70fe731c7e9ceeb51815496d0bdd3ff01ae705376ff`; DTB
`2abaea8b814543bb4b1a0f276d660c0eacf3006f4ca2a478d6ac01a3c081f862`. `make Image dtbs`
and `pack_boot --verify` passed, and `objdump` showed the exact watchdog sequence.
The owner approved the flash; `boot_a` flash and reboot returned OKAY. About 20
seconds after the reboot, `fastboot getvar product` returned `LIDAR`.

This proves the full kernel reached `late_initcall_sync` on this image: only that
driver sets the reset, so the return cannot come from anything else, and the proof
does not depend on pstore, MMC or `oem mem`. It does not show that the earlier
corrected forced-panic image reached late init, though the same base makes it likely.
Focus now shifts to the logging and storage path. Current `boot_a` holds this
late-init-return image; `boot_b` is untouched and A is active. The `oem mem` read
failure remains under investigation.

## pstore backend conflict and block-selected run, 2026-11-15

A backend conflict explains part of the missing pstore writes: `ramoops` registers at
`postcore_initcall` (`fs/pstore/ram.c:969`) and `pstore_blk` at `late_initcall`
(`fs/pstore/blk.c:348`), so the second `pstore_register` is rejected with `-EBUSY`
(`fs/pstore/platform.c:591-600`).

The image `artifacts/phase-04/boot-lidar-pstore-panic-block-selected.img`, SHA-256
`6689fa7cff10f5a71a3a8c0e7ace6f70b3283a1d7986afaca8c53c70ea7064bf`, forces the backend
with `pstore.backend=pstore_blk` and keeps the corrected GUID, `best_effort=y` and
64 KiB console/kmsg settings. Verify passed. The owner approved the flash; flash and
reboot returned OKAY.
`dumps/20261115-lidar-phase4/swdl-after-block-selected.bin`, SHA-256
`83ee47245398adee79bd9c0a8bc57b821e92aba10f5f9ade8a5d1fae4d8c4302`, is still all
zero. The conflict is real but not the sole blocker; the remaining MMC or
device-open path is suspected, not proven.

## oem mem investigation closed, 2026-11-15

The installed binary `cmd_mem` matches its source, and the info and dispatch paths
work. A safe one-byte read inside LK at `0x41E30000` also produced no output, and the
job was cancelled. Do not retry `oem mem`.

## Slot-valid USB serial console retest, 2026-11-15

The g_serial-only image is
`artifacts/phase-04/boot-lidar-usb-serial-console.img`, SHA-256
`9a768de09130d39090b247ec5680eefc9c290e51f66f0046476b12046b494fe4`. It uses the clean
defconfig plus `CONFIG_USB_G_SERIAL=y` and `CONFIG_U_SERIAL_CONSOLE=y`; the latter is
required for `ttyGS0` to serve as a printk console. No panic and no late reset. Pack
verify passed. The owner approved the flash; flash and reboot returned OKAY.

No CDC ACM device appeared 12 seconds or an extra 20 seconds after the reboot. The
host journal showed repeated preloader reconnects. This negative is now slot-A
controlled, so the earlier g_serial result stands re-examined. It does not identify
the exact failing subsystem; whether MUSB is at fault or a later crash occurs remains
unresolved.

## Kaeru peek milestone, 2026-11-15

A new Kaeru `cmd_peek` replaces `oem mem`: one aligned READ32, a static
`peek_value[9]` buffer, and `fastboot_publish`. Earlier variants hid the OKAY reply
and garbled a stack buffer; the static buffer fixed the output. The final installed
image is `expdb-lidar-kaeru-peek-static-0x40000.bin`, SHA-256
`72aaaa321f0c10c3d62906b8bb52351bf6f63a5c890cba5e9f46fb73d3534eae`; the approved
write and readback matched exactly and the tail stayed stock.

`fastboot oem peek 41E30000` followed by `fastboot getvar peek` returned `40080000`,
proving that LK reads the address and transports the result. Then an approved
`boot_a` flash of the late-init return image (`3deff1de...`) and reboot returned
`product LIDAR`, but `oem peek 44400000` disconnected the device. Aligned reads
inside LK work; DRAM reads fault. The likely reason is that the source-built LK image
lacks the reference kit's rammap-fixed change, and the binary mapping patch is being
analyzed.

This does not read ramoops content. Current `boot_a` holds the late-init return
image, `boot_b` is untouched and A is active, and the installed expdb image is the
static peek `72aaaa...`.

## Mapping analysis result, 2026-11-15

The earlier rammap hypothesis is wrong. The reference kit's rammap-fixed change uses
a different stock LK, but the two region lists are content-identical. Both mappings
cover `bootimg 0x40080000..0x4407FFFF` and `download 0x44FFF000..0x4DFFFFFF`, which
makes `0x44400000` and `0x44410000` holes. There is no reference MMU extension to
port, and the DRAM-read fault needs another explanation.

## Mapped-pstore kernel, 2026-11-15

A new kernel relocates the pstore memory to mapped addresses. Image:
`artifacts/phase-04/boot-lidar-lateinit-fastboot-return-mapped-pstore.img`, SHA-256
`24c2c7ce564fcf705591f35931c770fb412d53f0925148e0fd45cce1b622dd72`; kernel
`a5ced1e63b86967e1237ea540e90f9c94ca58974b4e067d9ac16d7c70cb351be`; DTB
`64a54d4806a3a3c2cc4ea3c657129daf1d1dde6f734a69c70e204ba716d68ce6`. Pack verify
passed. The DTS and driver use: driver marker `0x45000000`; ramoops
`0x45010000`, size `0xe0000`; records `0xc0000`; console `0x10000`; pmsg
`0x10000`; console address `0x450D0000`. The configuration is the clean late-reset
one, with the stock command line and ramdisk.

A new Kaeru LK image added a bounded `fetch:` handler backed by `mem_region_find`,
`oem peek`, and `oem fetch-enable`. The enable command publishes `max-fetch-size`
and `partition-size:ramoops` through stock LK's published-variable table; Kaeru's
duplicate `getvar:` wrapper is not the handler serving the host. The image
`expdb-lidar-kaeru-peek-fetch-enable-v2-0x40000.bin` (sha256 `0199258e...`) was
written and read back exactly. `fastboot fetch ramoops` then transferred the full
high-window region successfully. The capture, `ramoops-high.bin` (sha256
`79a4c415...`), contained repeating `6eUl` words and no marker, `PSIG`, or kernel
text; the high download window is overwritten by LK and is not a valid pstore
location.

## Fastboot fetch capture of the bootimg-window ramoops, 2026-11-15

The coordinated build relocated the probe into the mapped boot-image window. The
first layout used marker `0x44000000` and ramoops `0x44010000`. It was rejected
before any flash: the stock ramdisk loads at `0x44000000`, so the overlap was
unsafe, and that image was deleted.

The final layout uses marker `0x43800000` and ramoops `0x43810000`, size `0x60000`
(records `0x40000`, console `0x10000`, pmsg `0x10000`). It clears the stock kernel,
ramdisk, ATF and reservation regions. Final artifacts:

| Artifact | SHA-256 |
| --- | --- |
| `artifacts/phase-04/boot-lidar-lateinit-fastboot-return-mapped-pstore-bootimg.img` | `9c837a8d62dcc18b396267a3dbdc6fe5d6717ad8979e8ab0a77b13eaf9d3d57a` |
| kernel `Image` | `208ce3ecd0a8a2aa11f367c1722ec7ec842f79a48aaff5cf6bdd3f52f72a0b15` |
| DTB `libreecho-lidar.dtb` | `7a3d521c6e841c29dd9ace6c5c4794a9a728b990d397b4f8781e124b27e30cd9` |
| `artifacts/phase-04/expdb-lidar-kaeru-peek-fetch-438-0x40000.bin` | `b9d8afa314f360165256262f17fb1ca45ca10a5cf0f8cd528c3a43013f4d2ed7` |

The image passed pack verify. The owner approved the writes; `boot_a` and expdb
were written and read back exactly, with the expdb stock tail unchanged. The fetch
sequence on the device:

```sh
fastboot oem fetch-enable
# optional confirmation
fastboot getvar max-fetch-size
fastboot getvar partition-size:ramoops
fastboot fetch ramoops dumps/20261115-lidar-phase4/ramoops-438.bin
```

`fastboot fetch ramoops` transferred `0x60000` bytes and returned OKAY. The capture
`dumps/20261115-lidar-phase4/ramoops-438.bin` has SHA-256
`331dd1aea1592db13e3cfab7f8ba34e8bf63f2a7e510664c2dd6a8ddca80cbc7`. The console
zone at offset `0x40000` uses a 12-byte `DBGC` header; the length field at `+8`
reads `0x1ca5`. The extracted log
`dumps/20261115-lidar-phase4/kernel-console-438.log` (SHA-256
`2d7396a93e1ce4f72e37db434d9a35dd8588ae95ad0548d1dbc6bbc6df722430`, 116 lines) is a
full kernel console dump. It proves two milestones:

- `ramoops: using 0x60000@0x43810000` and `pstore: Registered ramoops as persistent
  store backend`: the ramoops backend registered at the planned address and size.
- `[LIBREECHO-LATEINIT-FASTBOOT] late_initcall_sync reached`: the kernel reached
  late init and the driver reset into fastboot, which served the fetch.

The log also shows the current failure set. Regmap lookups fail with `-ENOTSUPP`
for `/soc/topckgen@10000000`, `/soc/syscon@15000000`, `/soc/syscon@16000000` and
`/soc/mmsys@14000000`. Pinctrl `1000b000`, the power controller and
`clk-mt8167-mm` fail with `-EPROBE_DEFER` (524). `mt6577-uart` `11005000`,
`mtk_rng` `1020c000` and `musb-mtk` `11100000` fail with `-ENOENT` (missing
clocks). Every failure points at the same clock/regmap thread, which is the next
root-cause target. No RAM marker survived the reset, which matches earlier warm-RAM
observations.

## Session end state (updated 2026-11-15)

Current device state: `boot_a` holds the final bootimg-window image
(`9c837a8d...`), expdb holds the final fetch-438 image (`b9d8afa3...`), `boot_b`
is untouched, and A is active. The Phase 4 hardware gate remains open: capture now
works end to end, but the kernel's clock/regmap failures are unresolved and Phase 4
is not complete.

## Syscon stall bisect, 2026-11-15

The clock/regmap failure set has an identified root cause: the ARM64 defconfig
(`repos/LibreEcho-Linux/arch/arm64/configs/mt8167_arm64_defconfig`) did not set
`CONFIG_MFD_SYSCON`. Without it, `syscon_regmap_lookup_by_phandle` compiles to
stubs that return `-ENOTSUPP`, which matches the console log exactly. The defconfig
now sets `CONFIG_MFD_SYSCON=y`, which selects `CONFIG_REGMAP_MMIO`. The file is
changed; no claim follows that the fix works on hardware.

Three images followed, each flashed to `boot_a` under approval with a bounded
fastboot check (20 seconds, then 15 seconds more) after the reboot.

1. First syscon image
   (`artifacts/phase-04/boot-lidar-syscon-lateinit-fastboot-return.img`, sha256
   `b154e4c76a060941017d57d3e5edb7a0f49600301876d7ff6e4df4005d65ad6f`):
   regenerating the defconfig accidentally dropped
   `CONFIG_LIBREECHO_LATEINIT_FASTBOOT`, so no fastboot return was possible. Its
   no-fastboot result is not kernel-stall evidence and must not be used as such.
   The capture `dumps/20261115-lidar-phase4/ramoops-syscon.bin` exists from that
   attempt. The later corrected early-marker image, sha256 `277334ae...`, is the
   hardware-relevant reference. BROM recovery and the `fastboot fetch` capture
   worked.

2. Corrected early-marker image
   (`artifacts/phase-04/boot-lidar-syscon-early-marker.img`, sha256
   `277334ae84da5dd2690e7e40ce39d75e55609897bf0477888a8c4081cbc0d3fe`), flashed to
   `boot_a`: the bounded fastboot check failed. BROM recovery and fetch worked.
   The capture `dumps/20261115-lidar-phase4/ramoops-syscon-early.bin` (sha256
   `495148ea3481cd70f494d5c56daf6399333e236e43189b258468513dade86b13`) has no
   `DBGC` console record, no Linux text and no `PSIG`. The standalone marker at
   `0x43800000` was unreliable: the capture shows that location overwritten.

3. Pmsg markers image
   (`artifacts/phase-04/boot-lidar-syscon-pmsg-markers.img`, sha256
   `9e44fd8813098d1467d7ae3393621fd4918076e83a2c616de2ea5f904da707ea`), which
   writes pmsg marker strings from early boot: the bounded fastboot check also
   failed. BROM recovery and fetch worked. The capture
   `dumps/20261115-lidar-phase4/ramoops-syscon-pmsg.bin` (sha256
   `aa46d83bc9a88a6fce25292a68668bca376ca7d3a56dbd3a4bba9ea36b89b88f`) has no
   `DBGC` record, no Linux text, no `PSIG`, and neither the early nor the late
   marker strings. On the earlier fetch-438 config, the identical capture path
   carried a full console log and the late-init tag, so this comparison supports a
   stall before `early_initcall`. It does not prove the syscon change fixed
   anything.

Next test, built but not yet run: `start_kernel` probes in
`repos/LibreEcho-Linux/init/main.c`, under the existing
`CONFIG_LIBREECHO_LATEINIT_FASTBOOT` gate (grep `LIBREECHO-PROBE` to remove). The
probes write to the pmsg zone at physical `0x43860000` with a 4 KiB memblock
reservation taken right after `setup_arch()`; memblock is still the allocator at
that point, so the reservation keeps the page out of the buddy allocator. Marker
offsets: `0x200` after `setup_arch`, `0x300` before `time_init`, `0x400` after
`time_init`. Image `artifacts/phase-04/boot-lidar-syscon-start-kernel-probes.img`
(sha256 `99606a1b063d05b0b0cbdda9e9e37f5f648e1675a79f7e875496670bb5b544e5`). No
hardware result exists for this image. The Phase 4 hardware gate remains open, and
Phase 4 is not complete.

## Probe results and pause, 2026-11-15

The pending `start_kernel` probe image above is superseded by the runs below. The
C probes themselves are validated; the question is why the syscon kernel never
reaches them.

1. Cache-flushed no-syscon control (sha256 `7c6c0fc1...`), flashed with the Action
   button released: returned to fastboot. Its `raw` capture (sha256
   `4106ef91...`) contains the `PROBE-SETUP-ARCH!` marker, the before/after
   `time_init` markers, and the late marker. The C probe path works end to end on
   a config without `CONFIG_MFD_SYSCON`.

2. Syscon-flushed image (dd1393d7) and paging image (1a2d345e, paging marker at
   pmsg offset `0x50500`): both failed the bounded fastboot check, and both
   captures had no markers.

3. Syscon map-mem image (cd0da53e): failed the bounded check with the Action
   button released. Its capture (7507345b) has no map-mem, paging or later
   markers.

4. To remove doubt about the pmsg path, a direct ARM64 store probe was added to
   `primary_entry` in `head.S` at offset `0x50700`, running with the MMU off. The
   large syscon image with that entry probe (07521890) failed, and its capture
   (302df5d6) has no entry marker. The matching no-syscon entry control
   (f7c4d33d) returned to fastboot with the Action button released, and its
   capture (624dad06) carries every marker: `ENTRY`, `MAP-MEM`, `PAGING`,
   `SETUP`, before/after `time_init`, the late marker, plus a full `DBGC` Linux
   console log. The entry probe is validated, and the large syscon kernel never
   reaches `primary_entry`.

5. Image size was tested as a cause. The first small-syscon image (ff36091d)
   returned to fastboot, but the owner confirmed the Action button was held
   throughout that run, so the return is invalid as kernel evidence; a corrected
   retest with the Action button released failed. A small-syscon image with the
   entry probe and MUSB disabled (7f6a89ca) also failed with the Action button
   released; its capture (2520fe85) has no entry marker. Shrink alone does not
   explain the failure, and no size limit is proven.

6. Boot-image headers extracted from the flashed images: the large working
   no-syscon image and the large failing syscon image both decompress to length
   8282624 with `image_size` `0x850000` and have identical first 64 bytes; the
   small syscon image decompresses to length 8217088 with `image_size`
   `0x840000`.

Hardware tests are paused. The next step is primary-source LK load and handover
research in `experiments/phase-04/lk-kernel-handover-research.md`; all further
work is source-backed, not more blind probes. The Phase 4 hardware gate remains
open, and no claim is made that the syscon change works.

## LK replay and dual-address probe prep, 2026-11-15

The LK handover research in
`experiments/phase-04/lk-kernel-handover-research.md` closes two hypotheses
with source-backed replay of the load path. H1 gzip truncation is refuted: all
five replayed decompressions reach `Z_STREAM_END`. H2 DTB differences are
refuted: the working and failing boot images contain 19-blob DTB collections
that are byte-identical at 1018698 bytes. Simple decompressed size and
`image_size` cannot explain the large working and failing pair, since both
large images decompress to 8282624 with `image_size` `0x850000`.

A reserved-memory audit across the DTB blobs shows that only blob4 declares
`ramoops@43810000`, and the observed kernel selected blob4. Every blob declares
the common `minirdump@444f0000` region of size `0x10000`; that region was
chosen for a second entry marker at `0x444f0800`.

Next experiments, in order:

1. Active-slot plus `boot_a` byte-hash verification, to prove the flashed
   image is the image that runs.
2. Dual-address `primary_entry` marker probe, writing both `0x43860700` and
   `0x444f0800`.
3. Fetch of both regions from the capture.

Prepared artifacts, host-verified only, no hardware run:

- `artifacts/phase-04/boot-lidar-syscon-dual-entry-probe.img`, sha256
  `af8bc486cce08d6bb4847d5a30edbc596db17458cd020a10a3dbc7da5a301b53`.
- `artifacts/phase-04/expdb-lidar-kaeru-peek-fetch-438-444f-0x40000.bin`,
  sha256
  `3f215a64edcd0e47e9e47e62494cae8e563b666f1127b7f351e1eb82f4418940`. This
  image publishes the minirdump fetch. The prior installed `438` image
  stays untouched on the device.

Build, disassembly, packing, and `check_payload` all pass.

Risk: `0x444f0000` lies outside the documented LK mappings, so the minirdump
fetch may fault or disconnect the DA session. The MMU-off store in
`primary_entry` is unaffected by that risk. Device writes require owner
approval, and a readback mismatch aborts before any write. Phase 4 remains
open, and syscon is not validated.

## Dual-address run and fetch correction, 2026-11-15

The pre-write readback of `boot_a` was byte-identical to the expected small
syscon entry image (sha256 `7f6a89ca...`), refuting the wrong-image explanation
for that failing test. The LK image returned an empty `current-slot` value, so
the partition byte comparison is the evidence used.

With owner approval, the dual-probe image `af8bc486...` and first dual-fetch
image `3f215a64...` were flashed. The dual-probe boot did not return to
fastboot with Action released. BROM recovery fetched
`ramoops-syscon-dual-entry.bin` (sha256 `8d1de73b...`); it has no entry or
later markers, no `DBGC`, and no Linux console text.

The first dual-fetch image installed byte-exactly but returned an empty
`partition-size:minirdump`. The cause was in `cmd_fetch_enable`: it published
only the ramoops size. `repos/kaeru/lib/fastboot/cmd_fetch.c` now publishes
`partition-size:minirdump` using the same existing mechanism. The corrected
image passes `check_payload`; its sha256 is
`c6b7bcde620529eb77df5f5e6e1c03fd9ce14d356833afc0ea92b7f39184ab09`.
It was flashed under the same approval for the diagnostic expdb image. The
second region has not been read yet because the Lidar subsequently disappeared
from USB; normal boot is not expected to return to fastboot, and BROM recovery
is still required. No conclusion about the minirdump marker is available.

A no-syscon dual-marker control is prepared for a later `fastboot boot` test,
which will not replace the syscon image in `boot_a`:
`artifacts/phase-04/boot-lidar-no-syscon-dual-entry-control.img`, sha256
`86dcfd7dc376e76cd2aa62402d9d4008ba0ded17fd7d2550bd31da0e76b085b8`.
`pack_boot.py --verify` passed. The build configuration was restored to
`MFD_SYSCON=y`, `REGMAP_MMIO=y`, and `LIBREECHO_LATEINIT_FASTBOOT=y` after
packing the control. Phase 4 remains open.

## Entry-probe relocation and host-only build, 2026-11-15

The minirdump fetch attempt confirmed the risk recorded earlier: the
fastboot fetch of the `0x444f0000` minirdump region disconnected, because
that region lies outside LK's mappings. No minirdump data was captured.

A BROM `mtk.py peek` of `0x444f0800` and `0x10` succeeded after one
transient handshake retry, and the first peek returned 16 zero bytes
(sha256 `374708fff...`). This result is inconclusive: earlier warm-BROM RAM
reads in Phase 4 already failed to preserve a known valid marker, so a zero
read here does not show that no entry marker was written. No conclusion is
drawn from it.

The custom minirdump diagnostic is replaced. The Lidar DTS now declares a
`no-map` reserved-memory region `entry-probe@43ff0000` of size `0x10000`,
with the entry marker at `0x43ff0800`. The region sits inside LK's bootimg
mapping (`0x40080000..0x4407ffff`) and ends exactly at the stock ramdisk
load address `0x44000000`, so LK's fastboot can fetch it. The Kaeru LK image
now publishes `entryprobe` instead of `minirdump`; the ramoops marker at
`0x43860700` is unchanged.

Host-verified artifacts, no hardware run:

| Artifact | sha256 |
| --- | --- |
| `boot-lidar-syscon-mapped-dual-entry-probe.img` | `1119e33f09da4d4a6dc2271d8a35386b82c1088877a8e8cfbcfb1f19a60e628c` |
| `boot-lidar-no-syscon-mapped-dual-entry-control.img` | `017540d527eeb09955dc22b57ba41c44efc9869fc7176796859388bc447a5810` |
| `expdb-lidar-kaeru-peek-fetch-438-43ff-0x40000.bin` | `1b3cd36da5c96479cc81ca1603c9d94bd1d1af1518265f2b5143883200d8fad7` |

For all three, `pack_boot.py --verify` passed on both images, both images
carry the identical DTB (sha256 `99152dbc...`), the disassembly shows the
marker store in both kernels before `preserve_boot_args`, and
`check_payload` passed 46 of 46 checks.

Next run order: flash the Kaeru LK image, then a transient `fastboot boot` of the
no-syscon control (`boot_a` stays unchanged), and fetch `entryprobe` plus
ramoops to validate the channel. Only if that capture validates does the
syscon mapped image get flashed and tested. The attempt waited 300 seconds
for a fastboot device; none appeared, so no write and no boot happened.
Phase 4 remains open, syscon is unvalidated, and device reconnection is the
blocker.

## Mapped-entry controlled runs, 2026-11-15

The Kaeru LK image was flashed. LK rejected the planned transient
`fastboot boot` as an unknown command, so the no-syscon mapped control was
flashed to `boot_a`; `boot_b` stayed untouched. Only after its captures
validated the channel was the syscon mapped image flashed and tested.

1. No-syscon mapped control (`boot-lidar-no-syscon-mapped-dual-entry-control.img`,
   sha256 `017540d5...`) returned to fastboot with the Action button released.
   Its captures validate the whole fetch channel: the `entryprobe` region
   carries `PROBE-ENTRY` at `entryprobe+800`, the ramoops capture carries the
   marker at offset `0x50700`, and the DBGC zone holds a full Linux console
   log. Capture hashes: entryprobe `6251553d...`, ramoops `f7a66a24...`.

2. Syscon mapped image (`boot-lidar-syscon-mapped-dual-entry-probe.img`,
   sha256 `1119e33f...`) failed the bounded fastboot check with the Action
   button released. Both markers are absent: the entryprobe capture
   (`2fdfef35...`) and the ramoops capture (`3fa69359...`) contain neither
   `PROBE-ENTRY` nor the ramoops marker. A post-run `boot_a` readback is
   byte-exact against the flashed image hash, so the failing image is the
   image that ran.

3. Size-padding control (sha256 `61a0e6b8...`, no syscon, Action button
   released, returned to fastboot): it preserved the working kernel, gzip,
   DTB and ramdisk bytes but carried the syscon image's exact header
   `kernel_size` `0x4268e7` and `ramdisk_offset` `0x427800`. This excludes
   boot-image size and layout as the cause.

4. Gzip variants of the syscon kernel. The gzip6 image (sha256 `f23822e3...`)
   decompresses to the same syscon ARM64 `Image` (sha256 `fa90a628...`) and
   failed the bounded fastboot check; both markers are absent (entryprobe
   `85e9c3c6...`, ramoops `b43e8968...`). The gzip0 stored-deflate image
   (sha256 `17b16b93...`) decompresses to the same `Image` and also failed to
   return to fastboot per the owner's report; no marker fetch was run for it,
   so only a no-late-return claim is made for gzip0.

Together these runs exclude compression and boot-image layout. The conclusion
that the failure is tightly isolated to the syscon build's kernel binary
before `primary_entry` is superseded by the entry-WDT results below and by
section 11.8 of `lk-kernel-handover-research.md`: the absent RAM markers were
cleared along the failing manual BROM/DA recovery path, so they were never
proof that `primary_entry` did not run. Hardware flashing is paused pending
analysis of the actual UFBL/LK binary in
`experiments/phase-04/lk-kernel-handover-research.md`. The Phase 4 hardware
gate remains open and syscon runtime is still unvalidated.

## Entry-WDT delayed-reset runs, 2026-11-15

Two matched images, each carrying the identical `PROBE-ENTRY` marker stores at
`primary_entry` (before `preserve_boot_args`) followed by a 5-second busy-wait
on the generic timer and a TOPRGU reset (`0x10007000`: `0x1971` to `+0x08`,
`0x22000014` to `+0x00`, `dsb sy`, `0x1209` to `+0x14`, then spin), per the
design in section 11.8 of `lk-kernel-handover-research.md`. The reset is the
reachability signal, so a later BROM/DA clear of the RAM markers cannot
affect the conclusion.

| Artifact | sha256 |
| --- | --- |
| `boot-lidar-no-syscon-entry-wdt.img` | `969a06f7358f51110cbd73b6b7d52cc0031bacddbd69cc19b6ef578192d6873f` |
| `boot-lidar-syscon-entry-wdt.img` | `2959155a566141bac917e4afd676751ed5cd06773c21826de1c534f0e04a1e5e` |

Procedure and results:

1. No-syscon entry-WDT control (`969a06f7...`), flashed to `boot_a` under
   approval: returned to fastboot after the owner released the Action button at
   initial boot, then held it again roughly one second later. The shell's
   `SECONDS` counter was bogus in that session, so no control-run timing
   figure is claimed; only the on-device return itself is evidence.
2. Syscon entry-WDT image (`2959155a...`), flashed with the same procedure:
   returned to fastboot, measured at about 8 seconds after the reboot.

Both runs used the same procedure and the same marker + 5-second
`primary_entry` TOPRGU reset. Because the syscon image's delayed reset fired
after the measured delay, `primary_entry` executed in the syscon build. The
earlier result that syscon runs left no RAM markers stands as an observation,
but the markers were cleared along the failing manual BROM/DA recovery path
(recorded earlier in these notes: the BROM/DA path overwrote RAM in the
cold-entry reads), so their absence was never proof that `primary_entry` was
not reached. Section 11.8 of `lk-kernel-handover-research.md` anticipates
exactly this correction.

The device-binary audit is unchanged by these runs: the shipped UFBL accepts
any stream that ends in `Z_STREAM_END`, never compares the decompressed
length, and never reads `kernel_addr` content, `image_size`, `text_offset` or
the PE/entry fields (section 11.3-11.4). The fault is therefore after
`primary_entry`, and compression, boot-image layout and the LK handover
itself are all excluded as causes.

Current device state at the end of these runs: `boot_a` holds the syscon
entry-WDT image (`2959155a...`), the installed expdb image remains the
mapped peek/fetch image (`expdb-lidar-kaeru-peek-fetch-438-43ff-0x40000.bin`,
sha256 `1b3cd36da5c96479cc81ca1603c9d94bd1d1af1518265f2b5143883200d8fad7`),
and the device is back in fastboot. The Phase 4 hardware gate stays open, and
syscon runtime is validated only as far as `primary_entry` plus the delayed
reset; the post-entry stall remains unlocated.

Next step: a delayed TOPRGU reset at the top of `rest_init`, before
`rcu_scheduler_starting` / `user_mode_thread`, to separate early setup
(from `primary_entry` through `rest_init`) from driver and late init. The
existing `CONFIG_LIBREECHO_ENTRY_WDT_RESET` gate at `primary_entry` is
proven in both builds; the `rest_init` probe reuses the same
delayed-reset mechanism under a separate config, and preserves default
behavior with all diagnostic configs off.

## Delayed-WDT initcall bisect, 2026-11-15 (consolidated)

The `rest_init` and initcall probes ran as planned. All results below use
the proven delayed-TOPRGU-reset mechanism: each probe waits five seconds
at its site and then resets into Kaeru fastboot, so the fastboot return
after the delay is the reachability signal and does not depend on RAM
surviving the reset. The probes live in
`repos/LibreEcho-Linux/init/main.c` and `drivers/misc/`, gated by:

- `CONFIG_LIBREECHO_REST_INIT_WDT_RESET` (default n): reset at the top of
  `rest_init`, before `rcu_scheduler_starting` and `user_mode_thread`.
- `CONFIG_LIBREECHO_INITCALL_WDT_RESET` (default -1, disabled): reset
  inside `do_initcalls()` after the selected level finishes; -2 fires
  before level 0, 0..7 fire after pure, core, postcore, arch, subsys,
  fs, device and late.
- `CONFIG_LIBREECHO_INITCALL_ITEM_WDT_RESET` (default -1, disabled):
  reset inside `do_initcall_level()` before the selected zero-based
  item of the late level (level 7). Reaching the reset proves every
  earlier late initcall returned.

All diagnostic configs are off by default and were off in every
production-relevant build; the repository defconfig sets none of them.

Results (image short hash, time from reboot to a fastboot device):

| Probe | Control (no syscon) | Syscon (`CONFIG_MFD_SYSCON=y`) |
| --- | --- | --- |
| `rest_init` | `8a56b4c8`, 22 s | `3059546b`, 27 s |
| before level 0 (`-2`) | `24de29ab`, 9 s | `faa346f6`, 8 s |
| after arch (level 3) | `369c6cf9`, 27 s | `e7362313`, 9 s |
| after fs (level 5) | not run | `407899dd`, 9 s |
| after device (level 6) | not run | `9b45b492`, 9 s |
| after late (level 7) | not run | `517cf844`, 9 s |

The syscon `rest_init` return proves `rest_init` is reached in the
syscon build. The before-level-0 returns in both builds prove
`do_initcalls()` starts. The after-arch, after-fs, after-device and
after-late returns prove every ordinary initcall level 0 through 7
completes in the syscon build.

Late-level item probes (`CONFIG_LIBREECHO_INITCALL_ITEM_WDT_RESET`,
syscon build, all returning to fastboot):

- Item 14: the first run timed out and is invalid; the owner reported a
  possible Action-button mistake during that attempt. After BROM
  recovery with `enter_fastboot.py`, the retry returned to fastboot
  in 9 s.
- Item 21 (`9ff4390b`), 9 s; item 25 (`eb48c29d`), 9 s; item 27
  (`6877be3b`), 9 s; item 28 (`026e9fb1`), 8 s.

Because each item probe fires before its item runs, the item 28 return
proves late items 0 through 27 returned. The after-late-level return
(`517cf844`) proves the whole late level, including all 29 ordinary
items and `of_platform_sync_state`, completes when the final
`libreecho_lateinit_fastboot` diagnostic registration is suppressed
(the item and level-7 probes suppress that registration).

Conclusion, superseding the earlier wording that the fault lies after
`primary_entry` or in a late level: the original no-return behavior is
confined to the LibreEcho final marker/reset diagnostic itself or to
work after the ordinary initcalls finish. The ordinary kernel up to and
including every initcall level runs in the syscon build. No claim
follows that the product syscon change is at fault.

Current device state: `boot_a` holds the after-late-level syscon image
(`517cf844`), expdb holds the mapped peek/fetch image
(`expdb-lidar-kaeru-peek-fetch-438-43ff-0x40000.bin`, sha256
`1b3cd36da5c96479cc81ca1603c9d94bd1d1af1518265f2b5143883200d8fad7`),
and the device is in fastboot. Next test: a clean syscon build with
every diagnostic config off (all four probe configs at their defaults)
and normal MUSB, booting toward Android with the Action button
released.

## Clean-build exec-boundary and Android-gate runs, 2026-11-15

The clean syscon build ran. It uses a fresh defconfig with
`CONFIG_MFD_SYSCON=y`, normal MUSB, every diagnostic config at its
default (off) and the stock ramdisk. Image sha256
`3da28ee219dc27d66c5d459bc0d8360808d9cfa12e8affcf2ed734070308fc2c`.
It was flashed to `boot_a` under approval with the Action button
released. `adb wait-for-device` timed out at 120 seconds with no USB
interface, so the clean build still produces no userspace evidence on
its own.

A new pre-userspace probe then bounded the failure from the other end.
Image sha256 `e490d27bd29cef18ca45c10c147a7b4dc077b111b45e0ac1279c648763ae6843`
resets (proven TOPRGU delayed reset) after `do_sysctl_args()` and
before `run_init_process()`. The first attempt was invalid; after BROM
recovery and a retry, the device returned to fastboot 9 seconds after
the reboot. Because the reset sits after `do_sysctl_args()`, the return
proves the full kernel init path, including async probing, the rootfs
mount and `free_initmem`, reaches the exec boundary where `kernel_init`
calls `run_init_process()`. The earlier initcall bisect is thereby
extended through the end of `kernel_init_freeable()`.

A clean diagnostic-adb image followed. Image sha256
`d8fa7c7756f2be3980e49c45c8b753ee6bbf5bcd696e46e2b7919e2dde24488f`
carries the same clean kernel (sha256 `2e58e739...`) and modifies only
the ramdisk entries `init.rc` and `default.prop`; pack verify passed.
A first pack command failed with `adb: not found` before any flash;
the retry used the full adb path, so that failure is host tooling and
is not a device result. The image was flashed under approval with the
Action button released. `adb wait-for-device` again timed out at 120
seconds with no USB interface. So the exec-boundary kernel plus a
ConfigFS ADB ramdisk still shows no ADB device.

The exec-success probe then ran under an owner-approved retry. Image
sha256 `cf22ae65fb93da3fb1637a738c88d98a51f2a2a937a03a741e4755ffb3ad8efb`
resets into fastboot only if `run_init_process('/init')` returns 0; it
carries the diagnostic ramdisk, and pack verify passed. Its first
hardware attempt was invalid because the owner missed the Action-button
state. The approved retry flashed the same image with the Action button
released; the device returned to fastboot 9 seconds after the reboot.
The reset therefore fired, `run_init_process('/init')` returned 0, and
the ARM32 `/init` exec is proven. The remaining failure is in Android
init or ADB after the exec.

A fastboot ramoops fetch after the exec success found no `DBGC` record
at offset `0x40000` (random pattern), so no kernel console inference
follows from that capture.

Current device state: `boot_a` holds the exec-success image
(`cf22ae65...`); expdb holds the mapped peek/fetch image (sha256
`1b3cd36d...`); `boot_b` is untouched; the device is in fastboot. The
Android full-boot gate remains open. Next step, build only: a clean
syscon kernel with `CONFIG_USB_G_SERIAL=y` and no diagnostic configs,
as a kernel-only test that separates kernel UDC behavior from Android
`adbd`. No hardware action is planned beyond owner approval.

## Syscon g_serial run, 2026-11-15

The syscon g_serial kernel-only image (sha256
`98f5369ee48cad3066f253bf07b9f42d9fce625de49ec1c0d1ef17fa5ec88e12`,
stock ramdisk, pack verify OK) was flashed with the Action button
released. `/dev/ttyACM0` appeared on the host, but `lsusb` reports the
device as `0e8d:2000` MediaTek preloader, not `0525:a4a7` Linux
g_serial, so no USB success follows and the device returned to
preloader. BROM recovery restored fastboot. The capture
`ramoops-syscon-serial.bin` contains no `DBGC`, `LIBREECHO` or `musb`
text anywhere, so no kernel log inference follows from it. The DTS
confirms `dr_mode = "peripheral"`.

Current device state: `boot_a` holds the g_serial image
(`98f5369...`), and the device is in fastboot. Next step: a bounded
g_serial image plus a pre-userspace WDT probe, with a udev monitor on
the host to record the enumeration sequence.

## Bounded g_serial pre-userspace WDT run, 2026-11-15

Image sha256
`4ab15d710f9e94f90ab1e9c99e07d4c66ba5862d19d5ef9c606e4c4deac56ba3`
carries `CONFIG_USB_G_SERIAL=y` plus the existing pre-exec userspace
WDT probe. It returned to fastboot 9 seconds after the reboot in both
of two runs. The reset therefore fired after the bounded pre-userspace
point in both runs, proving device init including `gserial_init`
completed.

The first run's udev monitor was invalid: it recorded no events even
for a known fastboot device. The second run used a direct PyUSB poll.
It saw an empty list at first, then only `(0e8d, 2000)` at 11.703 s,
an empty list again at 14.280 s, and never `0525:a4a7`. The kernel
therefore never enumerates the g_serial gadget despite completed
initcalls; no specific MUSB cause is inferred yet.

Correction, 2026-11-15: `drivers/usb/gadget/legacy/serial.c` lines
35-36 define `0525:a4a6`, not `a4a7`. The poll above watched the wrong
product ID, so the no-`a4a7` observations here are invalid as g_serial
negatives. The status proofs (device init including `gserial_init`
completed) remain valid.

Current device state: `boot_a` holds the bounded g_serial image
(`4ab15d...`), and the device is in fastboot. Next step: a
`MusbStatusProbe` that resets at the same bounded pre-userspace marker
with three timings: 5 s after `mtk_musb_probe` success, 10 s when the
probe was entered but not successful, and 15 s when it was never
entered.

## MUSB glue status probe, 2026-11-15

Image sha256
`a60645d66032731edd412d07c909bd4b33877047caaa0f6c2c1161f626d60e77`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and `mtk_musb_probe` reached status 2 (probe success).

Qualification: glue-layer success covers only
`platform_device_register_full()` of the `musb-hdrc` child. It does
not show that the generic `musb_init_controller()` or the gadget side
succeeded.

Current device state: `boot_a` holds the glue status image
(`a60645d...`), and the device is in fastboot. Next step: a core
status probe that resets at `musb_init_controller()`'s final return 0
with the same 5/10/15-second delays.

## MUSB core status probe, 2026-11-15

Image sha256
`0c75851f90021d9cebb8bc200ede623ed8f5c71165e164337ac9cd03e5cfba6c`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and the generic `musb_init_controller()` reached status 2: final
return 0 after `musb_gadget_setup()` and `is_initialized`.

The USB failure is therefore after core and gadget registration.

Current device state: `boot_a` holds the core status image
(`0c75851...`), and the device is in fastboot. Next step: a gadget
status probe mapping start entry to a 15-second delay, success to
10 seconds, pullup-on to 5 seconds, and never reaching any of them to
20 seconds.

## MUSB gadget status probe, 2026-11-15

Image sha256
`b834cbe106a48a2dc0348f265880cfde3c56939d25d082d01f39e3c3e88edc1e`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and the probe reached status 3: `musb_gadget_pullup(is_on=1)`.
The g_serial gadget started and requested D+ pullup.

Current device state: `boot_a` holds the gadget status image
(`b834cbe...`), and the device is in fastboot. Next step: an actual
`musb_pullup` write probe with a 9-second delay after the SOFTCONN
readback is set, 14 seconds when the write's readback is clear, and
19 seconds when no actual write happened before the fallback.

## MUSB actual pullup probe, 2026-11-15

Image sha256
`409dd4be6ffe8bff2415e1603acdfb5f7ba6e1af0148973772f674ab652486d8`
returned to fastboot 8 seconds after the reboot, so the 9-second
timing class fired: the actual `musb_pullup(is_on)` ran and the
`MUSB_POWER_SOFTCONN` readback was set. The controller D+ request is
confirmed.

Current device state: `boot_a` holds the actual pullup image
(`409dd4b...`), and the device is in fastboot. Next step: a DEVCTL
VBUS status probe with a 9-second delay when VBUS reads full,
14 seconds when it reads partial, 19 seconds when it reads zero, and
24 seconds when no actual pullup ran.

## DEVCTL VBUS probe, 2026-11-15

Image sha256
`655a0a8677e65fa87008346bf49ed1c7bb2a05673fc2700d21e8dabc07c675c2`
returned to fastboot 9 seconds after the reboot, so the actual pullup
ran with the DEVCTL VBUS field reading full (`0x18`).

Repeating the same image under a direct PyUSB poll still never saw
`0525:a4a7`; only `0e8d:2000` appeared at 10.341 s and disappeared at
13.020 s. SOFTCONN is set and VBUS reads full, but the host never
enumerates the gadget. The next target is PHY power, mode and D+
signaling. A `MusbPhyResearch` comparison of the vendor and upstream
MT8167 PHY setup against MT8163 recovery is running.

Correction, 2026-11-15: the poll watched the wrong product ID;
`drivers/usb/gadget/legacy/serial.c` lines 35-36 define `0525:a4a6`.
The no-`a4a7` observation here is invalid as a g_serial negative. The
status proof (DEVCTL VBUS full under the actual pullup) remains valid.

## PHY fix run, 2026-11-15

The `Mt8516PhyFix` image (sha256
`cf87e11a62d18db65c5cd72159be573be3cf2e233f040d0e7da1c585e52c7f48`)
was rerun with the correct `0525:a4a6` and fastboot `0bb4:0c01` IDs
under a PyUSB poll. Timeline: fastboot `0bb4` initial at 0.021 s, gone
at 10.421 s; preloader `0e8d` at 12.269 s, gone at 14.997 s; fastboot
again at 18.086 s. `0525:a4a6` never appeared. This is a valid
negative for the PHY fix only; it does not retroactively establish the
baseline no-serial result.

Current device state: `boot_a` holds the PHY fix image
(`cf87e11...`), and the device is in fastboot. Next step: a BDEVICE
probe on the PHY-fixed source.

## BDEVICE probe, 2026-11-15

Image sha256
`47fd33d77ca646e93756c5af8bff5c61a6414593c985b9eea324461bf9ac8426`
returned to fastboot 9 seconds after the reboot. BDEVICE is set to
peripheral mode at the actual pullup on the PHY-fixed source.

The host journal shows no electrical connect between the fastboot
disconnect and the preloader, so no descriptor exchange happened.

Remaining vendor versus mainline gaps in the analog setup:

- `usb20_phy.c` lines 343-398 set SQTH6; mainline sets 2.
- `VRT_SEL7` and `TERM_SEL7` are absent from mainline.
- The `DP100K` bit 18 set with bits 17:16 clear is absent from
  mainline.

`Mt8516PhyFix` is adding these mt8516-only analog settings and
rebuilding the bounded g_serial image. Current device state: `boot_a`
holds the BDEVICE image (`47fd33d...`), and the device is in fastboot.

## PHY research conclusion, 2026-11-15

The MT8163 glue and recovery must not be used for this target. The
MT8167/MT8516 DT uses one register region and 3 clocks with the
separate t-phy driver, while the MT8163 needs a second register region
and 4 clocks.

Source comparison of the device-mode VBUS session fix:

- Vendor `LibreEcho-Platform/drivers/misc/mediatek/usb20/mt8163/usb20_phy.c`
  lines 343-398 use the same V1 layout, wait 800 us, then write
  `0x6c = 0x2e` and `0x6d = 0x3e`, forcing IDDIG, AVALID, BVALID,
  VBUSVALID and SESSEND.
- Mainline `drivers/phy/mediatek/phy-mtk-tphy.c` lines 565-588 force
  only IDDIG.

A minimal `mt8516-tphy` pdata quirk implementing the full device force
is building in `Mt8516PhyFix`, as a bounded g_serial image plus the
pre-userspace WDT. The IDDIG pinmux stays a second possible fix only
if needed. No runtime fix claim is made yet.

## Stock-layout MUSB experiment and correction, 2026-11-15

The earlier PHY research conclusion compared only the inherited mainline DTS
with MT8163. Decompiling the stock Lidar PVT DTB disproved that board-level
premise: its `usb@11100000` has two 64 KiB regions at `0x11100000` and
`0x11110000`, four clocks named `usbpll`, `usbmcu`, `usb`, `icusb`, GPIO41
IDDIG pull-up, and `drvvbus-not-supported`. It has no `vusb` supply. U-Boot's
MT8516 DTS maps the four clock roles to `USB_PHY48M`, `USBIF`, `USB`, and
`USB_1P`, although its driver enables only the first three.

A bounded g_serial image tested the stock resource shape through a separate
MT8167 glue configuration with the existing MT8163-style PHY recovery and an
optional `vusb`. Image sha256 is
`5aba70f61d81c550ce4a682085f589caabca259a37f2c8165a933a40c7fe9dab`;
kernel is `52be2e918b228ad653d428b05ae456f3b528563e6e577cd4cf365adc41170f84`
and DTB is `ff04694bab3b9fd8a0dac5c41eb3a966ce258d75cbb2b918eaa751af48aab3ca`.
Build, compiled-DTB resource checks and pack verification passed.

The first reboot observer was invalid: host Python raised
`ModuleNotFoundError: No module named 'usb'` before monitoring. The flash and
reboot themselves succeeded. A second reboot of the same image used
`uv run --with pyusb` and watched the correct IDs. It saw fastboot `0bb4:0c01`
at 0.018 s, preloader `0e8d:2000` at 2.018 s, fastboot again at 7.853 s, and
never g_serial `0525:a4a6`. The stock-shaped recovery experiment is therefore
a valid negative, not a USB fix. Its two source-file changes were reverted, and
`make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 Image dtbs -j8` passed after
the revert.

The parallel primary-source survey is in
`experiments/phase-04/usb-enumeration-research.md`. It found no published report
matching probe-successful MediaTek MUSB with no host connect. A new U-Boot port
is not the next control: LK fastboot already enumerates on this exact board,
cable and host. The next comparison is LK's known-good fastboot USB/PHY
initialization against mainline.

Current device state: `boot_a` holds image `5aba70f6...`; the device returned
to fastboot. The source revert does not change the flashed image.

## Course change, 2026-11-17

The owner compared Phase 4 with the independent lidar-mainline project, which boots a
mainline kernel on this device. The full comparison is in
`lidar-mainline-comparison.md` in this directory. Decisions made from it:

- ADB is dropped as the Phase 4 verification route. The failure is below ADB: the host never
  sees a USB connect at all. The debug channel becomes a USB CDC ACM serial root shell
  (getty on ttyGS0), a USB NCM network link with SSH as a development-only service, and
  pstore/ramoops console readback after a warm reboot. Passwordless telnet is rejected.
- Phase 4 stays on Linux 6.1.178 in `repos/LibreEcho-Linux` on `feature/lidar-support`. A
  7.3 rebase is an evidence-gated later option.
- Nothing from the reference project is built, flashed, or run. Only facts and settings are
  adopted. Copying reference GPL-2.0 driver code (a Phase 6 question) needs an explicit
  owner decision.
- Adopted steps, in order: (a) restore upstream 6.1 USB code after saving our probe/PHY
  patches here, drop the `&usb0` compatible override, remove WDT probe hooks; (b) add
  `clk_ignore_unused` to the cmdline; (c) drop `CONFIG_MUSB_PIO_ONLY` and enable
  `USB_INVENTRA_DMA`, `USB_CONFIGFS_ACM`, `USB_CONFIGFS_NCM`, pstore/ramoops console and
  pmsg, and `PANIC_TIMEOUT=10` in the defconfig; (d) DT changes (memory top 0x7f9c0000,
  ramoops relocation, `pmu` disabled, `cpu-idle-states` deleted); (e) our own ARM32 test
  initramfs with a configfs acm+ncm gadget, getty on ttyGS0, and link-local usb0; (f)
  `pack_boot.py` guards (bootopt prefix, 0x80000 DTB cap, `amzn,lidar-*` root compatible);
  (g) separately approved flash steps with disconnect-first power cycles.
- The Phase 4 gate is now: root shell over USB CDC ACM (or SSH over USB NCM), `uname -a`,
  `/proc/cmdline`, `dmesg`, `/proc/cpuinfo`, and a pstore console readback after a warm
  reboot. See `PLAN.md`.
- UART correction: the earlier "3.3 V UART console" diagnostic was superseded. UART0 TX is
  test point TM58 at 1.8 V, 921600 8N1, output only; UART0 RX is on no known test point.

Current device state is unchanged by this decision: `boot_a` still holds image
`5aba70f6...`, and the device is last known in fastboot. No build, flash, or hardware action
ran for this change.

## Test initramfs, 2026-11-17

Our own ARM32 test initramfs exists now, built and packaged on the host only. Nothing was
flashed, booted, or run on the device.

Toolchain route: stock Arch clang, lld, and llvm-ar 23.1.5 (no ARM gcc, no sudo), musl 1.2.5
built from source for `armv7a-linux-musleabihf` with `--disable-shared --enable-static`, and
compiler-rt builtins built from the matching llvm-project 23.1.5 source release because the
Arch compiler-rt package ships x86 builtins only. Only `lib/builtins` was configured
(`COMPILER_RT_DEFAULT_TARGET_ONLY=ON`), producing `libclang_rt.builtins-armhf.a` for
`__aeabi_*` and the 64-bit integer helpers. Static links go through a small clang wrapper that
uses `-fuse-ld=lld -nostdlib` plus the musl crt objects, `libc.a`, `libm.a`, and the builtins,
so no GCC installation is needed. musl ships no Linux UAPI headers, so the wrapper adds
`-idirafter /usr/include` for `linux/*` and `asm/*` only; libc headers still resolve to the
musl sysroot.

Pinned sources (the build script aborts on any sha256 mismatch):

- musl 1.2.5, `https://musl.libc.org/releases/musl-1.2.5.tar.gz`,
  `a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4`
- llvm-project 23.1.5 source,
  `https://github.com/llvm/llvm-project/releases/download/llvmorg-23.1.5/llvm-project-23.1.5.src.tar.xz`,
  `fb50b1eac93ddeb3aa8dab4cfe324dff74f4a9c2bdee6160c9e36188f8d06a6e`
- BusyBox 1.37.0, `https://busybox.net/downloads/busybox-1.37.0.tar.bz2`,
  `3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4`

BusyBox is static, from the platform config with `CONFIG_STATIC=y`, `CONFIG_CTTYHACK=y`, and
`CONFIG_DEVMEM=y` added and `CONFIG_PIE` off. `llvm-readelf` reports ELF32 ARM, flags
`0x5000400` (EABI5, hard-float), and no interpreter. All 53 required applets are present; the
check reads the built `.config`, since the ARM binary cannot run on the x86 host.

Files: `experiments/phase-04/initramfs/` holds `build_initramfs.sh`, `init`,
`busybox-1.37.0.config`, and `initramfs.list`. Outputs are
`artifacts/phase-04/initramfs/lidar-test-initramfs.cpio.gz` and `MANIFEST.txt`.

Build command:

```
cd experiments/phase-04/initramfs && ./build_initramfs.sh
```

The work dir defaults to `/tmp/lidar-initramfs-build` and can be set with
`LIDAR_INITRAMFS_WORK`; large sources and build trees never go into the artifacts directory.

Archive: `lidar-test-initramfs.cpio.gz`, 682342 bytes,
sha256 `7b4a7c85313e772b95760288f43a8896d69b8141f09d9e9ae6ab0660b0605325`. Two consecutive
builds produced that same hash. The cpio is gzip `-n -9` over `gen_init_cpio -t 0` output from
the kernel tree's own `usr/gen_init_cpio.c`, with the staged files touched to epoch 0, so file,
directory, and node mtimes are all 0.

`/init` (a BusyBox ash script) stages, in order: mount proc, sysfs, devtmpfs, devpts, configfs,
and pstore, copying any existing `/sys/fs/pstore` records to `/pstore-prev`; build configfs
gadget `g1` (`1d6b:0104`, bcdUSB 0x0200, `acm.usb0` plus `ncm.usb0` linked into `c.1`,
MaxPower 250, serial from `/proc/device-tree/serial-number` with a fixed fallback), retrying up
to 30 s for a UDC and binding the first entry from `/sys/class/udc`; bring up `usb0`, keep IPv6
link-local autoconfiguration, and add `169.254.42.1/16`; spawn a respawned root shell with a
controlling tty on `/dev/ttyGS0` via `setsid cttyhack sh`, plus an optional shell on
`/dev/console`; then reap forever so PID 1 never exits. Each stage writes a marker to
`/dev/kmsg` and, when present, `/dev/pmsg0`.

Checks run on the host:

- `bsdtar -tvf` lists `/init` as mode 0755, `/bin/busybox` as a regular 0755 file,
  `/dev/console` as char 5,1 mode 0600, and `/dev/null` as char 1,3 mode 0666, all with mtime
  Jan 1 1970.
- `pack_boot.validate_ramdisk` accepts the archive (gzip, newc, executable `/init`).
- `llvm-readelf` and the applet config check inside `build_initramfs.sh` pass.
- The build script's two runs exited 0 with identical archive hashes.

Unverified: the BusyBox binary was never executed, because `qemu-arm` user-mode is not
installed; no boot, flash, or hardware test happened; the gadget, usb0, and shell stages are
untested on the device.


## Clean USB control image, 2026-11-17

Kernel from `repos/LibreEcho-Linux` branch `experiment/lidar-usb-upstream-glue`, commit
`a251a739`, built with `make O=/tmp/lidar-arm64-build ARCH=arm64 LLVM=1 Image dtbs -j16`.
Packed and verified with:

```sh
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel /tmp/lidar-arm64-build/arch/arm64/boot/Image \
  --dtb /tmp/lidar-arm64-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --ramdisk artifacts/phase-04/initramfs/lidar-test-initramfs.cpio.gz \
  --cmdline-append clk_ignore_unused \
  --output artifacts/phase-04/boot-lidar-usb-acm-clean-control.img
# same arguments with --verify <image> instead of --output: verify OK
```

| Item | sha256 |
|---|---|
| Image (9 241 088 B) | `530f0f2dcf3ffc9406383bc4a00da930bf3fe04176e6fe2bfc3c40086ab0a79f` |
| DTB | `030d966f97460ad5faae963603967f7f26fe8c36e4871382721531ade7341047` |
| ramdisk | `7b4a7c85313e772b95760288f43a8896d69b8141f09d9e9ae6ab0660b0605325` |
| boot image (16 MiB) | `2e5b4584922b67b170760ebca423676a26671335606d1a9e5f96452f4e1e848c` |

Host evidence only; not flashed. Device `boot_a` still holds `5aba70f6...`.

## Clean USB control on hardware, 2026-11-17

The owner approved one `boot_a` write of `2e5b4584...`, one reboot and read-only
observation, with the Lidar in fastboot (Action held, mains before USB). Logs are in
`experiments/phase-04/hw-20261117-clean-control/`. The fastboot binary was the saved
android-tools 37.0.0p1 under `experiments/phase-03/session-state/20261114/tmp/`.

- Preflight: `getvar product` returned `LIDAR`; image sha256 matched.
- `fastboot flash boot_a`: `Sending OKAY`, `Writing OKAY`. No partition readback ran;
  this fastboot has no partition read.
- `fastboot reboot` returned OKAY, and `lsusb` was then polled every 0.25 s for 180 s:
  preloader `0e8d:2000` at 2.0 s, 67.2 s and 132.7 s, each lasting about 2.8 s. No gadget
  `1d6b:0104`, no `/dev/ttyACM*`, and no fastboot device appeared.

Result: the image resets about every 65 s and never enumerates USB. The kernel config
has `# CONFIG_WATCHDOG is not set`, so [INFERENCE] the reset is probably the boot
chain's own watchdog, which nothing services after the handover. A kernel that never
ran would trip the same watchdog, so this run does not show whether the kernel or init
executed. pstore is at `0x60000000`, outside LK's mapped regions
(`fastboot-boot-research.md`), so Kaeru `fetch` cannot read it. Gate not met. The
device was left in this reset loop.

## Watchdog and fetchable-pstore diagnostic, 2026-11-17

Diagnostic branch `experiment/lidar-wdt-fetch-diag` in `repos/LibreEcho-Linux` (from
`a251a739`, uncommitted; diff saved as
`experiments/phase-04/hw-20261117-wdt-diag/kernel-diag.patch`, sha256 `a53c473f...`)
adds `CONFIG_WATCHDOG`/`CONFIG_MEDIATEK_WATCHDOG` (the reference config enables the
driver) and moves ramoops to `0x43810000` size `0x60000`, the window Kaeru `fetch ramoops`
reads. The product placement stays `0x60000000`. The initramfs `init` now honours
`lidar.autoreboot=<s>` on the command line (ramdisk `07f6b9b8...`). Image
`artifacts/phase-04/boot-lidar-wdt-fetch-diag.img`, sha256 `24e1b5f2...` (kernel
`92e55a70...`, DTB `b1a30bd5...`), command line append
`clk_ignore_unused lidar.autoreboot=150`; pack verify OK.

Baseline before the flash: `fastboot oem fetch-enable` and then `fastboot fetch ramoops` returned
`dumps/20261117-lidar-wdt-diag/ramoops-baseline-before-flash.bin` (sha256 `c6c17d11...`),
with no `DBGC` header and no kernel text.

With owner approval: one `boot_a` write and one reboot. The owner held Action from about 30 s.
Observer log `experiments/phase-04/hw-20261117-wdt-diag/reboot-observe.log`: the
preloader appeared at 2.0 s, BROM `0e8d:0003` at 67.0 s, the preloader at 72.3 s, and fastboot at 78.0 s.
The reset came at the same ~65 s as before, not at the 150 s auto-reboot.

The fetch after the run returned `dumps/20261117-lidar-wdt-diag/ramoops-after-diag.bin` (sha256
`1162d698...`), with `DBGC` headers at 0x0, 0x10000 and 0x50000. Its console zone was extracted to
`dumps/20261117-lidar-wdt-diag/kernel-console-diag.log` (244 lines). Findings:

- The kernel boots, all four CPUs come up, and `ramoops: using 0x60000@0x43810000`. pstore
  at this address works through a warm watchdog reset.
- `mtk-power-controller ... power-domain@4: failed to power on domain: -110`. Domain 4 is
  `MT8167_POWER_DOMAIN_MFG_ASYNC`. The whole power-controller probe then fails with -110,
  with `device_release` warnings for the domains it had already added.
- The last line is `11005000.serial: ttyS0 at MMIO 0x11005000 ... ST16650V2`. No later
  initcall printed anything. `mtk_wdt`, `mtk_rng`, and MUSB come after `mtk8250` in
  `System.map`, so the watchdog driver never ran and init never started. The ~65 s reset is
  the boot chain's watchdog after a stall in or just after the UART probe.

Phase 4 gate not met. Device `boot_a` holds `24e1b5f2...`; the device is in fastboot.

## initcall_debug run, 2026-11-17

With owner approval: `boot_a` was written with `artifacts/phase-04/boot-lidar-wdt-fetch-initcall-diag.img`
(sha256 `52a59d7a...`; the same kernel, DTB, and ramdisk as `24e1b5f2...`, with `initcall_debug` added to the
command line) and the device rebooted once. Observer log
`experiments/phase-04/hw-20261117-initcall-diag/reboot-observe.log`; the reset again came at ~65 s.
The fetch returned `dumps/20261117-lidar-initcall-diag/ramoops-after-initcall.bin` (sha256
`6c471b9d...`). The console zone (DBGC start=size=12776, not wrapped) is in
`kernel-console-initcall.log`.

Result: inconclusive. `initcall_debug` is on the kernel command line, but no `calling`/`initcall`
lines were recorded. They print at `KERN_DEBUG`, and the pstore console only receives lines
above the console log level. The next image of this kind needs `ignore_loglevel` (or `loglevel=8`).
The log again ends at the `ttyS0 ... ST16650V2` line. LK also appends `skip_initramfs` and
`root=/dev/dm-0`, which this kernel does not act on (it stalls before init).

## Second-stage U-Boot, first hardware attempt, 2026-11-17

Source: upstream U-Boot v2026.10 (`5508406582f6`) in `repos/u-boot`, branch
`lidar-fastboot-stage2` (uncommitted); see `experiments/phase-04/uboot/README.md`. The build used
clang and ld.lld because the host has no aarch64 GCC. Image `artifacts/phase-04/uboot/u-boot-boot.img`,
sha256 `3840afb6...`.

With owner approval: `boot_a` was written with this image and the device rebooted once. The flash
returned OKAY. Observer log `experiments/phase-04/hw-20261117-uboot/reboot-observe.log` shows the
preloader at 2.0 s to 4.7 s and then no USB device up to 45 s. A second observer run logged
nothing, because its leading `fastboot reboot` blocked with no fastboot device present. The owner
then power-cycled into Kaeru while holding Action. The Kaeru `fetch ramoops` after this
(`dumps/20261117-lidar-uboot-try1/ramoops-after-uboot.bin`, sha256 `bfb52e43...`) holds no `DBGC`
headers, because DRAM decayed during the power-off.

Likely root cause (host evidence only, from `llvm-readelf -S` and `llvm-nm` on `/tmp/lidar-uboot-build3/u-boot`):
ld.lld placed `.bss` at address `0x0` (`__bss_start` = 0, `__bss_end` = `0x9a20`) instead of
overlaying it after `.rela.dyn` at `0x400e8fc8`. This is the same fault as the negative
`image_size` in the Image header. U-Boot clears BSS early and would write to `0x0..0x9a20`, which
is not DRAM, so it stops before any console or USB. The reference project builds with Debian's
`gcc-aarch64-linux-gnu` and GNU ld (`reference/lidar-mainline/Containerfile:4`). Next: rebuild
with an aarch64 GCC and binutils, then check that `.bss` follows `.rela.dyn` and that the
header `image_size` is positive before asking for another flash.

Device state after this run: `boot_a` held the U-Boot image `3840afb6...`; the device was in Kaeru fastboot.

## Second-stage U-Boot, GCC build, 2026-11-17

The owner installed `aarch64-linux-gnu-gcc` 16.2.0. Build:
`PATH=/tmp/lidar-uboot-gcc/scripts/dtc:$PATH make O=/tmp/lidar-uboot-gcc ARCH=arm CROSS_COMPILE=aarch64-linux-gnu- -j16`
(the `fdtoverlay` from the build tree must be on `PATH`). `.bss` now starts at `0x400e40f8`, after `.rela.dyn`, and
the header `image_size` is `0xe40f8`. Packed with `pack_uboot.py` as
`artifacts/phase-04/uboot/u-boot-boot-gcc.img`, sha256 `dfe755fd...`.

With owner approval: one `boot_a` write (OKAY) and one reboot. Observer log
`experiments/phase-04/hw-20261117-uboot-gcc/reboot-observe.log`: the preloader was present from 2.2 s to 4.9 s, there was no USB
device after that, and the preloader came back at 67.4 s. A warm reset by the boot-chain watchdog at the usual ~65 s means
U-Boot either did not reach `board_early_init_f` (which clears TOPRGU `MODE.EN`) or was never entered. The
owner held Action through a later reset, and the device is in Kaeru fastboot. Next: a RAM breadcrumb build that
writes markers to `0x43810000` for a Kaeru `fetch ramoops` after a warm reset.

## Second-stage U-Boot, breadcrumb runs, 2026-11-17

All runs below were owner-approved, with one `boot_a` write and one reboot each. Breadcrumb format: magic `LUBT`
at `0x43810000`, a u32 write offset at +4, and ASCII text from +16. U-Boot writes the first marker from
`save_boot_params` before it sets up a stack or the MMU, so a missing marker means LK never jumped.

1. `u-boot-boot-gcc-crumbs.img` (sha256 `e9dfc9ed...`), packed by `pack_uboot.py` with the U-Boot DTB and
   the stock ramdisk. The board reset at 67 s. After the owner held Action through a warm reset, the fetch
   (`dumps/20261117-lidar-uboot-crumbs/ramoops.bin`, `bfb52e43...`) was byte-identical to the fetch after the
   earlier cold power cycle, with no `LUBT`. LK never entered U-Boot.
2. `u-boot-crumbs-linuxdtb.img` (`2fc099bd...`): the same U-Boot packed by `pack_boot.py` with the Linux
   DTB and the test initramfs. This time there was no reset by 90 s and no USB, so the early watchdog stop ran
   and LK entered U-Boot. A power cut of about 1 s did not keep DRAM
   (`dumps/20261117-lidar-uboot-linuxdtb/ramoops.bin`, `abb4541d...`, decayed). Which part of the
   `pack_uboot.py` layout LK rejects is still open.
3. `u-boot-crumbs-keepwdt.img` (`787ad5c7...`): `pack_boot.py` layout, with `-DLIDAR_KEEP_LK_WDT=1` and the
   WDT, WDT_MTK and SYSRESET options turned off, so a hang ends in a warm reset. The reset came at 67.4 s and Kaeru at 73.4 s.
   The fetch `dumps/20261117-lidar-uboot-keepwdt/ramoops.bin` (`8d71caba...`) is decoded in `uboot-crumbs.log`: all markers from
   `SAVE_BOOT_PARAMS` to `fastboot` are present, and the U-Boot banner shows DRAM 1017.8 MiB. Then
   `mtk_musb usb@11100000: failed to get usbpll clock`, `USB gadget unavailable (-19)`, and
   `g_dnl_register: failed!, error: -6`. The TOPRGU mode read 0x5d (enabled) on entry.

Cause of the USB failure: `drivers/clk/mediatek/Makefile` builds `clk-mt8516.o` only for
`TARGET_MT8516`, so the Lidar target had no topckgen provider. Fix: build the file for
`TARGET_LIDAR` too. `lidar.c` now has `lidar_stop_lk_wdt()`. Normal builds call it in `board_early_init_f`; builds
with `-DLIDAR_KEEP_LK_WDT=1` call it only after the USB gadget probes. Image
`artifacts/phase-04/uboot/u-boot-crumbs-keepwdt-clk.img` (`db2f50e8...`, build dir `/tmp/lidar-uboot-diag-wdt`).

Clock-fixed run (`db2f50e8...`): no reset and no USB by 100 s. U-Boot reached `USB_OK` (the watchdog stops only
after that marker) but the host never saw a device. The device stayed hung, and the owner cold power-cycled it into Kaeru.

Watchdog-never-stopped run: `u-boot-crumbs-wdtalways.img` (`081c33c1...`, extra `-DLIDAR_WDT_NEVER_STOP=1`).
Observer: preloader at 2.2 s, no USB, warm reset at 67.5 s, Kaeru at 73.4 s. Fetch
`dumps/20261117-lidar-uboot-wdtalways/ramoops.bin` (`44037d65...`), decoded in `uboot-crumbs.log`:
`MTK MUSB OTG (Peripheral)`, `USB_OK`, then the `fastboot` marker with no error. The host enumerated nothing for
about 60 s, while the same port enumerates under Kaeru. Next: compare the MUSB setup with the reference project, and
log MUSB and PHY registers while fastboot waits.

USB diagnostic run: `u-boot-usbdiag.img` (`b6cb14c0...`), with the PHY forced to device mode after `mt_usb_phy_recover()`
and the registers logged once a second. Warm reset at 67.4 s, Kaeru at 73.4 s. Fetch
`dumps/20261117-lidar-uboot-usbdiag/ramoops.bin` (`d4c52355...`), decoded in `uboot-crumbs.log`. All the way to the
reset the registers read POWER=f0 (soft-connect, high-speed), DEVCTL=99 (B-device, session valid) and FADDR=00.
The host kernel log showed `new high-speed USB device`, then `device descriptor read/64, error -71` and
`device not accepting address, error -71`. Then: `unable to enumerate USB device`. Result: U-Boot now reaches the
host at high speed but fails on control transfers. Next: check whether the INTRUSB read in the poll hook clears
interrupts, and check the PHY or endpoint 0 handling.

Second USB diagnostic run: `u-boot-usbdiag2.img` (`8ec68008...`). The poll hook now runs after the ISR and no longer reads
INTRUSB, and SETUP packets are logged. Within 25 s of the reboot `fastboot getvar` found no device. The host log (`experiments/phase-04/hw-20261117-uboot-usbdiag2/host-dmesg.log`)
showed the same repeated `-71` enumeration failures. Fetch `dumps/20261117-lidar-uboot-usbdiag2/ramoops.bin`
(`d26f0e30...`): registers unchanged, and no SETUP packet logged, so the controller never delivered a setup to the
gadget code. The read-to-clear dump was not the cause. Next: keep LK's PHY state and log the interrupt enables and counts.

Third USB diagnostic run: `u-boot-usbdiag3.img` (`df02ce75...`), which keeps LK's PHY state (no U-Boot PHY writes). The host saw no
U-Boot device. Fetch `dumps/20261117-lidar-uboot-usbdiag3/ramoops.bin` (`12ba7ec7...`). At handoff LK leaves the PHY
suspended (PHY 68=d4, 6a=ba, 1a=00; MUSB FADDR=23 POWER=21), so U-Boot must power the PHY on. The MTK L1 interrupt
status reads 0x300 about 567k times a second, even though the ISR clears it on each read. That is a level-triggered interrupt storm, and it
likely starves the gadget loop. MUSB events: usb=1, tx=0, rx=0. Next: power-on path plus correct handling of L1 bits 8 and 9.

Correction to the third run: U-Boot's `request_irq()` is a no-op, and the fastboot loop polls the ISR on every pass, so the
0x300 count is the poll rate reading a steady status, not an interrupt storm. L1INTS bits 8 and 9 are the VBUSVALID and
IDDIG status bits.

Fourth USB diagnostic run: `u-boot-usbdiag4.img` (`32bbb14b...`). L1INTM is programmed to 0x0f, the D+ pullup drops for
250 ms before U-Boot reconnects, and the ISR counts each event type. Fetch `dumps/20261117-lidar-uboot-usbdiag4/ramoops.bin`
(`60eb8471...`), decoded in `uboot-crumbs.log`. Over about 60 s: about 35 bus resets, a few suspends, about 8000 SOF
interrupts a second, and tx=0 rx=0 with CSR0=0 throughout. The host log shows the same `-71` failures. The controller
receives HS token packets (SOF), but no SETUP ever lands in endpoint 0.

Register comparison with working LK, 2026-11-17. With the unit in Kaeru fastboot (which enumerates at high speed on the
same host, hub and wires), `fastboot oem peek` plus `getvar peek` read the live PHY, MUSB and TOPCKGEN registers. Reads
only; MUSB 0x00-0x0f (read-to-clear) were skipped. Output: `dumps/20261117-lidar-kaeru-usb-regs/peek.txt`. Every
register usbdiag4 logged matches LK: TOPCKGEN 0x20/0x24/0x3c, L1INTM=0x0f, DEVCTL=0x99, PHY bytes 1a/20/21/22/68/6a/6c/6d.
The PHY bytes usbdiag4 did not log differ. U-Boot's `mt_usb_phy_recover()` sets byte 0x00 bit 5 (`RG_USB20_INTR_EN`,
the internal resistor for the termination reference) and sets the squelch threshold `SQTH` (byte 0x18, low nibble) to 6.
LK runs with INTR_EN=0 and SQTH=2. The vendor kernel (`usb20/mt8163/usb20_phy.c`) never sets INTR_EN, and upstream
Linux `phy-mtk-tphy.c` sets SQTH=2. Our Linux USB fork also set INTR_EN (upstream tphy) and SQTH=6, and it also failed to
enumerate. Losing longer data packets while short SOF tokens get through fits a squelch or termination fault.
[INFERENCE] The reference project runs the same upstream writes and reports working U-Boot fastboot, so this setting may
be marginal rather than always fatal. Its pogo-pin wiring is not the same as our test-point wiring.

Next image `u-boot-usbdiag5-lkphy.img`: apply LK's INTR_EN=0 and SQTH=2 after U-Boot's PHY init. If no SETUP arrives
within 20 s, write every PHY word LK showed (0x00-0x20, 0x60-0x6c) and reconnect. Dump the full PHY and MUSB registers
for comparison with the LK dump. After the first SETUP, kick the watchdog from the fastboot poll loop, so a working
session is not reset at about 65 s.

Fifth USB diagnostic run: `u-boot-usbdiag5-lkphy.img` (`f46d46ad...`), flashed to boot_a from Kaeru, then rebooted.
Logs are in `experiments/phase-04/hw-20261117-uboot-usbdiag5/` (`flash.log`, `observer.log`, `host-dmesg.log`, `getvar.log`).
Preloader at 2.2 s. At 10.1 s the host enumerated a high-speed device `0bb4:0c01`, `Manufacturer: LibreEcho`,
`Product: USB download gadget`, with no `-71` errors. `fastboot getvar version` returned `0.4` (U-Boot fastboot) at
about 20 s, and again at about 83 s. The device stayed attached through the end of the 75 s observer window, with no
warm reset, so the watchdog kick works. Enumeration came before the 20 s fallback could trigger, so LK's PHY tuning
(INTR_EN=0, SQTH=2) was enough by itself. Result: U-Boot USB fastboot works on this unit. `fastboot boot` is not tested yet.
The breadcrumb log has not been fetched: U-Boot has no `fetch` command, and it stays readable in DRAM after the next warm
reset into Kaeru.

## U-Boot RAM boot of the Linux kernel and ACM shell, 2026-11-17

All hardware steps below were owner-approved. The PHY bisect run
(`hw-20261117-uboot-phy-bisect/`) enumerated U-Boot about 5 s after the jump with the upstream PHY
settings, so kernel K1 (`repos/LibreEcho-Linux` `experiment/lidar-console-wdt` at `24a9de47`, image
`boot-lidar-console-wdt-k1.img`, `5e090868...`) was used.

- `lidar_bootimg` passed the stock "Amazon Lidar DVT" DTB to K1 (`hw-20261117-k1-ramboot/`): U-Boot's
  libfdt rejects the unaligned appended DTBs with `FDT_ERR_ALIGNMENT`, every compatible check fails,
  and the code fell back to the last DTB. It also never copied the ramdisk. Fixed in
  `repos/u-boot` `board/libreecho/lidar/lidar_boot.c` (aligned copy before the check, no fallback,
  ramdisk copy with bounds); built, not packed or run on hardware.
- `uboot_manual_boot.sh` stages the image with `fastboot stage` and boots it with `oem run`
  (`unzip`, `cp.b`, `booti`); it reads the DTB and ramdisk offsets from the image. Only the RAM-loaded
  `u-boot-stage2-pstore.img` has `oem run`; the U-Boot in `boot_a` answers `Unsupported command`.
  K1 then ran on the LibreEcho DTB (`hw-20261117-k1-manual-booti/`): gadget `1d6b:0104` enumerated
  5 s after `booti`, `mtk-wdt` probed, the 240 s autoreboot fired, and pstore kept console and pmsg.
- The ACM shell only echoed (`hw-20261117-k1-acm-usbfs/`): busybox `cttyhack` ignores the redirected
  stdin and reopens the console tty, ttyS0. `initramfs/init` now starts the ttyGS0 shell with
  `setsid -c`. `initramfs/repack_initramfs.sh` swaps only `init` (a control repack reproduces
  `07f6b9b8...` byte for byte): `lidar-test-initramfs-setsid.cpio.gz` `fcbf9cb2...`, image
  `boot-lidar-console-wdt-k1-acm.img` `77bcf0f3...`, the same kernel and DTB as K1; pack verify OK.
- The host kernel has no `cdc_acm` module, so `acm_shell.py --usbfs` drives the ACM interface through
  usbfs, with access granted by `/etc/udev/rules.d/70-libreecho-lidar.rules`.

RAM boot of `77bcf0f3` (`hw-20261117-k1-acm-setsid/`): `acm-diagnostics.log` holds `uname -a`
(`Linux (none) 6.1.178+ ... aarch64`), `/proc/cmdline`, four Cortex-A35 cores (`0xd04`) in
`/proc/cpuinfo`, and the full `dmesg` (`Machine model: LibreEcho Lidar`). `acm-reboot.log` shows
`uid=0`, the marker `LIDAR_PSTORE_MARK_1432` written to `/dev/kmsg`, and `reboot -f`.
`pstore-display.raw`, read by `pstore_readback.sh` after the warm reboot, contains the marker
followed by `reboot: Restarting system`.

## Slot boot of 77bcf0f3 through LK, 2026-11-17

The owner approved a `boot_a` write of `77bcf0f3` (`hw-20261117-k1-acm-flash/`). In Kaeru
(`product: LIDAR`, `unlock_status: true`), `fastboot flash boot_a` returned OKAY.
`fastboot oem fetch-enable` followed by `fastboot fetch boot_a` read the slot back as `77bcf0f3...`
(`dumps/20261117-lidar-k1-acm-flash/boot_a-readback.bin`).

After a disconnect-first cold boot without the Action button, the preloader appeared from 14:36:06
to 14:36:09. Up to 14:40:44 no USB device appeared and no reset happened: no gadget, no
boot-chain watchdog reset at about 65 s, and no 240 s autoreboot. The same kernel, DTB and
initramfs reach init under U-Boot, so the LK handover is the difference. Candidates, none tested:
LK's appended `skip_initramfs root=/dev/dm-0`, LK's choice and edits of the DTB, or its ramdisk
placement. The pstore zone is at `0x60000000`, which Kaeru `fetch` cannot read, so this boot left
no readable log. The device was left hung; `boot_a` holds `77bcf0f3`.

Gate status: everything the gate lists has been captured under a U-Boot RAM boot, but the gate
requires a boot from a single slot, and the slot boot through LK failed. The gate stays open.

## LK slot boot diagnosis and ACM shell from boot_a, 2026-11-17

Each run below was flashed to `boot_a` in Kaeru by
`hw-20261117-k1-fetch-diag/flash.sh`, and each `fetch boot_a` readback matched the image.
Each boot was a disconnect-first cold boot without the Action button. The DTB
`artifacts/phase-04/dtb/k1-lidar-fetch.dts` (`b1a30bd5`) moves ramoops to `0x43810000` (size
`0x60000`), which Kaeru `fetch ramoops` can read. After a warm reset with Action held, the
console zone survives; `hw-20261117-k1-fetch-diag/fetch.sh` reads it without a flash. The decoded
logs are in `dumps/20261117-lidar-k1-fetch-diag/console-*.txt`.

| Image | Change | Result |
| --- | --- | --- |
| `4d2599ca` | fetch DTB, `watchdog.handle_boot_enabled=0` | no USB, no reset; ramoops decayed at power-off |
| `c50ad14d` | fetch DTB, `panic=5 panic_on_oops=1` | no USB, no reset |
| `f8d055ee` | `initcall_blacklist=mtk_wdt_driver_init` | no USB, no reset in 3 min |
| `8aebcc1d` | no `console=ttyS0` | reset every 65 s by the boot-chain watchdog |
| `a04448a8` | uart0 `disabled` in the DTB | no USB, no reset |
| `a8cfff3e` | uart0 and toprgu `disabled` | reset every 65 s |
| `3b5d3d93` | uart0 `disabled`, `/chosen` initrd properties | ACM shell, gate captures |

Two faults stop the LK slot boot.

1. LK passes no initrd. `console-nouart-nowdt-warm.txt` (`a8cfff3e`) shows LK uses our DTB (the
   disabled nodes stay disabled) but rewrites `/model` to `MT8167B`. `populate_rootfs` returns
   after 15 us with no `Unpacking initramfs`. The kernel then prints
   `Waiting for root device /dev/dm-0...` and waits forever for the `root=` that LK appends.
   In `lk_a.bin`, LK writes `linux,initrd-start` and `linux,initrd-end` only for IDME bootmode 2
   or `0x61` (VA `0x41E1B69E`, `0x41E1BE74`). It still copies the ramdisk to the header
   `ramdisk_addr` (`0x44000000`) on every boot (VA `0x41E1C3A6`). LK changes `/chosen` only
   with `fdt_setprop`, and `lk_a.bin` contains no `fdt_delprop`.
2. The uart0 probe stalls when uart0 is not a console. `console-noserial-warm.txt` (`8aebcc1d`)
   ends at `11005000.serial: ttyS0 at MMIO 0x11005000`. The serial core then powers the port
   down, and `mtk8250_runtime_suspend` polls `MTK_UART_DEBUG0` without a bound
   (`drivers/tty/serial/8250/8250_mtk.c:426`). After LK, the register never reads zero. The
   upstream driver still has no bound in this loop.

With the Linux watchdog driver running, both faults look like a dead board: `mtk-wdt` keeps the
boot-chain watchdog fed, so the board never resets and the RAM log is lost at power-off.

The fix in `3b5d3d93` keeps uart0 disabled and adds `linux,initrd-start = <0x00 0x44000000>` and
`linux,initrd-end = <0x00 0x440a6af2>` to `/chosen` (`k1-lidar-fetch-nouart-initrd.dts`,
DTB `e994545f`; the end address is the start plus the 682738-byte ramdisk). The kernel, ramdisk
and command line suffix are the same as in `a8cfff3e`.

Slot boot of `3b5d3d93` (`hw-20261117-k1-lk-slot-initrd/`): the gadget `1d6b:0104` enumerated.
`acm-diagnostics.log` holds `uname -a` (`6.1.178+ ... aarch64`), the LK `/proc/cmdline`,
`/proc/cpuinfo` and `dmesg` with `Unpacking initramfs...`, `Run /init as init process` and the
`lidar-init` stages. `acm-reboot.log` shows `uid=0`, the marker
`LIDAR_LK_SLOT_PSTORE_MARK_1757` (`marker.txt`) written to `/dev/kmsg`, and `reboot -f`. The owner
held Action through the warm reboot into Kaeru, and `fetch.sh lk-slot-marker-warm` read the
ramoops region (`ramoops-lk-slot-marker-warm.bin`, `9d7bbad4`). Its console zone has the marker
at line 1101 and `reboot: Restarting system` at line 1136.

In-Linux readback, 18:04: `hw-20261117-k1-fetch-diag/reboot.sh` ran `fastboot reboot` from
Kaeru, and LK booted `boot_a` into the ACM shell (uptime 2.23 s). `acm-pstore-mark.log` shows
`uid=0` and the marker `LIDAR_LINUX_PSTORE_MARK_1804` (`marker-linux.txt`) written to
`/dev/kmsg`. `reboot -f` dropped the link (`acm-pstore-reboot.log` has no output, as expected).
No button was held, and LK booted `boot_a` again. In `acm-pstore-readback.log` (uptime 11.96 s),
`/sys/fs/pstore` lists `console-ramoops-0` (57328 bytes) and `pmsg-ramoops-0`. A search for
`MARK` in `console-ramoops-0` prints the new marker, and its last line is
`reboot: Restarting system`.

Open items: the fix lives in the DTB, so `pack_boot.py` should derive the initrd properties from
the header, and the 8250 wait needs a bound before uart0 can come back under LK. The power domain
`MFG_ASYNC` still fails with `-110` on both boot paths.

## LK slot initrd fix in source, 2026-11-17

The DTB fix now lives in the packager and in the kernel DTS.

`pack_boot.py` parses and rewrites the FDT itself (`parse_fdt`, `serialize_fdt`, `FdtNode`,
`FlatFdt`), so a replacement DTB gets `linux,initrd-start` and `linux,initrd-end` in `/chosen`
from the stock header `ramdisk_addr` plus the ramdisk length. Stock appended DTBs stay
byte-identical. `--verify` recomputes the expected DTB and checks the properties. Tests:
`python3 -m unittest experiments/phase-04/test_pack_boot.py`, 43 OK. The old image `3b5d3d93`
still verifies and reports `0x44000000..0x440a6af2`.

Kernel `repos/LibreEcho-Linux`, base `92af22e3`, branch `feature/lidar-support`:

| Commit | Change |
|---|---|
| `b96322d5faf0` | uart0 disabled, ramoops at `0x43810000` size `0x60000` (record `0x10000`, console `0x40000`, pmsg `0x10000`) |
| `22e6c3324ab8` | `CONFIG_DEBUG_FS=y` for the mt8167 config |
| `6276a30b0db9` | no-PMIC layout, `core_power` 1.15 V, `sdio_fixed_3v3` 3.3 V on GPIO24 with 500 ms startup (unreferenced) |

The CPU rail is recorded as a comment: Richtek RT5738 buck on i2c1 at 0x57, 0.3-1.3 V, always
on, vsel GPIO9 (stock DTS 1441-1466). Linux 6.1 has no RT5738 driver or binding, and a
`proc-supply` on an unbound regulator would let fw_devlink defer CPU consumers, so the node
stays out until both are backported.

Build branch `experiment/lidar-lk-slot-source` starts at `24a9de47` and holds the same three
changes as `bf102cdb` (dts), `cab0d025` (debugfs) and `79d8d10e` (rails), tip `79d8d10e`.

Build and pack:

```sh
make O=/tmp/lidar-lk-slot-source-build ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make O=/tmp/lidar-lk-slot-source-build ARCH=arm64 LLVM=1 olddefconfig
make O=/tmp/lidar-lk-slot-source-build ARCH=arm64 LLVM=1 Image dtbs -j16
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel /tmp/lidar-lk-slot-source-build/arch/arm64/boot/Image \
  --dtb /tmp/lidar-lk-slot-source-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --ramdisk artifacts/phase-04/initramfs/lidar-test-initramfs-setsid.cpio.gz \
  --cmdline-append "clk_ignore_unused lidar.autoreboot=240 panic=5 ignore_loglevel initcall_debug" \
  --output artifacts/phase-04/boot-lidar-lk-slot-source.img
# same command with --verify <image>: verify OK
```

`CONFIG_DEBUG_FS=y` is in `.config`; mount it with `mount -t debugfs none /sys/kernel/debug` if
it is not already mounted. Not exercised on hardware.

Schema check: the old venv `dt-validate` shebang names the removed `/tmp/lidar-dtschema`, and
`-m` is `--show-unmatched`, not the schema. A fresh `dtschema` in `/tmp/dtsvenv` with `-s`
works:

```sh
/tmp/dtsvenv/bin/dt-validate -s artifacts/phase-04/tmp-20261115/lidar-dtschema-build/Documentation/devicetree/bindings/processed-schema.json <dtb>
```

The previous DTB and the new one both exit 0 with the same five warnings: the unrecognised
`amzn,lidar-pvt` compatible, ramoops `ecc`, the generic `syscon` compatible and the `mmsys`
nodename. The rails add no warnings.

| Item | sha256 |
|---|---|
| kernel Image, 9 380 352 B | `91b4209fcf1d17729db39570405a9ee4d5bb6878831fb114842c128b548d1cea` |
| DTB | `0ed145b03a01914298e201a8e5ba398d3608d54692402e8117fe5155e20588da` |
| boot image, 16 MiB | `7284abc588ac5ab0b1bb8928b5aba105c7854f609c285bfb1bf4adb659a03fce` |

Stored: `artifacts/phase-04/boot-lidar-lk-slot-source.img`,
`artifacts/phase-04/dtb/k1-lidar-lk-slot-source.dtb` and `.dts`, and
`artifacts/phase-04/boot-lidar-lk-slot-source.sha256` (`sha256sum -c` passes).

The extracted DTB differs from `k1-lidar-fetch-nouart-initrd.dts` only by the pio phandle added
for the GPIO reference, `regulator-core` and `regulator-sdio-3v3`
(`artifacts/phase-04/dtb/k1-lidar-lk-slot-source.diff`). `/chosen`, uart0 and ramoops match the
hand-built tree.

Caveat: at build time `feature/lidar-support` still carried the pre-clean-control MUSB glue
and had no `MEDIATEK_WATCHDOG`. The branch alignment section below removes both differences.
Not flashed; the device still holds whatever `boot_a` the last hardware session left.

## feature/lidar-support aligned with the gate image, 2026-11-17

Base `6276a30b0db9`. Two commits were added on `feature/lidar-support`:

| Commit | Change |
|---|---|
| `a47db1334a3c` | `revert(usb): restore upstream v6.1.178 MUSB and gadget code` |
| `d4e78e5f1bc3` | `build(mt8167): enable the MediaTek TOPRGU watchdog` |

The revert restores `drivers/usb/musb/mediatek.c`, `drivers/usb/musb/musb_gadget.c` and
`drivers/usb/gadget/function/f_fs.c` to v6.1.178 and deletes the two MT8163 contract tests.
`musb_core.c` and `phy-mtk-tphy.c` already matched v6.1.178. Neither branch carried the
LibreEcho WDT-reset probe options, so no hook removal was needed; the watchdog change is the
defconfig entry only.

`git diff feature/lidar-support experiment/lidar-lk-slot-source` is empty, so the branch now
holds the tree that produced the gate image.

Build command: `make O=/tmp/lidar-feature-align ARCH=arm64 LLVM=1
mt8167_arm64_defconfig`, then `make O=/tmp/lidar-feature-align ARCH=arm64 LLVM=1 Image dtbs
-j16`, with `KBUILD_BUILD_USER=user`, `KBUILD_BUILD_HOST=<WORKSTATION_A>`,
`KBUILD_BUILD_VERSION=2` and `KBUILD_BUILD_TIMESTAMP='Tue Nov 17 18:20:01 AEDT 2026'`.

| Item | sha256 |
|---|---|
| Image, 9 380 352 B | `4d1cae769fd4524a0569e580069bfb1e05051d99dc23140dc9776fc0ce5c6053` |
| DTB | `0ed145b03a01914298e201a8e5ba398d3608d54692402e8117fe5155e20588da` |

The DTB matches `0ed145b0` exactly. The Image does not match `91b4209f`. The `.config` and the
generated `autoconf.h`, `utsrelease.h`, `compile.h` and `utsversion.h` are identical to the
archived build. The differences start in the UTS_VERSION banner: `linux_banner` reads
`#2 SMP <date>` in this build and `# SMP ` in the archived one, which shifts `.rodata` after
the banner by `0x18` (`btypes` moves from `+0x140` to `+0x158`). An address-for-address
comparison then reports the shifted tables (`arm64_features`, `arm64_elf_hwcaps`,
`sys_call_table`) and the PC-relative operands in `.text` that reach them. The cause is the
pinned `KBUILD_BUILD_VERSION`, which also feeds `init/utsversion-tmp.h`. An unpinned rebuild
with `.version=1` and the archived timestamp was not completed, so an exact byte reproduction
of `91b4209f` is unverified. `git diff` shows no source difference.

## Gate run with the source-built image, 2026-11-17

Image `artifacts/phase-04/boot-lidar-lk-slot-source.img` (`7284abc5`), built from
`experiment/lidar-lk-slot-source` (`79d8d10e`) and packed by the new `pack_boot.py`, which writes
the `/chosen` initrd properties. The first attempt (`flash.sh`, after a cold boot into Kaeru)
failed: `fetch ramoops` returned `Value too large for defined data type`, the flash printed
nothing within 60 s, the readback was empty, and Kaeru stopped answering `getvar`. After a
disconnect-first power cycle into Kaeru, `hw-20261117-k1-fetch-diag/flash-only.sh` skipped the
ramoops fetch. The flash returned `OKAY`, and the `boot_a` readback
(`boot_a-readback-lk-slot-source-retry.bin`) matches `7284abc5`.

The owner then did a disconnect-first cold boot without Action. Logs are in
`hw-20261117-lk-slot-source/`:

- `acm-diagnostics.log`: uptime 2.26 s, `uid=0`, `uname -a` (`6.1.178+ #2 SMP Tue Nov 17
  18:20:01 AEDT 2026 aarch64`), the LK `/proc/cmdline`, four Cortex-A35 cores (`CPU part
  0xd04`), `/proc/partitions` (`mmcblk0` p1 to p16, boot0, boot1), debugfs, the regulator
  summary (`mmc_power` 3.3 V, `mmc_io` 1.8 V, `core_power` 1.15 V, `sdio_fixed_3v3` unused),
  the clock summary, and `dmesg` with `Unpacking initramfs...`.
- `acm-mark.log`: the marker `LIDAR_SOURCE_PSTORE_MARK_1827` (`marker.txt`) written to
  `/dev/kmsg`, then `reboot -f`.
- `acm-pstore-readback.log`: after the warm reboot (uptime 11.97 s), `console-ramoops-0` holds
  the marker.

The kernel reports `#2 ... 18:20:01`. The previous section explains the Image hash difference
by a missing build number in the archived Image, but the booted Image shows `#2`. So that
explanation is unverified, and the cause of the hash difference is open. Both branches still
have the same source tree.

## Peripherals: buttons, LEDs, SDIO, codecs, 2026-11-17

Kernel `repos/LibreEcho-Linux`, branch `feature/lidar-support`, base
`d4e78e5f1bc368c15dd22bb335a5ecf7232d940e`.

| Commit | Change |
|---|---|
| `0c21b83d7854` | gpio-keys on GPIO7/12/42/108 and the GPIO18 `EV_SW` privacy switch; `CONFIG_INPUT`, `INPUT_EVDEV`, `KEYBOARD_GPIO` |
| `306226d8fbb3` | i2c0 with the IS31FL3236 at `0x3f` (36 channels, GPIO4 SDB via pinctrl); `CONFIG_I2C`, `I2C_CHARDEV`, `I2C_MT65XX`, `NEW_LEDS`, `LEDS_CLASS`, `LEDS_IS31FL32XX` |
| `5dc5c43a8c55` | mmc2/mc1 SDIO for the MT7668 combo, `reg_sdio_3v3` off-on delay, msdc2 source/hclk clock fix; `CONFIG_BT`, `BT_MTKSDIO`, `CFG80211` |
| `feb02cdf4e12` | i2c2 TLV320AIC32x4 at `0x18`, four TLV320ADC3101 at `0x18`-`0x1b` on i2c0, optional shared ADC reset in the driver; `CONFIG_SOUND`, `SND`, `SND_SOC` and both codec drivers |
| `fcb422ec7924` | DTS scope comment; `CONFIG_NEW_LEDS` and `CONFIG_SOUND` parent symbols |

Key nodes: gpio-keys `arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:139-188`, LED
controller `:324-375`, `&mmc2` `:227-249`, mmc2 clocks
`arch/arm64/boot/dts/mediatek/mt8516.dtsi:423-436`, mic ADCs `:452-496`, DAC `:504-521`,
pin groups `:280-364`.

`make savedefconfig` keeps all requested symbols: `CONFIG_I2C`, `I2C_MT65XX`, `I2C_CHARDEV`,
`INPUT_EVDEV`, `KEYBOARD_GPIO`, `NEW_LEDS`, `LEDS_CLASS`, `LEDS_IS31FL32XX`, `SOUND`, `SND`,
`SND_SOC`, `SND_SOC_TLV320AIC32X4_I2C`, `SND_SOC_TLV320ADC3XXX`, `BT`, `BT_MTKSDIO`,
`CFG80211`. `CONFIG_INPUT=y` is in `.config` but savedefconfig omits it as a default. The first
pass dropped the LED and sound symbols because `NEW_LEDS` and `SOUND` were unset; both parents
were added.

Build, host only, no hardware:

```sh
make O=/tmp/lidar-periph-build ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make O=/tmp/lidar-periph-build ARCH=arm64 LLVM=1 Image dtbs -j12
```

Exit 0. The DTC step for `libreecho-lidar.dtb` produced no warnings; the only warnings in the
log are clang warnings in `scripts/sorttable.c` and `drivers/clk/mediatek/clk-pll.h`.

| Item | sha256 |
|---|---|
| kernel Image, 5 577 329 B | `277e852dd10a4f821d7b3d44cbe93d9186b7cbc3b20f31353416278ad5e00398` |
| DTB | `866ae7a51907fe704f2b9fc13e016d8fb3df1d7f66849a14b45ebfe41ac7d25a` |
| boot image, 16 777 216 B | `8333baa427b2fc5daf60ae51f10f2d856af50009ac553a4c71ca7cd5b44096cd` |

Packed with the gate recipe from "LK slot initrd fix in source" (same stock `boot_a.bin`, same
`lidar-test-initramfs-setsid.cpio.gz`, same cmdline append, `--verify` recomputes the initrd
properties):

```sh
python3 experiments/phase-04/pack_boot.py \
  --stock dumps/20261110-lidar-readback/boot_a.bin \
  --kernel /tmp/lidar-periph-build/arch/arm64/boot/Image \
  --dtb /tmp/lidar-periph-build/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb \
  --ramdisk artifacts/phase-04/initramfs/lidar-test-initramfs-setsid.cpio.gz \
  --cmdline-append "clk_ignore_unused lidar.autoreboot=240 panic=5 ignore_loglevel initcall_debug" \
  --output artifacts/phase-04/boot-lidar-peripherals.img
```

The image is exactly 16 MiB (the envelope), the ramdisk sits at `0x44000000..0x440a6af2` and
the trailer from `0x5f9800` is all zero. This first image was flashed later; see "Hardware
runs" below.

Initramfs applets: `hexdump`, `dmesg`, `grep`, `ls`, `cat`, `dd`, `devmem` and `stat` exist;
`od` and `i2cdetect` are absent, so the checks below use `hexdump` and read the i2c bus through
sysfs only.

On-device checks (arm32 busybox shell on ttyGS0):

```sh
cat /proc/bus/input/devices
# expect "gpio-keys" and its inputN; no other input device

hexdump -C /dev/input/eventN    # press volume up/down, action, mic mute
# expect 0001 0073/0072 (KEY_VOLUMEUP/DOWN), 0001 008a (KEY_HELP),
# 0001 00f8 (KEY_MICMUTE); moving the privacy switch gives 0005 000e (SW_MUTE_DEVICE)
# start the hexdump in the background so the shell stays usable

ls /sys/class/leds
# expect ring1:red .. ring12:blue (36 entries)
echo 255 > /sys/class/leds/ring1:red/brightness
echo 0 > /sys/class/leds/ring1:red/brightness

ls /sys/bus/i2c/devices
# expect 0-003f, 0-0018, 0-0019, 0-001a, 0-001b, 2-0018

ls /sys/bus/sdio/devices
# expect mmc1:0001:1 (WLAN) and mmc1:0001:2 (Bluetooth) once the combo enumerates

dmesg | grep -iE 'mmc1|sdio|btmtksdio|aic32x4|adc3xxx|is31fl'
# expect the is31fl "36-channel atomic frame interface ready" line, mtk-sd probe on
# 11170000, codec probe messages, and btmtksdio binding or a firmware-load failure
```

Expected negatives: `/proc/asound/cards` stays empty because there is no MT8167 AFE or machine
driver; there is no `wlan0` because 6.1 has no MT7668 WLAN driver; `btmtksdio` may fail to load
`mediatek/mt7668pr2h.bin`, which this step accepts.

Hardware disputes: the action key uses `KEY_HELP` (138 = stock `0x8a`), not the reference's
`KEY_PROPS`, whose comment calls 130 `0x8a`. Stock puts action on GPIO3 and mute on GPIO18;
the DTS follows the hardware-verified GPIO42/GPIO108 mapping. The four ADC3101 share one reset
line on GPIO2, so only the `0x18` node owns `reset-gpios` and the driver now treats the reset
descriptor as optional. `mmc2` has no infracfg reset bank in this tree, so no `resets`
property is described.


### Hardware runs, 2026-11-17

Each image was flashed to `boot_a` from Kaeru with
`hw-20261117-k1-fetch-diag/flash-only.sh`, and its readback matched
(`dumps/20261117-lidar-k1-fetch-diag/boot_a-readback-peripherals{,-2,-3}.bin`). Each was then
cold-booted by the owner. Logs are in `hw-20261117-peripherals/`.

| Image | sha256 | Result |
|---|---|---|
| `boot-lidar-peripherals.img` | `8333baa4` | gpio-keys bound. `is31fl32xx` failed with `-22`: the ADC nodes sat inside the LED node. `11170000.mmc` failed with `-19` (`Cannot find pinctrl uhs!`). The DAC did not bind, and without aliases the eMMC came up as `mmc2` (`acm-probe.log`). |
| `boot-lidar-peripherals-2.img` | `09285ac9` | Fixed the LED node nesting, added `state_uhs` and the aliases. 36 LEDs, four ADCs bound, eMMC on `mmc0`, MT7668 enumerated. DAC probe `2-0018` returned 6 (`-ENXIO`) (`acm-probe-2.log`, `acm-buttons-3.log`). |
| `boot-lidar-peripherals-3.img` | `2e387bbe` | Restored the 1 ms wait after the DAC reset release. Every peripheral probes (`acm-probe-3.log`, `acm-buttons-5.log`). |

Evidence from image 3 (kernel `6.1.178+ #2 SMP Tue Nov 17 20:27:41 AEDT 2026`):

- I2C: `is31fl32xx` bound to `0-003f`, `tlv320adc3xxx-codec` to `0-0018` through `0-001b`,
  `tlv320aic32x4` to `2-0018`, with every `probe of` line returning 0.
- LEDs: there are 36 entries in `/sys/class/leds`. With all `*:red` channels at brightness 16,
  the owner saw the ring glow dim red. In an earlier run (`acm-probe-3.log`), all red channels
  went to 255 and the USB link then dropped with `EPROTO`. The owner saw the ring change
  between full and dim brightness and saw no flicker. The cause of the drop is not known.
- SDIO: the host reports `mmc1: new ultra high speed SDR104 SDIO card`, with functions
  `mmc1:0001:1` (`037a:7608`, WLAN, no driver) and `mmc1:0001:2` (`037a:7668`, bound to
  `btmtksdio`). Bluetooth fails as expected:
  `Direct firmware load for mediatek/mt7668pr2h.bin failed with error -2`.
- Sound: `/proc/asound/cards` reports `--- no soundcards ---`, as expected.
- Buttons: `dd` from `/dev/input/event0` while the owner pressed each button. The records are
  16-byte compat `input_event`s (the busybox is 32-bit). In order: `KEY_VOLUMEDOWN` (114) at
  107.62 s, `KEY_HELP` (138) at 109.00 s, `KEY_VOLUMEUP` (115) at 110.50 s, `KEY_MICMUTE` (248)
  at 112.23 s, then `SW_MUTE_DEVICE` = 1 at 112.25 s. Each key has a matching release. The owner
  confirmed that he pressed volume down first. The unit has no separate privacy switch: the mic
  mute button sets the hardware latch that GPIO18 reports.

Fix commits on `feature/lidar-support`: `2066d8c0` (DTS: LED node closed, `state_uhs`, `i2c`
and `mmc0` aliases) and `7594c578` (TLV320AIC32x4: 1 ms after reset release; commit
`abd2f555` had moved the upstream delay).
