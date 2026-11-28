# Kaeru Lidar fastboot, BCB and reboot map

Scope: `repos/kaeru` at local commit `0cbe64d` (`feat(lidar): add the fastboot fetch and peek diagnostics`),
the stock LK in `dumps/stock/lk_a.bin`, the recorded Phase 1 to 4 experiments, and
`repos/amonet-koboreru`. Read-only investigation; no hardware was touched.

## Bottom line

* The Lidar Kaeru port is thin: it forces the unlock predicate to 1, prints two lines, adds
  `oem mem`/`oem peek`/`oem partitions`/`fetch:`/`oem fetch-enable`, and defines two memory regions.
  It does **not** include Amazon's BCB code, AOSP bootloader-message code, key detection, a boot-mode
  policy, or a recovery policy. **Slot selection and fastboot entry remain entirely stock LK.**
* Stock LK's fastboot has `flash:`, `erase:`, `getvar:`, `download:`, `reboot`,
  `reboot-bootloader`, `continue`, `verify`, `dump`, `signature`, `set_active`,
  `oem reboot-recovery`, `oem append-cmdline`, `oem reboot-wmfk`, `oem relock`, `oem flags`,
  `flash:unlock`, `flash:tucert`, `flash:tucode`. There is **no `boot` command**; Kaeru rejects it
  (`unknown command`, hardware-observed).
* `misc[0:16] = FASTBOOT_PLEASE`, `misc[0:32] = bootonce-bootloader` and `misc[0:32] = boot-recovery`
  are **inert on this unit**. They are Kaeru/AOSP conventions compiled only under
  `CONFIG_BOOTLOADER_MESSAGE_SUPPORT`, which is off (`.config:215`), and Amazon BCB support is off
  too (`.config:214`). Stock LK contains none of those literals.
* The Amazon BCB at `misc+0x360` is real and stock LK reads it (Boot Ctrl strings,
  `androidboot.slot_suffix=%s`). The only recorded dump has **both slots marked successful**, so the
  recorded A to B move is explained by **priority** (B=15 > A=14), not by a tries-exhaustion fallback.
  No recorded evidence shows stock LK decrementing tries.
* There is no recovery partition and no `boot-recovery` handling. `oem reboot-recovery` is a stock
  command with no usable target on this GPT.
* The only *proven* buttonless route into Kaeru fastboot is the watchdog flag:
  set bit 2 of `0x10007024`, then `MODE=0x22000014` / `SWRST=0x1209` on `0x10007000`. It writes no
  eMMC, MISC or BCB.
* The Phase 4 research claim that `reboot`, `reboot-bootloader` and `set_active` are NOPed “in this
  board port” is **wrong for Lidar**: it cites `board-mt8516-common.c`, which the Lidar build does not
  compile (`board/amazon/Makefile:1,15`). On Lidar those stock registrations are intact.

---

## Q1. Fastboot commands, filters and limits

### Kaeru-added commands (Lidar build)

| Command | Implementation | Notes |
|---|---|---|
| `oem kaeru-version` | `lib/fastboot/cmd_version.c:25` | prints `kaeru-version: <ver>` |
| `oem mem read <addr> <len>` | `lib/fastboot/cmd_mem.c:116` | only `MEM_READ_MAX = 0x400` (`cmd_mem.c:12`); DRAM reads fault, see below |
| `oem mem write <addr> <value>` | same file | no read-modify-write |
| `oem peek <addr>` | `lib/fastboot/cmd_peek.c:54` | one aligned `READ32`, publishes the `peek` variable |
| `oem partitions` | `lib/fastboot/cmd_partitions.c:34` | lists MMC partitions |
| `fetch:<name> [off:len]` | `lib/fastboot/cmd_fetch.c:190` | `MAX_FETCH_SIZE = 0x100000`, `USB_CHUNK = 0xFC00` (`cmd_fetch.c:13-14`); name must be in `mem_regions` (`board/amazon/board-lidar.c:48-58`) |
| `oem fetch-enable` | `lib/fastboot/cmd_fetch.c:191` | publishes `max-fetch-size` and `partition-size:<name>` |
| `oem help` | `lib/fastboot/cmd_help.c:48` | **not compiled**: `# CONFIG_FASTBOOT_HELP_COMMAND is not set` (`.config:155`) |
| `oem env` | `lib/fastboot/cmd_env.c:130` | **not compiled**: `# CONFIG_ENVIRONMENT_SUPPORT is not set` (`.config:165`) |

The Lidar `.config` enables `CONFIG_FASTBOOT_MEM_COMMAND=y` and
`CONFIG_FASTBOOT_FETCH_COMMAND=y` (`.config:157-158`). `board-lidar.c` supplies the named regions
`ramoops` and `entryprobe` plus the stock `bootimg`/`ram`/`download` ranges
(`board/amazon/board-lidar.c:48-58`).

`getvar` is special: Kaeru registers a duplicate `getvar:` handler (`cmd_fetch.c:192`), but the
Phase 4 observation was that **stock LK's published-variable table served the host**, not Kaeru's
wrapper (`experiments/phase-04/notes.md:790-795`). The wrapper's own variables appear only after
`oem fetch-enable`.

### Stock LK commands kept on Lidar

From `experiments/phase-01/dtb/lk_strings.txt:3440-3600` and `lk_probe.txt:330-400`:

`getvar:`, `flash:`, `erase:`, `download:`, `reboot`, `reboot-bootloader`, `continue`, `verify`,
`dump`, `signature`, `set_active`, `oem relock`, `oem flags`, `oem reboot-recovery`,
`oem append-cmdline`, `oem reboot-wmfk`, `flash:unlock`, `flash:tucert`, `flash:tucode`.

* `max-download-size` is `0x8000000` (128 MiB), published by stock LK and recorded in
  `experiments/phase-04/fastboot-boot-research.md:133-135`.
* There is **no `boot` command**: the hardware test returned `FAILED (remote: 'unknown
  command')` and the device stayed in fastboot (`experiments/phase-04/notes.md:202-210`).
* `set_active` is registered by stock LK. It was not NOPed on Lidar, but no successful run is
  recorded; the Phase 4 text calling it unsupported is based on the MT8516 board, not Lidar.

### Partition allow/deny

Only one deny is recorded, for the preloader:

* `flash preloader is not permitted.` (`lk_strings.txt:3615`).

No general allow-list or per-slot deny-list string exists. The hardware run successfully wrote
`boot_a` (`experiments/phase-04/notes.md:211-220`), and Kaeru's unlock predicate makes
`unlock_status: true`. `boot0`/`boot1` names are present in LK, but no test or restriction is
recorded. Treat everything except `preloader` as flashable-but-unverified, not as policy.

### Fetch/peek caveat

`oem mem` is effectively unusable for DRAM: an `oem peek 44400000` read disconnected the device;
only mapped addresses work (`experiments/phase-04/notes.md:765-785`). `fetch ramoops` works because
`ramoops` is a mapped region in `board-lidar.c`. Do not plan a Phase 5 recovery path that reads
arbitrary DRAM through `oem mem`.

---

## Q2. How fastboot is entered

| Mechanism | Stock LK | Kaeru Lidar build | Verdict on this unit |
|---|---|---|---|
| Action key at power-on | yes, “fastboot keys triggered, enter fastboot” (`lk_strings.txt:3456`), stock key-detect strings at `lk_strings.txt:2809-2830`, `CONFIG_MTK_DETECT_KEY_ADDRESS=0x41E11734` in the Lidar defconfig | not used; `board_lidar.c` never calls `mtk_detect_key()` | **works**; the only observed manual entry (Action held, mains before USB: `PLAN.md:93`, `experiments/phase-03/FASTBOOT.md:24`) |
| `misc[0:16] = FASTBOOT_PLEASE` | no such literal or parser | `lib/recovery.c:50` maps it to `BOOTMODE_FASTBOOT`, but only with `CONFIG_BOOTLOADER_MESSAGE_SUPPORT`, which is off (`.config:215`) | **inert**; stock `misc.bin` contains no marker |
| `misc[0:32] = bootonce-bootloader` | no such literal | `lib/recovery.c:23` maps it to fastboot, same disabled config | **inert**; `libreecho_bootctl.c:363-372` writes it, so that write is wasted on Lidar |
| `misc[0:32] = boot-recovery` | no such literal | `lib/recovery.c:20` maps it to recovery, same disabled config | **inert** |
| expdb marker | not applicable | expdb is only the Kaeru payload store; `board_lidar.c` never reads a flag from it | **not a fastboot trigger** |
| Watchdog flag | stock LK sees `0x10007024` bit 2 and selects fastboot | inherited | **works, proven** (below) |

Kaeru's Lidar `board_early_init()` consists of a print, `FORCE_RETURN(0x41E0196C, 1)` and (per
commit message) the omitted-info-address change (`board/amazon/board-lidar.c:20-29`);
`board_late_init()` only prints (`board-lidar.c:27-29`). There is no `boot_mode_select()`, no
`parse_bootloader_messages()`, no `set_bootmode()`, no `mtk_detect_key()`.

`CONFIG_BOOTMODE_ADDRESS=0x0` (`.config:193`) makes Kaeru's boot-mode get/set a no-op fallback.

**Consequence for Phase 5:** a userspace `reboot bootloader` that writes
`bootonce-bootloader` into misc cannot work. Either use the watchdog flag, or hold Action. If a
software-requested fastboot is a requirement, it must be built on the WDT path.

---

## Q3. Stock LK and the Amazon BCB at `misc+0x360`

### What stock LK contains

`lk_strings.txt:2698-2706` (LK VA `0x27bcd`-`0x27d27`), duplicated in the preloader at
`boot0_strings.txt:1819-1827`:

```
Boot Ctrl - Magic                    : 0x%x
Boot Ctrl - Version                  : %d
Boot Ctrl - Recovery Tries Remaining : %d
Boot Ctrl - Slot 0 Priority          : %d
Boot Ctrl - Slot 0 Tries Remaining   : %d
Boot Ctrl - Slot 0 Successful Boot   : %d
Boot Ctrl - Slot 1 Priority          : %d
Boot Ctrl - Slot 1 Tries Remaining   : %d
Boot Ctrl - Slot 1 Successful Boot   : %d
```

plus `Alternate slot %d marked unbootable.` (`lk_strings.txt:965` region) and
`androidboot.slot_suffix=%s` (`lk_strings.txt:1445`). There is **no** string for
`boot-recovery`, `bootonce-bootloader`, `boot-fastboot`, `FASTBOOT_PLEASE`, `bootloader_message`,
or `command`/`status` BCB fields. Stock LK's only misc-related loader string is
`mboot_recovery_load_misc` (`lk_strings.txt:2953`), which stages the misc partition into memory for
the MTK recovery path; it is not an AOSP command reader.

So stock LK implements the **Amazon 7-byte BCB**, not the AOSP bootloader message. That matches the
Kaeru library definition even though Lidar does not compile it: magic `0x42424100`, offset `0x360`,
max version 1 (`include/lib/bcb_amzn/bcblib.h:23-25`), two 1-byte slot-metadata bitfields
(`priority:4`, `tries:3`, `success:1`, `bcblib.h:51-53`).

### Layout and the recorded bytes

```
misc+0x360: 00 41 42 42   magic 0x42424100 (little endian)
misc+0x364: 01            version 1
misc+0x365: 8e            slot 0: prio 14, tries 0, success 1
misc+0x366: 8f            slot 1: prio 15, tries 0, success 1
misc+0x367: 00
```

Source: the Phase 4 investigation dump (`experiments/phase-04/notes.md:470-500`). The `strings`/grep
probe on `dumps/stock/misc.bin` finds the magic at column 865, which is offset 0x360.

**Important correction:** because both slots have `success = 1`, the observed A to B change is a
**priority** decision (B 15 > A 14), not a “tries ran out, fall back” decision. The Phase 5
background sentence “LK fell back from slot A to slot B through the BCB after a failed boot” is not
supported by the recorded bytes. What is supported is: the stock LK honoured a changed BCB priority
and booted B.

### Decrement / success clearing

Not recorded. The strings prove the fields are read and the state is printed; they do not prove the
write-back policy. `bcblib.h:90-93` documents `bcblib_bcb_get_active_slot(bcb, decrement_tries,
try_other)`, i.e. the library has the operation, but Lidar does not compile or call it.

[INFERENCE] Stock LK follows the usual Amazon semantics visible in the sibling port: select highest
priority among slots with `tries > 0`, decrement the chosen slot's tries before boot, and let the OS
mark `success`. Do not rely on this for Phase 5 without a hardware A/B experiment.

### Does Kaeru override any of it?

No.

* `# CONFIG_AMZN_BCB_SUPPORT is not set` (`.config:214`).
* `lib-$(CONFIG_AMZN_BCB_SUPPORT) += ... bcblib.o ...` is therefore not built
  (`lib/Makefile`, bcblib line).
* `board-lidar.c` has no `get_active_slot` patch, no `get_boot_part` hook, no `load_bcb()`, no BCB
  initialisation. Those live in `board-mt8163-common.c:379-422` and `board-mt8516-common.c:90-122`,
  neither of which the Lidar build links (`board/amazon/Makefile:15` links only `board-lidar.o`).
* `androidboot.slot_suffix` comes from stock LK. Observed `_a` on every recorded boot
  (`experiments/phase-04/hw-20261117-lk-slot-source/acm-diagnostics.log:19`). No `_b` observation
  exists, though the stock format string takes `%s`.

---

## Q4. Recovery

* The GPT has no `recovery` partition (`experiments/phase-05/boot-shape-decision.md:24-40`).
* Stock LK has idme-driven recovery: `read idme_boot_mode`, then
  `g_boot_mode = RECOVERY_BOOT (IDME_BOOTMODE_RECOVERY)` (`lk_strings.txt:2808-280c`), and it has
  the Android recovery-image loader (`mboot_android_load_recoveryimg_hdr`,
  `lk_strings.txt:295e0-29872`). It does **not** parse `boot-recovery` from misc (no literal), and
  without a recovery partition the loader has no target.
* `oem reboot-recovery` exists in stock LK (`lk_strings.txt:3516`) but is unverified and has no
  partition to boot. Treat it as a no-op or failure, not a recovery path.
* Kaeru's own recovery policy (`lib/recovery.c`) is not compiled on Lidar, and `board-lidar.c` has no
  `get_boot_part_hook` (the hook is in `board-mt8516-common.c:500-512`). So Kaeru neither adds nor
  redirects recovery on this unit.

**Phase 5 implication:** TWRP-less install/recovery cannot use an LK recovery mode. It must be an
initramfs/userspace function of the flashed `boot_a`/`boot_b` image, or a temporary boot image
flashed to a slot, because the stock LK cannot chainload a third image.

---

## Q5. Reboot paths from Linux without the button

### Proven: watchdog fastboot flag

From `experiments/phase-04/no-uart-research.md:67-69, 203-250`, `experiments/phase-04/notes.md:690-735`
and the late-init driver experiment:

1. kick the watchdog: write `0x1971` to `0x10007008`;
2. set bit 2 of `0x10007024` (the `FASTBOOT` warm-reset flag);
3. write `MODE = 0x22000014` at `0x10007000` (key + `EXTEN` + `AUTO_RESTART`);
4. write `SWRST = 0x1209` at `0x10007014`.

Stock LK then selects fastboot (`no-uart-research.md:15`). The sequence “does not write eMMC, MISC,
BCB, or any partition” (`experiments/phase-04/notes.md:717`; also
`no-uart-research.md:203`). It was proven end-to-end: a full kernel driver performing exactly this
sequence at `late_initcall_sync` re-enumerated as `LIDAR` fastboot about 20 s after reboot, with no
other code setting the reset (`experiments/phase-04/notes.md:700-728`).

The existing driver is an out-of-tree build, `drivers/misc/libreecho_lateinit_fastboot.c` (Kconfig
`CONFIG_LIBREECHO_LATEINIT_FASTBOOT`, default n; not present in the current `LibreEcho-Linux`
tree). Phase 5 must port this into the shipped kernel, not assume it is already there.

### Not a route: `reboot bootloader` / `bootonce-bootloader`

* AOSP `reboot bootloader` writes `bootonce-bootloader` to `misc[0:32]`. Stock Lidar LK has no such
  literal and no bootloader-message parser; Kaeru has the parser but compiles it out
  (`.config:215`). Result: an ordinary reset into the normal boot slot, no fastboot.
* The Kaeru image installed on the unit wrote `bootonce-bootloader` via its OTA tool
  (`tools/mt8163-arm32/ota/libreecho_bootctl.c:363-372`). That is a dead assumption for Lidar and
  should be removed or guarded in Phase 5.

### `fastboot reboot-bootloader`

* The command string is stock LK (`lk_strings.txt:3511`), and Lidar does **not** NOP its
  registration.
* The stock LK also contains `[FASTBOOT] reboot to boot loader` (`lk_strings.txt:28b54`), which
  suggests a dedicated boot-mode path. No misc write string is tied to it, and no hardware test was
  recorded.
* [INFERENCE] It most likely sets an in-RAM boot mode and performs a warm SoC reset, not the WDT
  flag. If so it would return to the same slot, not guaranteed fastboot. **Unverified; do not design
  on it.**
* The Phase 4 conclusion (`no-uart-research.md:81-82, 408`) that `reboot-bootloader` is a rejected
  BROM route is still correct in outcome, but its stated reason (NOPed registration) is wrong for
  Lidar. The real reasons: no BROM entry is provided, and no fastboot re-entry is proven.

---

## What this means for Phase 5 planning

1. **Fastboot entry**: ship the watchdog-flag reset as the software route. Keep Action-held
   power-on as the manual route. Do not spend time on misc markers unless you also enable
   `CONFIG_BOOTLOADER_MESSAGE_SUPPORT` and verify stock LK does not clear/ignore misc[0:32], and
   even then, stock LK owns the decision to read it, not Kaeru.
2. **Slot selection**: stock LK is authoritative. `libreecho-bootctl`'s BCB writer is still the
   right interface (offset 0x360, 7 bytes, magic/version), but its **bootloader-message writes at
   misc[0:32] are dead code on Lidar** and should be removed. Any “mark slot successful” logic must
   match the observed bitfield (success bit 7) and the priority semantics.
3. **Recovery**: there is no LK recovery. A development recovery is a boot image in a slot; a
   production installer must run from the booted initramfs/userspace.
4. **Install**: `fastboot flash boot_a|boot_b` works and is the only proven write path. The host
   must not rely on `fastboot boot`, `set_active`, or `reboot-bootloader`. After a flash, a normal
   `reboot` boots the new image; to re-enter fastboot, use the WDT flag.
5. **Diagnostics**: `fetch` only reads named mapped regions; `oem peek` only reads mapped LK/DRAM
   addresses. `oem mem` is not a general RAM reader.

## Verification status

* Read: Kaeru source/config/Makefiles, stock LK string tables, Phase 1 to 4 notes, Phase 5 decision
  doc, Platform bootctl writer.
* Grep only against `dumps/stock/lk_a.bin` and `dumps/stock/misc.bin`; no new disassembly.
* Nothing was built, flashed, or run against hardware. Hardware claims are cited from the Phase 3/4
  records.
