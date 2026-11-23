# No-UART Phase 4 research: the existing boot chain as a RAM observability channel

Date: 2026-11-15. Scope: no code changes, no device commands, no hardware changes.
This note answers whether the pinned boot chain or a small early-entry change can
replace a serial console for Phase 4. Physical UART is excluded by requirement and is
not evaluated as an option.

## Bottom line

The boot chain does not contain a hidden no-UART console. Its useful capability is
narrower and better: while Kaeru fastboot is running, `oem mem read` reads arbitrary
32-bit physical memory, up to `0x400` bytes per command, and `oem mem write` writes one
32-bit word. The missing piece is a reliable way to get back to fastboot after kernel
code has run. That piece is already proven on this unit: stage 2 sets WDT_NONRST bit 2
at `0x10007024`, then performs a watchdog reset, and LK selects fastboot.

The current self-reset control does not reproduce that sequence. It writes the marker
and then writes only `WDT_SWRST`; it does not set the WDT mode for an external reset and
does not set the fastboot flag. Its no-detection result is therefore confounded: the
device may not have reset at all, may have reset without selecting fastboot, or may have
reset and lost DRAM. The first experiment below removes that ambiguity with two
additional register writes and uses only mechanisms already hardware-proven by
phase-03.

The corrected `pstore_blk` run also changes the priority. With the real `swdl` GUID,
`best_effort`, and 64 KiB zones, the partition still read all zero. GUID and zone
configuration are no longer plausible explanations, so the next pstore attempt must
prove that kernel late init and the MMC path were reached. A direct RAM write from late
init, followed by a fastboot read, tests that without involving pstore or the eMMC
partition table.

## Evidence classes

- **Proven**: observed on this unit, or directly readable in the cited source.
- **Inferred**: follows from source and platform behavior but was not observed here.
- **Unknown**: no primary source found.

## 1. What the boot chain can actually do (question 1)

### 1.1 Runtime physical memory access

Kaeru registers a custom fastboot command `oem mem`:

- Read: `oem mem read <hex-addr> [hex-len]`. Default length is `0x100`; maximum is
  `0x400`; output is a hexdump sent through `fastboot_info`.
  `repos/kaeru/lib/fastboot/cmd_mem.c:9-10`, `:42-51`, `:74-90`.
- Write: `oem mem write <hex-addr> <hex-value>`. The address must be word-aligned; the
  value is one 32-bit word; the command reads the word back and prints it.
  `repos/kaeru/lib/fastboot/cmd_mem.c:92-110`.
- The address argument may also be a named region if `mem_region_find` is compiled in:
  `repos/kaeru/lib/fastboot/cmd_mem.c:56-59`. The names registered on this build were
  not enumerated. **Unknown** whether `ramoops`, `ram_console`, or `swdl` are names.

This is real arbitrary physical access, but only while LK/fastboot owns the CPU. It is
not a kernel-time debugger.

### 1.2 Custom ARM64 execution

Custom ARM64 execution exists only on the BROM side, in the pinned boot-chain stages:

- stage 1 command `0x4000`: receive data to an arbitrary address; command `0x4001`:
  jump to an arbitrary address. `reference/echo-plus-2-bootchain-v0.2.1/brom-payload/stage1.c:55-75`.
- stage 1 also has `0x3000` reset and `0x3001` watchdog kick.
  `.../stage1.c:77-92`.
- stage 2 command `0x5000`: read arbitrary address and length back to the host.
  `.../stage2.c:257-262`.
- stage 2 command `0x3000`: `RESTART=0x1971`, `MODE=0x22000014`, `SWRST=0x1209`.
  `.../stage2.c:264-273`.
- stage 2 command `0x6000`: `*(0x10007024) |= (1 << 2)`, the fastboot flag.
  `.../stage2.c:281-286`.

Kaeru itself has no "execute this ARM64 blob and return" command. It offers only the
fixed fastboot commands listed in 1.3.

### 1.3 Reboot modes and other fastboot extensions

Kaeru's own command strings include `oem kaeru-version`, `oem mem`, `oem partitions`,
`oem reboot-recovery`, `oem append-cmdline`, `oem reboot-wmfk`, `oem flags`, and
`oem idme` (strings in the pinned Kaeru binary; board support at
`repos/kaeru/board/amazon/board-mt8516-common.c:478` registers the custom reboot).
The stock `reboot`, `reboot-bootloader`, and `set_active` registration callers are
NOPed in this board port, so `reboot-bootloader` is not a route to BROM:
`repos/kaeru/board/amazon/board-mt8516-common.c:514-570`.
This matches the observed "set_active/print-bcb unsupported" behavior.

### 1.4 What the unlock kit is not

`reference/echo-plus-2-bootchain-v0.2.1` installs Koboreru in `tee1` and a Lidar Kaeru
in `expdb`; its README states that BROM is still a mode the user must enter, and the kit
does not add a new BROM entry path:
`reference/echo-plus-2-bootchain-v0.2.1/README.md:9-10`.
The release supplies the Kaeru image, not a BootROM access path. It helps after fastboot is
reached; it does not solve the current BROM-entry problem by itself.

## 2. Can it read RAM without a warm reset, or return to LK? (question 2)

- **While fastboot runs: yes.** `oem mem read` reads any physical address in 1 KiB
  chunks. This is the only no-UART RAM read proven on this unit while the device is
  already running. BROM `peek` also reads RAM, but only after a cold power cycle, which
  invalidates the contents being tested.
- **While Linux runs: no.** Fastboot is an LK application. Once LK jumps to the kernel,
  its USB device stack and command loop are gone. With no ADB or USB network interface,
  the host has no path into the running kernel. `oem mem` is not resident.
- **Return to LK from custom code: no existing API.** stage 1/2 `jump` is one-way
  (`stage1.c:70-75`); there is no saved LK context, stack, or return trampoline. Kaeru
  has no exec-and-return command. Adding one would require new LK code plus a safe
  scratch region, and is not justified when a reset can be made to land in fastboot.
- A one-way reset into fastboot is the practical substitute. The fastboot flag and reset
  sequence already exist and are proven by phase-03 (`stage2.c:281-286`, then
  `stage2.c:264-273`; phase-03 status in `experiments/phase-03/FASTBOOT.md:113-118`).

## 3. Why BROM does not appear after a WDT reset with Action held (question 3)

BROM download mode is not selected by the Action button alone. On MediaTek, a
flag-triggered USB download request lives in `BOOT_MISC0` (also called `USBDL_FLAG`):

- Value: `(0x444C << 16) | ((timeout_seconds & 0x3fff) << 2) | 1`.
  `https://github.com/cyrozap/mediatek-lte-baseband-re/blob/master/SoC/common/doc/BROM-Notes.md`
  ("Decoding the BROM log", `[DL]` line).
- The flag must be protected from the watchdog by writing `MISC_LOCK_KEY=0xAD98` and
  `RST_CON=1` before the reset. The offsets depend on the SoC register block: cyrozap's
  MT8163 code uses `USBDL+0x20` and `+0x28`
  (`https://github.com/cyrozap/mediatek-lte-baseband-re/blob/master/SoC/common/usbdl.py:225-247`;
  same sequence in C at `.../demo/hello-aarch64/main.c:519-537`), while coreboot's
  MT8195 names separate registers at `SECURITY_AO+0x100` and `+0x108`
  (`https://github.com/coreboot/coreboot/blob/main/src/vendorcode/mediatek/mt8195/include/mt8195.h:142-154`).
  Do not copy one SoC's offsets to another without checking the local binary.
- mtkclient implements the same idea in `reset_to_brom`:
  `https://github.com/bkerler/mtkclient/blob/main/mtkclient/Library/mtk_preloader.py:454-482`.

A plain watchdog reset does not set that flag. Holding Action can affect the cold
power-on path: phase-03's physical sequence uses Action plus mains to catch BROM or
fastboot (`experiments/phase-03/FASTBOOT.md:15-35`), but a WDT reset is not a cold
power-on and does not replay the PMIC/strap sequence that cold BROM entry uses. That is
why the same button procedure that worked from a power cycle did not produce BROM after
the automatic reset.

The MT8167 `BOOT_MISC0`/`USBDL` address is **unknown**. mtkclient's chip configuration
has no MT8167 `misc_lock`, and cyrozap's table lists only MT8163 at `0x10202050`
(`usbdl.py:190-220`). Writing the MT8163 address on MT8167 would be a guess. Do not do
that without locating the address in a local MT8167 binary first.

## 4. What clears RAM, or blocks the pstore write? (question 4)

The current evidence does not prove that a proper WDT reset clears RAM. The marker test
that returned zeros was read through BROM after a power cycle
(`experiments/phase-04/notes.md:580-600`). A cold BROM entry necessarily removes power
from DRAM, so that zero result says nothing about a warm WDT reset. This is the main
reason to repeat the marker test with a reset that lands in fastboot.

Candidate causes, ranked:

1. **The reset path itself / DRAM reinitialization: most likely, still inferred.**
   Kaeru and the stage-2 code use `MODE=0x22000014`, i.e. key plus `EXTEN` plus
   `AUTO_RESTART`, then `SWRST=0x1209` (`repos/kaeru/drivers/wdt/mtk_wdt.c:3-14`;
   `stage2.c:264-273`). `EXTEN` asserts an external SoC reset, which is broader than a
   CPU-only reset. The next preloader then runs DRAM initialization again; public
   preloader code writes EMI/DRAMC registers during `init_dram2`
   (`https://github.com/andreya108/bindu-kernel-mediatek/blob/master/platform/mt6589/preloader/src/drivers/mt_emi.c`,
   `init_dram2`). Whether this particular MT8167 preloader retrains or clears DRAM is
   not established. **Unknown**, but the leading hypothesis.
2. **The kernel zeroing BSS or the page allocator: unlikely for `0x44400000`.**
   The custom DTS reserves `ram_console@44400000` and `ramoops@44410000` before
   `minirdump@444f0000`
   (`repos/LibreEcho-Linux/arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:39-79`;
   stock DTBs use `mediatek,pstore` / `mediatek,ram_console`). A reserved region should
   not be handed to the page allocator, and the kernel does not memset reserved memory.
   It does zero its own BSS, which is why `__log_buf` starts zero before any pstore
   write.
   LK is also unlikely to clear it: the reserved region lies outside LK's loaded image,
   and no LK source reviewed here performs a full-DRAM memset. This is inference, not a
   source proof for this build.
3. **Wrong physical mapping: possible for the pstore addresses, not for the marker.**
   The Phase 4 notes derive `__log_buf` physical `0x4085f388` from `System.map` by
   subtracting `_text` and adding the kernel physical base
   (`experiments/phase-04/notes.md:568-576`). That arithmetic depends on the true load
   address and page-offset relationship and was not independently validated. The
   marker at `0x44400000` does not have this problem: it is a direct physical address
   written by the stub.
4. **Reset hardware cutting DRAM power: unresolved.** A WDT `EXTEN` reset may or may
   not remove DRAM power/self-refresh on this PMIC. No public MT8167 schematic or BROM
   source was found.

The pstore backend has a separate failure mode that is now the stronger suspect. A
live corrected run on 2026-11-15 (reported by Main, with the device on A and MISC
unchanged) used the actual `swdl` GUID
`<PARTUUID_12>`. The earlier images had a typo or unrelated
GUID and a bad config. The corrected forced-panic image (SHA-256 prefix `9e59e1d8`)
used `best_effort` and 64 KiB zones and still left `swdl` all zero. This retires the
GUID/typo/config explanation. The remaining possibilities are that `pstore_blk` late
initialization was never reached, that the MMC/block path was unavailable at panic time,
or that the write never left cache. `PSTORE_BLK` depends on `PSTORE` plus `BLOCK`
(`https://github.com/torvalds/linux/blob/master/fs/pstore/Kconfig`), so any missing
block device or command-line opt-in produces exactly this silent zero result.

Do not spend another cycle on the PARTUUID or `swdl` GUID. The next pstore test should
either prove late init was reached (Experiment 2) or abandon `swdl` for a reserved-RAM
target that does not depend on MMC.

## 5. Ranked no-UART experiments

Ranking is by information gained per unit of risk. All device work still needs owner
approval. No experiment below writes MISC, BCB, `boot_b`, or user data.

### Experiment 1: marker persistence with a real fastboot reset (highest value)

**Question answered:** does DRAM survive the WDT reset, and can a kernel-entry stub
return the device to Kaeru fastboot without BROM? This also unblocks every later RAM
read.

**Why it is new:** the existing control at
`experiments/phase-04/early_entry_ram_marker_reset.S`
(`experiments/phase-04/notes.md:606-610`) writes the marker, waits, then writes only
`SWRST`. It does not write `WDT_MODE`, and it does not set `WDT_NONRST` bit 2. Add the
two proven steps from stage 2:

```asm
// x1 = 0x10007000 (use a literal pool; the address is not a single MOV immediate)
ldr x1, =0x10007000

// 1. Kick, as stage2 0x3001 does.
ldr w0, =0x1971
str w0, [x1, #0x08]

// 2. Select fastboot on the next LK boot. Read-modify-write so other
//    WDT_NONRST bits are preserved. This is stage2 0x6000.
ldr w0, [x1, #0x24]
orr w0, w0, #(1 << 2)
str w0, [x1, #0x24]

// 3. Hardware reset with external reset + auto restart, as stage2 0x3000.
ldr w0, =0x22000014
str w0, [x1, #0x00]
ldr w0, =0x1209
str w0, [x1, #0x14]

4:  wfi
    b 4b
```

The marker write and the `dsb`/delay before reset stay as in the current source. Keep
the marker at `0x44400000`; do not move it into ramoops yet.

**Host steps after the device reboots:**

```sh
fastboot devices

# The local fastboot build needs its library path and does not support wait-for-device.
LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib \
  fastboot oem mem read 0x44400000 0x100
```

The expected hexdump contains `4c 49 42 52 45 45 43 48 4f 52 41 4d 4d 52 4b 21`
(`LIBREECHORAMMRK!`) at the start.

**Interpretation:**

- Marker present: DRAM survives the reset and fastboot works. The pstore zeros are a
  pstore/kernel/address problem, not a RAM-clearing problem. Proceed to Experiment 2.
- Marker absent but fastboot is present: the reset works, but DRAM is cleared before
  LK reads it. Stop pursuing pstore over reset; the remaining no-UART channels are USB
  gadget or display, both larger efforts.
- No fastboot at all: the flag or reset sequence is not taking effect on this build.
  Then read the marker through the next cold BROM session only as a negative control,
  not as evidence about warm reset.

**Risk:** low. Only `boot_a` changes, as in the existing control. If the flag is not
honored, the unit boots the same diagnostic again. It does not touch `boot_b`, MISC, or
the BCB.

### Experiment 2: prove the ramoops region is writable from kernel late init

**Question answered:** does the kernel reach late init, and is the reserved ramoops
region actually writable at `0x44410000`?

Add a built-in `late_initcall` that writes a 32-byte pattern (for example
`LIBREECHO-RAMOOPS-<build-id>`) to `0x44410000`, then executes the same stage-2 reset
sequence and fastboot flag as Experiment 1. Do not use pstore for this step; write the
bytes directly, then reset. The corrected `swdl` run still wrote zero, so this
experiment also distinguishes "late init never ran" from "the block path failed" without
another PARTUUID change.

Read back:

```sh
LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib \
  fastboot oem mem read 0x44410000 0x100
```

This is a stronger version of the existing forced-panic probe
(`experiments/phase-04/notes.md:546-567`) because it removes panic and pstore from the
variable set. If the pattern survives, the reserved region and reset path are good, and
pstore configuration becomes the only remaining suspect. If it does not survive, no
amount of pstore tuning will help.

**Risk:** low-medium. One kernel build and one `boot_a` flash.

### Experiment 3: capture the real kernel log through fastboot

**Prerequisites:** Experiment 1 and ideally Experiment 2 succeed.

Two sub-steps:

1. **Validate the kernel physical base before trusting `__log_buf`.** Read the ARM64
   Image header through fastboot:

   ```sh
   fastboot oem mem read 0x40080000 0x40
   ```

   The ARM64 Image magic `ARM\x64` (`41 52 4d 64`) should be at offset `0x38` if the
   image is loaded at `0x40080000`. If it is not, the `0x4085f388` derivation is wrong;
   locate the header first, then recompute `__log_buf`.

2. **Arm fastboot before entering the kernel.** Have the early stub set
   `WDT_NONRST` bit 2 and then continue into the kernel instead of resetting. Arrange a
   deterministic panic after the log has content (the existing forced
   `late_initcall_sync` panic is suitable), with `panic=5` on the command line. If the
   panic path performs a watchdog reset, LK will see the non-reset fastboot bit and
   return to fastboot. Then dump `__log_buf`.

   ```sh
   LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib \
     fastboot oem mem read 0x4085f388 0x400
   ```

   `oem mem read` is capped at `0x400`, so repeat with
   `0x4085f788`, `0x4085fb88`, and so on. The pstore console buffer is `0x10000` bytes,
   so a few chunks around the start are enough to see whether it was written.

**Unknown:** whether this kernel's panic path resets via the MTK watchdog. If it does
not, add an explicit WDT reset in the panic notifier rather than relying on
`emergency_restart`. This is new kernel code, but small and bounded.

**Risk:** medium (kernel build and flash). It is the only route that yields the actual
boot log without a console.

### Experiment 4: flag-triggered BROM entry from the stub

**Question answered:** can the device enter BROM download mode on a warm reset without
Action and without a power cycle?

This needs the MT8167 `BOOT_MISC0`/`USBDL` address, which is unknown. Do not use the
MT8163 address. First locate the address in a local MT8167 binary:

- The installed 2019 preloader and the pinned Kaeru LK are available in the Phase 3/4
  artifacts. Search their disassembly for the USBDL constant `0x444C` and the lock
  constant `0xAD98`, and for stores near `0x1001A000`/`0x10202050`-style blocks.
- If either binary contains a `0x444C << 16` immediate or an `0xAD98` write, the
  surrounding base register gives the MT8167 address.

Once found, the stub sequence is:

```asm
// usbdl = discovered MT8167 BOOT_MISC0 address
// flag = (0x444C << 16) | (60 << 2) | 1
// Use the lock/reset offsets that match the discovered register block,
// not the MT8163 values blindly.
str w_flag, [x_usbdl, #0x00]
ldr w0, =0xAD98
str w0, [x_usbdl, #LOCK_OFF]      // MISC_LOCK_KEY
ldr w0, =1
str w0, [x_usbdl, #RSTCON_OFF]    // RST_CON
str wzr, [x_usbdl, #LOCK_OFF]     // lock key back to 0
// then stage-2 WDT reset sequence
```

After reset, the host should see the MediaTek BROM device `0e8d:0003` and can use the
existing `mtk`/Kamakiri tooling. This is an independent channel that does not depend on
LK at all.

**Risk:** medium-high. A wrong address may hang the stub until the watchdog fires; the
device still resets. Do not attempt without disassembly evidence for the address.
**Value:** high if it works, because it restores BROM without a power cycle and makes
future recovery independent of LK.

### Experiment 5: use fastboot itself to test reset behavior

Once Experiment 1 reaches fastboot, the same test can be repeated interactively without
reflashing:

```sh
# Write a marker word, then trigger the same reset.
fastboot oem mem write 0x44400000 0x4c494252
fastboot oem mem write 0x10007024 0x00000004   # only if other bits are zero; prefer read first
fastboot oem mem write 0x10007000 0x22000014
fastboot oem mem write 0x10007014 0x00001209
```

The `oem mem write` command cannot read-modify-write, so read `0x10007024` first and
preserve its other bits. This is a low-cost confirmation of Experiment 1 and a way to
test whether the fastboot flag survives each reset variant. **Risk:** low, but a bad
WDT_MODE value can hang the unit until the watchdog fires.

## 6. Rejected or deferred routes

- **More blind pstore/ramoops reads.** Rejected until Experiment 1 separates "reset
  clears RAM" from "pstore never wrote." The existing reads were taken after a cold
  BROM entry, which invalidates them as warm-reset evidence
  (`experiments/phase-04/notes.md:560-600`).
- **`PSTORE_BLK` on `swdl` as a first-line channel.** Deferred. The corrected image
  used the real GUID, `best_effort`, and 64 KiB zones, and still wrote zero. Another
  config or PARTUUID change is not the next step. Revisit only after Experiment 2 shows
  whether late init and the MMC path were reached.
- **`fastboot set_active` / BCB writes.** Rejected. Kaeru NOPs the stock command
  registration (`board-mt8516-common.c:514-570`) and the raw `_a` path times out.
- **`reboot-bootloader` as a BROM route.** Rejected for the same reason.
- **Returning from custom code to the running LK.** Rejected. No API, no saved context,
  and no need while reset-to-fastboot works.
- **Guessing the MT8167 USBDL address from MT8163.** Rejected. The SoC families differ;
  a wrong write is a silent hang.
- **Early USB gadget / configfs / `f_fs` as the first fix.** Deferred. The current
  kernel does not enumerate USB at all, so gadget work would be layered on an unproven
  USB controller path. It becomes relevant only if Experiments 1-3 fail.
- **Physical UART.** Excluded by the requirement; not evaluated.

## 7. Unknowns that would change the plan

1. MT8167 `BOOT_MISC0`/`USBDL` address, and whether its BROM honors the `0x444C` flag.
2. Whether the MT8167 WDT `EXTEN` reset preserves DRAM contents, and whether the 2019
   preloader retrains or clears DRAM on every boot.
3. Whether `WDT_NONRST` bit 2 survives the exact reset used by the kernel-entry stub and
   is still read by this Kaeru build. Phase-03 proves it for the BROM stage-2 path; the
   kernel-entry path is the same register but a different reset origin.
4. The true kernel physical load address and therefore the real `__log_buf` physical
   address. Experiment 3 step 1 resolves this with the Image magic.
5. Whether this kernel's panic path performs a watchdog reset at all.
6. Whether Kaeru's `mem_region_find` exposes named `ramoops`/`ram_console` regions on
   this build.

## Sources

Local:

- `reference/echo-plus-2-bootchain-v0.2.1/README.md:1-35`: kit contents and BROM
  caveat.
- `reference/echo-plus-2-bootchain-v0.2.1/brom-payload/stage1.c:55-92`: write, jump,
  reset, kick.
- `reference/echo-plus-2-bootchain-v0.2.1/brom-payload/stage2.c:257-290`: read, reset,
  fastboot flag.
- `repos/kaeru/lib/fastboot/cmd_mem.c:1-116`: `oem mem` implementation.
- `repos/kaeru/board/amazon/board-mt8516-common.c:15-18,356-363,388-455,478,514-570`:
  WDT_NONRST bits, boot-mode selection, NOPed stock reboot registration.
- `repos/kaeru/drivers/wdt/mtk_wdt.c:3-14`: reset sequence.
- `experiments/phase-03/FASTBOOT.md:1-40,113-118`: proven stage-1/2 fastboot entry and
  physical sequence.
- `experiments/phase-04/notes.md:546-576,580-630`: panic probe, marker controls, and
  session end state.
- Live Phase 4 corrected `pstore_blk` run, 2026-11-15 (reported by Main): real `swdl`
  GUID `<PARTUUID_12>`, corrected forced-panic image SHA-256
  prefix `9e59e1d8`, `best_effort`, 64 KiB zones, `swdl` all zero, MISC unchanged.

External primary sources:

- cyrozap, BROM notes (USBDL flag encoding):
  <https://github.com/cyrozap/mediatek-lte-baseband-re/blob/master/SoC/common/doc/BROM-Notes.md>
- cyrozap, `usbdl.py` (flag + MISC_LOCK + RST_CON + WDT reset):
  <https://github.com/cyrozap/mediatek-lte-baseband-re/blob/master/SoC/common/usbdl.py>
- cyrozap, ARM64 demo with `usbdl` and `reset` commands:
  <https://github.com/cyrozap/mediatek-lte-baseband-re/blob/master/SoC/common/demo/hello-aarch64/main.c>
- mtkclient, `reset_to_brom`:
  <https://github.com/bkerler/mtkclient/blob/main/mtkclient/Library/mtk_preloader.py>
- coreboot MT8195 register names for `BOOT_MISC0`, `MISC_LOCK_KEY`, `RST_CON`,
  `USBDL_BIT_EN`, `USBDL_BROM`, `USBDL_TIMEOUT_MASK`:
  <https://github.com/coreboot/coreboot/blob/main/src/vendorcode/mediatek/mt8195/include/mt8195.h>
- MT6589 preloader DRAM initialization (`init_dram2`):
  <https://github.com/andreya108/bindu-kernel-mediatek/blob/master/platform/mt6589/preloader/src/drivers/mt_emi.c>
- Linux ramoops DT binding (record/console/pmsg sizes):
  <https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/reserved-memory/ramoops.yaml>
- Linux `PSTORE_BLK` Kconfig dependency:
  <https://github.com/torvalds/linux/blob/master/fs/pstore/Kconfig>
