# PLAN.md Phase 4 journal (frozen 2026-11-17)

This is the dated status journal that `PLAN.md` carried inside Phase 4 while the phase ran.
Phase 4 closed on 2026-11-17. The Phase 4 section of `PLAN.md` now keeps only the status,
the checklist with its done notes, the gate, the binding decisions and the handoff, and
points here for the running account.

The text below is verbatim from `PLAN.md` as of the close (lines 374-1093 of that revision).
It is a record, not instructions: several hypotheses in it were refuted later in the same
journal, and the exact commands, hashes and captures are in `notes.md`. Where a later entry
or `notes.md` overrides an entry, the later text wins.

Host status, 2026-11-15: the ARM64 kernel and Lidar DTB build successfully. The target planner,
source contracts, boot packager, image verifier, and Lidar-specific DT schema checks pass on the
host. The 16 MiB development image and its hashes are in `artifacts/phase-04/`. Exact commands
and results are in `experiments/phase-04/notes.md`. The new CI lane has not run because no push
is authorized. The first approved `fastboot boot` attempt on 2026-11-15 was rejected by Kaeru as
an unknown command. A separately approved `boot_a` write and reboot both returned `OKAY`, but no
fastboot, ADB or other Lidar USB interface appeared afterwards. No independent readback or kernel
boot evidence was obtained. The result is inconclusive, and hardware bring-up and the gate remain
unverified. `boot_b` and the boot chain were not changed.

Update, 2026-11-15: a read-only BROM readback of `boot_a`, `boot_b` and `misc` completed
with the existing da0 path. On-device `boot_a` is byte-identical to the first development
image (3d2997), so the earlier flash is confirmed on the slot. `boot_b` differs from its
2026-11-10 readback; normal userspace automatic update is a possible explanation, not
established causation and not proof that a kernel booted. `misc` differs in two bytes.
The root cause of the missing USB interfaces was found: the ARM64 defconfig lacked
`CONFIG_USB_CONFIGFS_RNDIS` and `CONFIG_USB_CONFIGFS_F_FS`, which the ARM32 defconfig
sets. Both are now added, and the revised image (boot image b2e01e, Image a2fd2d, DTB
unchanged) built cleanly and passed pack --verify and the 12/12 target tests.

Second update, 2026-11-15: the revised b2e01e image was flashed to `boot_a` and the device
rebooted under separate approval; both fastboot operations returned `OKAY` with the same
zero-partition-size AVB footer warning. No MediaTek USB or ADB interface appeared during a
90-second wait, so the boot remains inconclusive. Approved BROM diagnostics
(`dumps/20261115-lidar-phase4-revised/`) read RAM at `0x44410000` (0xe0000), RAM at
`0x44400000` (0x10000), and expdb (10 MiB). The RAM regions contain `RAM_RW` fill patterns
after cold entry with no readable Linux banner; expdb holds binary LK/Kaeru data with no
development-kernel banner. No boot verdict follows. Stock ramdisk inspection found a legacy
`android0` USB setup with `ro.debuggable=0` and `ro.adb.secure=1`, which an upstream
ConfigFS kernel cannot drive.

Third update, 2026-11-15: the diagnostic ADB image shipped. `pack_boot.py` gained an
opt-in `--diagnostic-adb` mode that rewrites only the ramdisk cpio entries `init.rc`
and `default.prop`: ConfigFS FunctionFS ADB gadget setup with the UDC write deferred
to a `sys.usb.ffs.ready=1` trigger, `ro.debuggable=1`, `ro.adb.secure=0`, and no
network ADB or RNDIS. The real stock cpio needed 4-byte name alignment support in the
cpio parser, and the test fixture now covers an unaligned `act` entry.
`test_pack_boot.py` passed 32 tests, the real diagnostic pack and
`--verify --diagnostic-adb` passed, and the base pack and verify passed with the base
image hash unchanged at `b2e01e`. I approved the diagnostic flash; the hash
was checked before flashing. `fastboot flash boot_a` of the diagnostic image and
`fastboot reboot` both returned `OKAY` with the same zero-partition-size AVB footer
warning. `adb wait-for-device` timed out after 90 seconds with no output; no kernel
version or userspace property evidence was obtained. This rules out the stock legacy
USB setup as the whole explanation, not every userspace issue. An early kernel fault
is a hypothesis, not proven. No further image flashes without new evidence; the next decisive diagnostic, as of
2026-11-15, was a 3.3 V UART console (superseded on 2026-11-17; see the course-change block). The device is in the post-reboot state
after the diagnostic image, with no DA/BROM session running. The Phase 4 hardware
gate remains open. Details: `experiments/phase-04/notes.md`.

Gate, replaced 2026-11-17: a development kernel boots from a single slot, and I reach
a root shell over USB CDC ACM (or SSH over USB NCM). Capture `uname -a`, `/proc/cmdline`,
`dmesg` and `/proc/cpuinfo` through that shell, and a pstore console readback after a warm
reboot. (Previous wording, until 2026-11-17: "a development kernel boots from fastboot or a
single slot. Capture boot evidence through available USB, ADB, pstore, or persistent logs.")

Status, 2026-11-17: the evidence the gate lists now exists for a boot from `boot_a` through
the stock LK (`3b5d3d93`, readback verified): root shell over USB ACM, `uname -a`,
`/proc/cmdline`, `dmesg`, `/proc/cpuinfo`, and a pstore console readback of a marker after a
warm reboot (read from Kaeru, and again from `/sys/fs/pstore` inside Linux). The DTB disables
uart0 and adds the `/chosen` initrd properties, because LK passes no initrd on a normal boot.
The gate awaits my review. Earlier, the same checks passed under a U-Boot RAM boot
(`77bcf0f3`). Details: `experiments/phase-04/notes.md`,
"LK slot boot diagnosis and ACM shell from boot_a".

My decision, 2026-11-17: the gate passes only after the fix is in source and a rebuilt
image boots again from `boot_a` with the same captures. In source means two changes:
`pack_boot.py` writes `linux,initrd-start` and `linux,initrd-end` from the boot image header,
and the Lidar DTS on `feature/lidar-support` disables uart0 and moves ramoops to `0x43810000`.
A bound on the `8250_mtk.c` idle wait is deferred, so uart0 stays disabled. The power domain
`MFG_ASYNC` fails with `-110` on every boot path; this is a known issue for the later display
and GPU work, not a Phase 4 item.

Gate passed, 2026-11-17: my condition is met. The source-built image
`boot-lidar-lk-slot-source.img` (`7284abc5`, from `experiment/lidar-lk-slot-source` `79d8d10e`;
`feature/lidar-support` has the same tree) was flashed to `boot_a` (readback verified) and
cold-booted through the stock LK. Over the USB ACM root shell it gave `uname -a`,
`/proc/cmdline`, `/proc/cpuinfo`, `dmesg`, the regulator and clock summaries, and a pstore
readback of a marker after a warm reboot. Details: `experiments/phase-04/notes.md`, "Gate run
with the source-built image".

Course change, 2026-11-17: I compared LibreEcho's Phase 4 with the independent
lidar-mainline project, which boots a mainline kernel on this device. The full comparison and
its evidence table are in `experiments/phase-04/lidar-mainline-comparison.md`; the decisions
below are binding.

- ADB is dropped as the Phase 4 verification route. Our failure is below ADB: the host never
  sees any USB connect at all, so no ADB or g_serial stack can help. The debug channel is now:
  a USB CDC ACM serial root shell (getty on ttyGS0), a USB NCM network link with SSH as a
  development-only service (key auth, bound to the USB interface, never a product default),
  and pstore/ramoops console readback after a warm reboot. Passwordless telnet, as in the
  reference, is rejected for LibreEcho.
- Phase 4 stays on Linux 6.1.178 (`repos/LibreEcho-Linux`, branch `feature/lidar-support`). A
  7.3 rebase is an evidence-gated later option, evaluated when Phase 6 needs Wi-Fi, cpufreq,
  or audio.
- Nothing from the reference project is built, flashed, or run. Only its facts and settings
  (config symbols, DT values, cmdline, boot-image constraints, gadget setup approach) are
  adopted. Reference driver code is license-compatible but AGENTS.md forbids copying from
  `reference/`; any copy in Phase 6 needs an explicit decision from me.
- Adopted Phase 4 work, in order: (a) USB clean control and removal of the WDT probe hooks;
  (b) `clk_ignore_unused` on the cmdline; (c) the defconfig changes listed in the checklist;
  (d) the DT memory, ramoops, pmu and cpu-idle-states changes; (e) our own ARM32 test
  initramfs; (f) `pack_boot.py` guards; (g) the approved flash sequence. Each step is an
  unchecked checklist item above.
- UART correction: the earlier "3.3 V UART console" diagnostic named the wrong level and
  assumed an input path. UART0 TX is test point TM58 at 1.8 V, 921600 8N1, output only;
  UART0 RX is on no known test point (reference README test-point table; not verified on our
  unit). The UART stays optional.

Entry milestone, 2026-11-15: a minimal ARM64 entry probe
(`experiments/phase-04/early_entry.S`, image sha256
`b5724301...`) proved the full path: LK decompressed the boot image and ATF entered it
at the expected address, shown by a persistent blue light on a cold boot with A
selected. Image format, load address and ARM64 architecture are proven viable through
the stock chain. This is not a Linux boot; the full kernel has not produced any
on-device evidence yet.

Late-init gate (open): the probe stops before kernel late init, so whether the kernel
reaches pstore_blk writes on `swdl`, USB, or a console is unproven. The pstore
candidate (sha256 `f2c5f4c6...`) was flashed to `boot_a` with A explicitly selected
and the slot stayed A after the reboot (BCB `00 41 42 42 01 8f 8e 00`, no fallback);
this is the first valid full-kernel run. I saw the blue light; no USB or ADB
interface appeared, and the `swdl` read (`swdl-after-valid-pstore.bin`, sha256
`83ee4724...`) was all 32 MiB zero with no `PSIG` record or kernel text. This shows
the kernel reached no working pstore_blk panic write and no userspace USB, and it
does not locate where the kernel stopped. Next planned diagnostic: a late-init forced
panic after the pstore backend initializes; not yet built or run. Before every
A-slot test, confirm A is selected; after the first failed A boot the BCB fell back
to B, so conclusions from that period about normal boots, missing USB, or zero pstore
do not prove the flashed image ran. The verified misc BCB repair (two-byte
priority/tries swap, `misc-slot-a.bin` sha256 `9248bd41...`) restored A selection and
must be repeated if B fallback recurs. `boot_b` was never written. A later
late-init forced-panic probe (`boot-lidar-pstore-panic-probe.img`, sha256
`10ee2b65...`, flashed with A selected) again left `swdl` all zero; this shows only
that no pstore block record appeared, not whether the panic or late init ran. Warm
BROM-only `mtk.py peek` reads of `0x44400000` and of the physical log buffer
(`0x4085f388`, from `__log_buf` minus `_text` plus the kernel physical base) were both
all zero, so the RAM path gave no kernel log either. The RAM-marker control resolved
this: after a loose wire was resoldered, a warm BROM peek of the marker address read
16 zero bytes, so the warm reset did not preserve a marker the boot-chain stage had written.
The earlier all-zero RAM and log-buffer reads are not usable kernel-stage evidence. A
requested manual warm-read repeat was cancelled with no device detection, and a
self-resetting control (`early_entry_ram_marker_reset.S`, image
`boot-lidar-ram-marker-warm-reset.img`, sha256 `d5b11ec0...`, marker write, 5-second
`CNTFRQ_EL0`/`CNTPCT_EL0` delay, then WDT_SWRST_KEY `0x1209` to `TOPRGU+0x14` per
`mtk_wdt.c`) also ended with no BROM detection; no marker file exists, so nothing
follows about whether the marker wrote or the reset fired. The warm-reset/BROM route
remains unusable as a log channel. A configuration audit then invalidated the earlier
pstore command lines: the base image carried a typo in the `swdl` PARTUUID
(`...-78a5-...` instead of the GPT-verified `<PARTUUID_12>`),
and the forced-panic image used an unrelated PARTUUID, omitted `best_effort`, and set
`console_size`/`kmsg_size` in bytes where the driver takes KiB, so that attempt was
not a valid logging configuration. A corrected image
(`boot-lidar-pstore-panic-probe-corrected.img`, sha256 `9e59e1d8...`, same panic
kernel and DTB, verified command line with `best_effort=y`, 64 KiB console/kmsg,
`max_reason=5`) was flashed to `boot_a` with A selected; `swdl` was again all 32 MiB
zero with no `PSIG` record. In a valid corrected run the kernel therefore either did
not reach late init or its eMMC/pstore setup failed; the result cannot distinguish
the two, and the typo is not proven to be the whole root cause. The next
dependable log channel is a physical UART; no USB-UART adapter is present on the
host, and a research agent is separately exploring a no-UART path
(`experiments/phase-04/no-uart-research.md`). A milestone followed: the RAM-marker
image now ends with the proven Kaeru stage2 watchdog reset sequence, and after its
flash and reboot `fastboot getvar product` returned `LIDAR` about 12 seconds later.
A fastboot return without BROM entry or a power cycle is proven. Marker persistence
in RAM is unknown: `oem mem read` attempts at `0x44400000` disconnected or failed,
a read of the watchdog at `0x10007000` hung, while `oem kaeru-version` returned
normally, so the `oem mem` implementation or address mapping is suspect and no blind
retries are planned. Current state: fastboot-reset marker image on `boot_a`,
`boot_b` untouched, A active. Work in progress: a full-kernel
`late_initcall_sync` fastboot-return milestone probe, and a read-only investigation
of the `oem mem` failure. The milestone then landed: a full-kernel driver
(`libreecho_lateinit_fastboot.c`, default-n `CONFIG_LIBREECHO_LATEINIT_FASTBOOT`,
repository defconfig unchanged) logs a tag at `late_initcall_sync`, writes the marker
`LIBREECHOLATEINIT!` to physical `0x44400000`, and performs the exact proven fastboot
watchdog reset. Image `boot-lidar-lateinit-fastboot-return.img`, sha256 `3deff1de...`,
kernel `c07213a5...`, DTB `2abaea8b...`; build, pack verify and objdump checks passed.
After the approved flash and reboot, `fastboot getvar product` returned `LIDAR` about
20 seconds later. This proves the full kernel reached `late_initcall_sync` on this
image: only that driver sets the reset, and the proof does not depend on pstore, MMC
or `oem mem`. It does not show that the earlier corrected forced-panic image reached
late init, though the same base makes it likely. The logging and storage path is now
the focus. Two findings then
closed that thread. First, a pstore backend conflict: `ramoops` registers at
`postcore_initcall` (`fs/pstore/ram.c:969`) and `pstore_blk` at `late_initcall`
(`fs/pstore/blk.c:348`), so the second `pstore_register` is rejected with `-EBUSY`
(`fs/pstore/platform.c:591-600`). An image forcing the backend
(`pstore.backend=pstore_blk`, `boot-lidar-pstore-panic-block-selected.img`, sha256
`6689fa7c...`, corrected GUID and 64 KiB settings kept) still left `swdl` all zero,
so the conflict is real but not the sole blocker; the MMC or device-open path is
suspected, not proven. Second, the `oem mem` investigation closed: the installed
binary matches its source and info/dispatch work, but even a safe one-byte read
inside LK produced no output. Do not retry `oem mem`. Because the earlier
`CONFIG_USB_G_SERIAL` negative predates valid slot-A control, a g_serial-only retest
(`console=ttyGS0`, no reset or panic) was then run. Image
`boot-lidar-usb-serial-console.img`, sha256 `9a768de0...`, clean defconfig plus
`CONFIG_USB_G_SERIAL=y` and `CONFIG_U_SERIAL_CONSOLE=y` (required for `ttyGS0` as a
printk console); verify OK, approved flash/reboot OK. No CDC ACM device appeared 12
seconds or an extra 20 seconds after the reboot, with the host journal showing
repeated preloader reconnects. The negative is now slot-A controlled, but the exact
failing subsystem is not identified; MUSB versus a later crash remains unresolved.
The next build is a minimal `oem peek` command (one aligned READ32 with an OKAY-only
reply that does not go through `mem_hexdump`); build only, no flash, and any
source-built stage hardware test needs separate approval given the Phase 3 records
of the expdb 256 KiB target and stock rollback. Current state: g_serial console image on
`boot_a`, `boot_b` untouched, A active.
The peek replacement then landed. The new Kaeru `cmd_peek` performs one aligned
READ32 into a static `peek_value[9]` buffer and publishes it; earlier variants hid
the OKAY reply and garbled a stack buffer, and the static buffer fixed the output.
The installed LK stage `expdb-lidar-kaeru-peek-static-0x40000.bin` (sha256
`72aaaa32...`) was written and read back exactly, with the stock tail unchanged.
`fastboot oem peek 41E30000` plus `fastboot getvar peek` returned `40080000`,
proving LK reads the address and transports the result. An approved re-flash of the
late-init return image (`3deff1de...`) to `boot_a` returned `product LIDAR`, but
`oem peek 44400000` disconnected the device: aligned reads inside LK work, DRAM reads
fault, likely because the source-built stage lacks the reference rammap-fixed
change. The subsequent mapping analysis corrected that hypothesis: the reference
rammap-fixed change uses a different stock LK, but the region lists are
content-identical; both mappings cover `bootimg 0x40080000..0x4407FFFF` and
`download 0x44FFF000..0x4DFFFFFF`, making `0x44400000`/`0x44410000` holes. There is
no reference MMU extension to port, and the missing-rammap-patch suggestion no longer
applies. A mapped-pstore kernel followed
(`boot-lidar-lateinit-fastboot-return-mapped-pstore.img`, sha256 `24c2c7ce...`,
kernel `a5ced1e6...`, DTB `64a54d48...`, verify OK): driver marker `0x45000000`,
ramoops `0x45010000`/`0xe0000`, records `0xc0000`, console and pmsg `0x10000`,
console address `0x450D0000`, clean late-reset config with stock cmdline and ramdisk.
A Kaeru LK stage added a bounded `fetch:` handler backed by `mem_region_find`,
`oem peek`, and `oem fetch-enable`. The enable command publishes `max-fetch-size`
and `partition-size:ramoops` through stock LK's published-variable table; Kaeru's
duplicate `getvar:` wrapper is not the handler serving the host. The LK stage
`expdb-lidar-kaeru-peek-fetch-enable-v2-0x40000.bin` (sha256 `0199258e...`) was
written and read back exactly. `fastboot fetch ramoops` then transferred the full
high-window region successfully. The capture, `ramoops-high.bin` (sha256
`79a4c415...`), contained repeating `6eUl` words and no marker, `PSIG`, or kernel
text; the high download window is overwritten by LK and is not a valid pstore
location. A coordinated kernel/LK build is moving the probe to marker
`0x44000000` and ramoops `0x44010000`/`0x60000` (records `0x40000`, console and
pmsg `0x10000`) inside the mapped boot-image window. The Phase 4 hardware gate
remains open until that capture is validated.
Details: `experiments/phase-04/notes.md`.

Fetch and capture result, 2026-11-15: the `0x44000000` layout was rejected before
any flash, because the stock ramdisk loads at `0x44000000`; that unsafe image was
deleted. The final layout uses marker `0x43800000` and ramoops `0x43810000`, size
`0x60000`, records `0x40000`, console and pmsg `0x10000`, and clears the kernel,
ramdisk, ATF and reservation overlaps. The final image
`boot-lidar-lateinit-fastboot-return-mapped-pstore-bootimg.img` (sha256
`9c837a8d62dcc18b396267a3dbdc6fe5d6717ad8979e8ab0a77b13eaf9d3d57a`, kernel
`208ce3ec...`, DTB `7a3d521c...`) passed pack verify and is on `boot_a`; `boot_b`
is untouched and A is active. The final Kaeru LK stage
`expdb-lidar-kaeru-peek-fetch-438-0x40000.bin` (sha256
`b9d8afa314f360165256262f17fb1ca45ca10a5cf0f8cd528c3a43013f4d2ed7`) was written and
read back exactly, with the stock tail unchanged. The fetch sequence on the device:

```sh
fastboot oem fetch-enable
# optional confirmation
fastboot getvar max-fetch-size
fastboot getvar partition-size:ramoops
fastboot fetch ramoops dumps/20261115-lidar-phase4/ramoops-438.bin
```

The transfer of `0x60000` bytes returned OKAY; the capture sha256 is
`331dd1aea1592db13e3cfab7f8ba34e8bf63f2a7e510664c2dd6a8ddca80cbc7`. The console
zone at offset `0x40000` uses a 12-byte `DBGC` header with the length at `+8`
(`0x1ca5`); the extracted `kernel-console-438.log` (sha256
`2d7396a93e1ce4f72e37db434d9a35dd8588ae95ad0548d1dbc6bbc6df722430`, 116 lines)
shows `ramoops: using 0x60000@0x43810000` and the late-init driver tag, so the
kernel reached `late_initcall_sync`. The log also shows the current failure set:
regmap lookups fail with `-ENOTSUPP` for `topckgen@10000000`, `syscon@15000000`,
`syscon@16000000` and `mmsys@14000000`; pinctrl `1000b000`, the power controller
and `clk-mt8167-mm` defer with `-524`; `mt6577-uart`, `mtk_rng` and `musb-mtk` fail
with `-ENOENT` (missing clocks). This identifies the clock/regmap thread as the
next root-cause target. No marker survived the reset, as expected for a warm RAM
marker. The Phase 4 hardware gate stays open: capture works, but the Phase 4
scope is not complete.
Details: `experiments/phase-04/notes.md`.

Syscon stall bisect, 2026-11-15: the clock/regmap failures now have an identified
root cause. The ARM64 defconfig (`repos/LibreEcho-Linux/arch/arm64/configs/mt8167_arm64_defconfig`)
did not set `CONFIG_MFD_SYSCON`, so every `syscon_regmap_lookup_by_phandle` returned
`-ENOTSUPP` from the stubs; enabling `CONFIG_MFD_SYSCON=y` selects `REGMAP_MMIO`.
The defconfig file is changed. No hardware claim follows from that change alone.

Two further images were flashed to `boot_a` under approval, each with a bounded
20-second plus 15-second fastboot check after the reboot; both checks failed, and
BROM recovery and the `fastboot fetch` capture worked both times. The first image
(`artifacts/phase-04/boot-lidar-syscon-early-marker.img`, sha256
`277334ae84da5dd2690e7e40ce39d75e55609897bf0477888a8c4081cbc0d3fe`) was built after
regenerating the defconfig and accidentally omitted
`CONFIG_LIBREECHO_LATEINIT_FASTBOOT`, so its no-fastboot result is not evidence
that the kernel stalled; do not use it as kernel-stall evidence. Its capture
`dumps/20261115-lidar-phase4/ramoops-syscon-early.bin` (sha256
`495148ea3481cd70f494d5c56daf6399333e236e43189b258468513dade86b13`) has no `DBGC`
record, no Linux text and no `PSIG`. The standalone RAM marker at `0x43800000` was
unreliable in that run; the capture shows the location overwritten.

The second image (`artifacts/phase-04/boot-lidar-syscon-pmsg-markers.img`, sha256
`9e44fd8813098d1467d7ae3393621fd4918076e83a2c616de2ea5f904da707ea`) carried pmsg
marker writes from early boot. It also failed the bounded fastboot check. Its
capture `dumps/20261115-lidar-phase4/ramoops-syscon-pmsg.bin` (sha256
`aa46d83bc9a88a6fce25292a68668bca376ca7d3a56dbd3a4bba9ea36b89b88f`) has no `DBGC`
record, no Linux text, no `PSIG`, and neither the early nor the late marker
strings. On a config where the identical base reached `late_initcall_sync` and
served `fastboot fetch`, this supports a stall before `early_initcall`; it does
not prove the syscon fix works.

Next test, built but not run: `start_kernel` probes in
`repos/LibreEcho-Linux/init/main.c`, gated by `CONFIG_LIBREECHO_LATEINIT_FASTBOOT`,
writing to the pmsg zone at physical `0x43860000` with a 4 KiB memblock
reservation taken after `setup_arch()`. Markers: `0x200` after `setup_arch`,
`0x300` before `time_init`, `0x400` after `time_init`. Image
`artifacts/phase-04/boot-lidar-syscon-start-kernel-probes.img`
(sha256 `99606a1b063d05b0b0cbdda9e9e37f5f648e1675a79f7e875496670bb5b544e5`). No hardware
result exists yet. The Phase 4 hardware gate remains open; no claim that the syscon
fix works, and Phase 4 is not complete.
Details: `experiments/phase-04/notes.md`.

Probe-result update, 2026-11-15: the pending `start_kernel` probe image above is
superseded by the runs recorded here. The C probes themselves are validated. A
cache-flushed, no-syscon control image (sha256 `7c6c0fc1...`) was flashed with the
Action button released and returned to fastboot; its `raw` capture (sha256
`4106ef91...`) contains the `PROBE-SETUP-ARCH!`, before/after-`time_init` markers
and the late-init marker. With `CONFIG_MFD_SYSCON=y` the same probes never appear:
the syscon-flushed image (dd1393d7) and the paging image (1a2d345e, marker at pmsg
offset `0x50500`) both left captures with no markers. A syscon image with a
map-mem probe (cd0da53e) failed the bounded fastboot check with the Action button
released, and its capture (7507345b) has no map, paging or later markers. Because
the pmsg path left doubt, a direct ARM64 store probe was added to
`primary_entry` in `head.S` at offset `0x50700`, run with the MMU off. The large
syscon image with that entry probe (07521890) failed, and its capture (302df5d6)
has no entry marker. The matching no-syscon entry control (f7c4d33d) returned to
fastboot with the Action button released, and its capture (624dad06) carries every
marker: `ENTRY`, `MAP-MEM`, `PAGING`, `SETUP`, before/after `time_init`, the late
marker, and a full `DBGC` Linux console log. The entry probe is therefore
validated, and the large syscon kernel never reaches `primary_entry`.

Image size was tested as a cause and ruled out as the whole explanation. The first
small-syscon image (ff36091d) returned to fastboot, but the user confirmed the
Action button was held throughout that run, so that return is invalid as kernel
evidence. The corrected retest with the Action button released failed. A
small-syscon image with the entry probe and MUSB disabled (7f6a89ca) also failed
with the Action button released; its capture (2520fe85) has no entry marker. The
shrink-alone hypothesis is disproven, and no size limit is proven. Boot-image
headers extracted from the flashed images agree: the large working no-syscon image
and the large failing syscon image both decompress to length 8282624 with
`image_size` `0x850000` and have identical first 64 bytes; the small syscon image
decompresses to length 8217088 with `image_size` `0x840000`.

Hardware tests are paused pending primary-source LK load and handover research in
`experiments/phase-04/lk-kernel-handover-research.md`. All further work is
source-backed; no more blind probes. The Phase 4 hardware gate stays open, and no
claim is made that the syscon change works.
Details: `experiments/phase-04/notes.md`.

LK replay update, 2026-11-15: the research report in
`experiments/phase-04/lk-kernel-handover-research.md` refutes two earlier
hypotheses with source-backed replay. H1 gzip truncation is refuted: all five
replayed decompressions end in `Z_STREAM_END`. H2 DTB differences are refuted:
the working and failing boot images carry 19-blob DTB collections that are
byte-identical at 1018698 bytes. Simple size or `image_size` therefore cannot
explain the large working and failing pair. A reserved-memory audit shows only
blob4 declares `ramoops@43810000`, and the observed kernel selected blob4; the
common `minirdump@444f0000` region of size `0x10000` was chosen for a second
entry marker at `0x444f0800`.

Next experiments, in order: first an active-slot plus `boot_a` byte-hash
verification; then a dual-address `primary_entry` marker probe writing both
`0x43860700` and `0x444f0800`; then a fetch of both regions. The dual-entry
probe image is built and checked on the host:
`artifacts/phase-04/boot-lidar-syscon-dual-entry-probe.img`, sha256
`af8bc486cce08d6bb4847d5a30edbc596db17458cd020a10a3dbc7da5a301b53`. A new
expdb LK stage
`artifacts/phase-04/expdb-lidar-kaeru-peek-fetch-438-444f-0x40000.bin`, sha256
`3f215a64edcd0e47e9e47e62494cae8e563b666f1127b7f351e1eb82f4418940`, publishes
the minirdump fetch; the prior installed `438` stage stays untouched. Build,
disassembly, packing, and `check_payload` all pass. No hardware run happened.

Risk: `0x444f0000` lies outside the documented LK mappings, so the minirdump
fetch may fault or disconnect the session. The MMU-off store in `primary_entry`
is unaffected. Device writes still require user approval, and a readback
mismatch aborts before any write. Phase 4 remains open, and syscon is not
validated.
Details: `experiments/phase-04/notes.md`.

Entry-probe relocation update, 2026-11-15: the minirdump fetch attempt
confirmed the recorded risk; `fastboot fetch` of the `0x444f0000` region
disconnected, because it lies outside LK's mappings, and no data was
captured. A BROM `mtk.py peek` of `0x444f0800`/`0x10` succeeded after a
transient handshake retry and returned 16 zero bytes (sha256 `374708fff...`);
the result is inconclusive because earlier Phase 4 warm-BROM RAM reads failed
to preserve a known valid marker, so no conclusion about the entry marker
follows from it. The custom minirdump diagnostic is replaced: the Lidar DTS
declares a `no-map` reserved-memory region `entry-probe@43ff0000`, size
`0x10000`, marker `0x43ff0800`, inside LK's bootimg mapping and ending at
the ramdisk address `0x44000000`. The LK stage now publishes `entryprobe`;
the ramoops marker `0x43860700` is unchanged. Host-verified artifacts, no
hardware run: `boot-lidar-syscon-mapped-dual-entry-probe.img` sha256
`1119e33f09da4d4a6dc2271d8a35386b82c1088877a8e8cfbcfb1f19a60e628c`,
`boot-lidar-no-syscon-mapped-dual-entry-control.img` sha256
`017540d527eeb09955dc22b57ba41c44efc9869fc7176796859388bc447a5810`,
`expdb-lidar-kaeru-peek-fetch-438-43ff-0x40000.bin` sha256
`1b3cd36da5c96479cc81ca1603c9d94bd1d1af1518265f2b5143883200d8fad7`. Pack
verify passes on both images, both carry the identical DTB (sha256
`99152dbc...`), disassembly shows the marker store in both kernels before
`preserve_boot_args`, and `check_payload` passes 46/46. Next run order:
flash the LK stage, transient `fastboot boot` of the no-syscon control
(`boot_a` unchanged), fetch `entryprobe` plus ramoops to validate the
channel; only then flash and test the syscon mapped image. The attempt
waited 300 seconds with no fastboot device, so no write or boot occurred.
Phase 4 remains open, syscon is unvalidated, and device reconnection is the
blocker.
Details: `experiments/phase-04/notes.md`.

Mapped-entry controlled runs, 2026-11-15: `fastboot boot` was rejected as an
unknown command, so the no-syscon mapped control
(`boot-lidar-no-syscon-mapped-dual-entry-control.img`, sha256 `017540d5...`)
was flashed to `boot_a`; `boot_b` stayed untouched. The control returned to fastboot
and its captures validate the channel: `PROBE-ENTRY` at `entryprobe+800` and
the marker at ramoops offset `0x50700`, plus a full DBGC Linux console.
Captures: entryprobe sha256 `6251553d...`, ramoops sha256 `f7a66a24...`. The
syscon mapped image (`boot-lidar-syscon-mapped-dual-entry-probe.img`, sha256
`1119e33f...`) failed the bounded fastboot check; both markers are absent
(entryprobe sha256 `2fdfef35...`, ramoops sha256 `3fa69359...`), and the
post-run `boot_a` readback is byte-identical to the flashed image hash, so the
right image ran. A size-padding no-syscon control (sha256 `61a0e6b8...`) kept
the working kernel, gzip, DTB and ramdisk bytes but carried the syscon image's
exact `kernel_size` `0x4268e7` and `ramdisk_offset` `0x427800` header values;
with the Action button released it returned to fastboot, which excludes
boot-image size and layout as the cause. Two gzip variants of the syscon
kernel followed: the gzip6 image (sha256 `f23822e3...`) decompresses to the
same syscon `Image` (sha256 `fa90a628...`) and failed with both markers
absent (entryprobe sha256 `85e9c3c6...`, ramoops sha256 `b43e8968...`); the
gzip0 stored-deflate image (sha256 `17b16b93...`) has the same decompressed
`Image` and also failed the fastboot return per the user's report, so only a
no-late-return claim is made for it because no marker fetch ran. The failure
is now superseded by the entry-WDT results below: compression and layout are
excluded, and the absent RAM markers were cleared along the failing manual
BROM/DA recovery path, so they were not proof that `primary_entry` was
unreached. See the correction in `experiments/phase-04/notes.md`
(entry-WDT delayed-reset runs) and section 11.8 of
`experiments/phase-04/lk-kernel-handover-research.md`. Hardware flashing is
paused pending the actual UFBL/LK binary analysis in
`experiments/phase-04/lk-kernel-handover-research.md`. The Phase 4 hardware
gate stays open and syscon remains unvalidated.
Details: `experiments/phase-04/notes.md`.

Entry-WDT delayed-reset runs, 2026-11-15: two matched images, each carrying
the identical `primary_entry` marker stores followed by a 5-second busy-wait
and a TOPRGU reset, per section 11.8 of
`experiments/phase-04/lk-kernel-handover-research.md`. The no-syscon control
(`boot-lidar-no-syscon-entry-wdt.img`, sha256
`969a06f7358f51110cbd73b6b7d52cc0031bacddbd69cc19b6ef578192d6873f`) returned
to fastboot after the user released the Action button at initial boot and
held it again about one second later; the shell `SECONDS` counter was bogus
in that session, so no control-run timing is claimed. The syscon image
(`boot-lidar-syscon-entry-wdt.img`, sha256
`2959155a566141bac917e4afd676751ed5cd06773c21826de1c534f0e04a1e5e`) used the
same procedure and returned to fastboot, measured about 8 seconds after the
reboot. Because both runs use the identical marker + 5-second
`primary_entry` TOPRGU reset and the reset is the reachability signal,
`primary_entry` executed in the syscon build; the prior absent RAM markers
were cleared along the failing manual BROM/DA recovery path and are not
no-entry proof. The UFBL decompressed-content audit is unchanged: it checks
neither the decompressed image length nor `kernel_addr` content
(research sections 11.3-11.4), so compression, boot-image layout and
the handover itself are excluded as causes. The "fault is after
`primary_entry`" scoping is itself superseded by the consolidated
delayed-WDT bisect below: the kernel reaches every ordinary initcall
level, so the original no-return is confined to the LibreEcho final
marker/reset diagnostic or work after the ordinary initcalls. Current device state: `boot_a` holds the syscon entry-WDT image
(`2959155a...`), the expdb LK stage remains the mapped peek/fetch stage
(sha256 `1b3cd36d...`), and the device is back in fastboot. Next step: a
delayed TOPRGU reset at the top of `rest_init`, before
`rcu_scheduler_starting` / `user_mode_thread`, to separate early setup from
driver and late init; the existing `CONFIG_LIBREECHO_ENTRY_WDT_RESET` gate at
`primary_entry` is proven in both builds, and the `rest_init` probe reuses
the same delayed-reset mechanism under a separate config, preserving default
behavior with all diagnostic configs off. The Phase 4 hardware gate stays
open; syscon runtime is validated only as far as `primary_entry` plus the
delayed reset, and the post-entry stall remains unlocated.
Details: `experiments/phase-04/notes.md`.

Delayed-WDT initcall bisect, 2026-11-15 (consolidated): the `rest_init`
and initcall probes ran with the proven five-second delayed-TOPRGU-reset
mechanism, so the fastboot return after the delay is the reachability
signal. Probes are gated by `CONFIG_LIBREECHO_REST_INIT_WDT_RESET`
(default n, reset at the top of `rest_init`),
`CONFIG_LIBREECHO_INITCALL_WDT_RESET` (default -1, reset after a
selected level; -2 is before level 0, 0..7 after pure, core, postcore,
arch, subsys, fs, device and late) and
`CONFIG_LIBREECHO_INITCALL_ITEM_WDT_RESET` (default -1, reset before a
selected zero-based late-level item). All diagnostic configs are off by
default and were off in every production-relevant build.

Results (control = no `CONFIG_MFD_SYSCON`, syscon =
`CONFIG_MFD_SYSCON=y`; time from reboot to a fastboot device):

| Probe | Control | Syscon |
| --- | --- | --- |
| `rest_init` | `8a56b4c8`, 22 s | `3059546b`, 27 s |
| before level 0 (`-2`) | `24de29ab`, 9 s | `faa346f6`, 8 s |
| after arch (level 3) | `369c6cf9`, 27 s | `e7362313`, 9 s |
| after fs (level 5) | not run | `407899dd`, 9 s |
| after device (level 6) | not run | `9b45b492`, 9 s |
| after late (level 7) | not run | `517cf844`, 9 s |

Late-level item probes in the syscon build all returned to fastboot:
item 14 (first run timed out; invalid because the user reported a
possible Action-button mistake, retry after BROM recovery with
`enter_fastboot.py` returned in 9 s), item 21 (`9ff4390b`, 9 s), item 25
(`eb48c29d`, 9 s), item 27 (`6877be3b`, 9 s) and item 28
(`026e9fb1`, 8 s). Each item probe fires before its item runs, so the
item 28 return proves late items 0 through 27 returned, and the
after-late-level return (`517cf844`) proves the whole late level,
including all 29 ordinary items and `of_platform_sync_state`, completes
when the final `libreecho_lateinit_fastboot` diagnostic registration is
suppressed.

Conclusion: the kernel in the syscon build reaches `rest_init`, starts
`do_initcalls()` and completes every ordinary initcall level 0 through
7. The original no-return behavior is therefore confined to the
LibreEcho final marker/reset diagnostic itself or to work after the
ordinary initcalls finish. No claim follows that the product syscon
change is at fault. Current device state: `boot_a` holds the
after-late-level syscon image (`517cf844`), expdb holds the mapped
peek/fetch stage (sha256 `1b3cd36d...`), and the device is in
fastboot. Next test: a clean syscon build with every diagnostic config
off (all four probe configs at their defaults) and normal MUSB, booting
toward Android with the Action button released.
Details: `experiments/phase-04/notes.md`.

Clean-build exec-boundary update, 2026-11-15: the clean syscon build
(fresh defconfig, `CONFIG_MFD_SYSCON=y`, normal MUSB, all diagnostic
configs off, stock ramdisk; image sha256
`3da28ee219dc27d66c5d459bc0d8360808d9cfa12e8affcf2ed734070308fc2c`)
was flashed with the Action button released; `adb wait-for-device`
timed out at 120 seconds with no USB interface. A pre-userspace probe
(image sha256
`e490d27bd29cef18ca45c10c147a7b4dc077b111b45e0ac1279c648763ae6843`)
resets after `do_sysctl_args()` and before `run_init_process()`; its
first attempt was invalid, and the retry after BROM recovery returned
to fastboot 9 seconds after the reboot. This proves the full kernel
init path, including async probing, the rootfs mount and
`free_initmem`, reaches the exec boundary in `kernel_init`. A clean
diagnostic-adb image (sha256
`d8fa7c7756f2be3980e49c45c8b753ee6bbf5bcd696e46e2b7919e2dde24488f`,
same clean kernel `2e58e739...`, only `init.rc` and `default.prop`
modified, pack verify OK) also timed out at 120 seconds with no USB.
An early pack failure (`adb: not found`) happened before any flash and
is host tooling, not a device result. The pending exec-success probe
(image sha256
`cf22ae65fb93da3fb1637a738c88d98a51f2a2a937a03a741e4755ffb3ad8efb`)
resets into fastboot only if `run_init_process('/init')` returns 0; it
carries the diagnostic ramdisk and pack verify passed. Its first
hardware attempt was invalid (missed Action-button state) and the retry
was stopped by a user tool denial, so no exec-success result exists
yet. Current device state: fastboot; `boot_a` holds the
pending `cf22ae65...` image from the first attempt; expdb holds the
mapped peek/fetch stage (sha256 `1b3cd36d...`); `boot_b` is
untouched. The clean Android gate remains open. Next step: a
user-approved retry of the same `cf22ae65...` image. A fastboot return
proves `/init` exec success and points the failure at Android or ADB;
a timeout requires a valid procedure before any conclusion.
Details: `experiments/phase-04/notes.md`.

Exec-success result, 2026-11-15: the user approved the retry and the
same `cf22ae65...` image was flashed with the Action button released;
the device returned to fastboot 9 seconds after the reboot. The probe
resets only if `run_init_process('/init')` returns 0, so the return
proves the ARM32 `/init` exec succeeded. The remaining failure is in
Android init or ADB after the exec. A fastboot ramoops fetch after the
exec success found no `DBGC` record at offset `0x40000` (random
pattern), so no kernel console inference follows. Current device
state: `boot_a` holds `cf22ae65...`, `boot_b` is untouched, and the
device is in fastboot. The Android full-boot gate remains open. Next
step, build only: a clean syscon kernel with `CONFIG_USB_G_SERIAL=y`
and no diagnostic configs, to separate kernel UDC behavior from
Android `adbd`.
Details: `experiments/phase-04/notes.md`.

Syscon g_serial result, 2026-11-15: the syscon g_serial image (sha256
`98f5369ee48cad3066f253bf07b9f42d9fce625de49ec1c0d1ef17fa5ec88e12`,
stock ramdisk, pack verify OK) was flashed with the Action button
released. `/dev/ttyACM0` appeared on the host, but `lsusb` reports
`0e8d:2000` MediaTek preloader, not `0525:a4a7` Linux g_serial, so no
USB success follows and the device returned to preloader. BROM
recovery restored fastboot. The capture `ramoops-syscon-serial.bin`
contains no `DBGC`, `LIBREECHO` or `musb` text, so no kernel log
inference follows. The DTS confirms `dr_mode = "peripheral"`. Current
device state: `boot_a` holds the g_serial image (`98f5369...`) and the
device is in fastboot. Next step: a bounded g_serial image plus a
pre-userspace WDT probe, with a udev monitor on the host.
Details: `experiments/phase-04/notes.md`.

Bounded g_serial WDT result, 2026-11-15: image sha256
`4ab15d710f9e94f90ab1e9c99e07d4c66ba5862d19d5ef9c606e4c4deac56ba3`
(`CONFIG_USB_G_SERIAL=y` plus the existing pre-exec userspace WDT)
returned to fastboot 9 seconds after the reboot in both of two runs,
proving device init including `gserial_init` completed. The first
run's udev monitor was invalid (no events even for a known fastboot
device). The second run's direct PyUSB poll saw an empty list at
first, only `(0e8d, 2000)` at 11.703 s, an empty list again at
14.280 s, and never `0525:a4a7`. The kernel therefore never enumerates
the g_serial gadget despite completed initcalls; no specific MUSB
cause is inferred yet. Correction, 2026-11-15:
`drivers/usb/gadget/legacy/serial.c` lines 35-36 define `0525:a4a6`,
not `a4a7`, so the poll watched the wrong product ID and this
observation is invalid as a g_serial negative; the status proof
(device init including `gserial_init` completed) remains valid. Current device state: `boot_a` holds
`4ab15d...` and the device is in fastboot. Next step: a
`MusbStatusProbe` at the same bounded pre-userspace marker with
timings 5 s (after `mtk_musb_probe` success), 10 s (probe entered, not
successful) and 15 s (probe never entered).
Details: `experiments/phase-04/notes.md`.

MUSB glue status result, 2026-11-15: image sha256
`a60645d66032731edd412d07c909bd4b33877047caaa0f6c2c1161f626d60e77`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and `mtk_musb_probe` reached status 2 (probe success). The
glue-layer success covers only `platform_device_register_full()` of
the `musb-hdrc` child; it does not show that the generic
`musb_init_controller()` or the gadget side succeeded. Current device
state: `boot_a` holds `a60645d...` and the device is in fastboot.
Next step: a core status probe that resets at `musb_init_controller()`'s
final return 0 with the same 5/10/15-second delays.
Details: `experiments/phase-04/notes.md`.

MUSB core status result, 2026-11-15: image sha256
`0c75851f90021d9cebb8bc200ede623ed8f5c71165e164337ac9cd03e5cfba6c`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and the generic `musb_init_controller()` reached status 2: final
return 0 after `musb_gadget_setup()` and `is_initialized`. The USB
failure is therefore after core and gadget registration. Current
device state: `boot_a` holds `0c75851...` and the device is in
fastboot. Next step: a gadget status probe mapping start entry to a
15-second delay, success to 10 seconds, pullup-on to 5 seconds, and
never reaching any of them to 20 seconds.
Details: `experiments/phase-04/notes.md`.

MUSB gadget status result, 2026-11-15: image sha256
`b834cbe106a48a2dc0348f265880cfde3c56939d25d082d01f39e3c3e88edc1e`
returned to fastboot 9 seconds after the reboot, so the 5-second reset
fired and the probe reached status 3: `musb_gadget_pullup(is_on=1)`.
The g_serial gadget started and requested D+ pullup. Current device
state: `boot_a` holds `b834cbe...` and the device is in fastboot.
Next step: an actual `musb_pullup` write probe with a 9-second delay
after the SOFTCONN readback is set, 14 seconds when the write's
readback is clear, and 19 seconds when no actual write happened before
the fallback.
Details: `experiments/phase-04/notes.md`.

MUSB actual pullup result, 2026-11-15: image sha256
`409dd4be6ffe8bff2415e1603acdfb5f7ba6e1af0148973772f674ab652486d8`
returned to fastboot 8 seconds after the reboot, so the 9-second
timing class fired: the actual `musb_pullup(is_on)` ran and the
`MUSB_POWER_SOFTCONN` readback was set. The controller D+ request is
confirmed. Current device state: `boot_a` holds `409dd4b...` and the
device is in fastboot. Next step: a DEVCTL VBUS status probe with a
9-second delay when VBUS reads full, 14 seconds when partial, 19
seconds when zero, and 24 seconds when no actual pullup ran.
Details: `experiments/phase-04/notes.md`.

DEVCTL VBUS result, 2026-11-15: image sha256
`655a0a8677e65fa87008346bf49ed1c7bb2a05673fc2700d21e8dabc07c675c2`
returned to fastboot 9 seconds after the reboot, so the actual pullup
ran with the DEVCTL VBUS field reading full (`0x18`). Repeating the
same image under a direct PyUSB poll still never saw `0525:a4a7`; only
`0e8d:2000` appeared at 10.341 s and disappeared at 13.020 s. SOFTCONN
is set and VBUS reads full, but the host never enumerates the gadget;
the next target is PHY power, mode and D+ signaling. Correction,
2026-11-15: the poll watched the wrong product ID (`0525:a4a6` is the
defined g_serial ID), so this observation is invalid as a g_serial
negative; the DEVCTL VBUS-full status proof remains valid. A
`MusbPhyResearch` comparison of the vendor and upstream MT8167 PHY
setup against MT8163 recovery is running. Current device state:
`boot_a` holds `655a0a...` and the device is in fastboot.
Details: `experiments/phase-04/notes.md`.

PHY research conclusion, 2026-11-15: do not use the MT8163 glue or
recovery for this target. The MT8167/MT8516 DT uses one register
region and 3 clocks with the separate t-phy driver; the MT8163 needs a
second register region and 4 clocks. Source comparison of the
device-mode VBUS session fix: the vendor
`LibreEcho-Platform/drivers/misc/mediatek/usb20/mt8163/usb20_phy.c`
(lines 343-398) uses the same V1 layout, waits 800 us, then writes
`0x6c = 0x2e` and `0x6d = 0x3e`, forcing IDDIG, AVALID, BVALID,
VBUSVALID and SESSEND; mainline `drivers/phy/mediatek/phy-mtk-tphy.c`
(lines 565-588) forces only IDDIG. A minimal `mt8516-tphy` pdata quirk
implementing the full device force is building in `Mt8516PhyFix`, as a
bounded g_serial image plus the pre-userspace WDT. The IDDIG pinmux
stays a second possible fix only if needed. No runtime fix claim is
made yet.
Details: `experiments/phase-04/notes.md`.

PHY fix run, 2026-11-15: the `Mt8516PhyFix` image (sha256
`cf87e11a62d18db65c5cd72159be573be3cf2e233f040d0e7da1c585e52c7f48`)
was rerun with the correct `0525:a4a6` g_serial and `0bb4:0c01`
fastboot IDs under a PyUSB poll. Timeline: fastboot `0bb4` initial at
0.021 s, gone at 10.421 s; preloader `0e8d` at 12.269 s, gone at
14.997 s; fastboot again at 18.086 s. `0525:a4a6` never appeared. This
is a valid negative for the PHY fix only; it does not retroactively
establish the baseline no-serial result. Current device state: `boot_a`
holds `cf87e11...` and the device is in fastboot. Next step: a BDEVICE
probe on the PHY-fixed source.
Details: `experiments/phase-04/notes.md`.

BDEVICE probe result, 2026-11-15: image sha256
`47fd33d77ca646e93756c5af8bff5c61a6414593c985b9eea324461bf9ac8426`
returned to fastboot 9 seconds after the reboot; BDEVICE is set to
peripheral mode at the actual pullup on the PHY-fixed source. The host
journal shows no electrical connect between the fastboot disconnect
and the preloader, so no descriptor exchange happened. Remaining
vendor versus mainline analog gaps: `usb20_phy.c` lines 343-398 set
SQTH6 while mainline sets 2; `VRT_SEL7` and `TERM_SEL7` are absent
from mainline; the `DP100K` bit 18 set with bits 17:16 clear is
absent. `Mt8516PhyFix` is adding these mt8516-only analog settings and
rebuilding the bounded g_serial image. Current device state: `boot_a`
holds `47fd33d...` and the device is in fastboot.
Details: `experiments/phase-04/notes.md`.
