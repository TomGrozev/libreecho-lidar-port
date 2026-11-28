# Stock `cmd_boot` in the Lidar LK: read-only disassembly

Date: 2026-11-17. Scope: read-only analysis of
`dumps/20261110-lidar-readback/lk_a.bin`
(sha256 `e1f541d1a793ca98d2d995f875d227998bd5ac6368e44d814f63a6515fff9d5c`,
1048576 bytes; identical to `dumps/stock/lk_a.bin`). No code changes, builds,
commits, flashes or hardware commands. Method: capstone 5.0.7, Thumb and ARM modes,
with a clobber-aware backward scan for `ldr rX,[pc,#imm]` / `add rX,pc` string
references.

Address mapping: `VA = 0x41DFFE00 + file_offset`, equivalently
`VA = 0x41E00000 + (file_offset - 0x200)`, as in
`experiments/phase-02/kaeru/addresses.md`.

## Bottom line

The string block that the plan attributed to a *present but unregistered* `cmd_boot`
is **orphaned `.rodata`**: **the stock `cmd_boot` body is not in this LK image.**
There is no address to register, so `fastboot_register("boot", addr, 1)` in
`board-lidar.c` cannot work: the address it would need does not exist. A karat-style
custom handler is the only option; it can reuse the stock handover function
`0x41E1AE6A`, whose LK address is stable.

Correction to the plan's offset: the format string is at file `0x2dc84` =
**VA `0x41E2DA84`**, not `0x41E2DC84` (the plan value is exactly `+0x200` too high,
a file-offset/VA mix-up).

## Q1. Address of stock `cmd_boot`: none exists

There is no xref of any kind to `cmd_boot,boot_hdr = NULL`
(VA `0x41E2DA84`) or to any of its sibling messages. Methods tried, all negative:

| search | result |
| --- | --- |
| Thumb `ldr rX,[pc,#imm]` + `add rX,pc`, clobber-aware lookback | 1155 string targets resolved, none in `0x41E2DA84..0x41E2DD97` |
| Thumb-2 `add.w rX, pc, #imm` | no target in the block |
| ARM (`A32`) `add/sub/adr rX, pc, #imm`, `ldr rX,[pc,#imm]` literal | no target in the block |
| `movw`/`movt` pair forming the string address | 93 pairs scanned, none |
| absolute 32-bit literal equal to the string VA (A32 `ldr =sym` pool) | zero occurrences in the whole image |
| any 32-bit word pointing into `0x41E2D900..0x41E2E400` | only 10, all the `FOS_FLAGS_*` name table at `0x41E337E8` |

The whole block `0x41E2DA84` .. `0x41E2DE4A`, which contains exactly the
boot-image messages a `cmd_boot` would print: the NULL-hdr line, the page-size
request, the four unsigned-overflow checks, `incomplete bootimage`, the kernel/
ramdisk address and overlap checks, `invalid ... overlap with the download image`,
`RECOVERY`, and the `Kernel Address: 0x%8X`, `Ramdisk Address:`, `Atag Address:`,
`Command: %s` header dump, has **no reference at all** (16 of 16 strings dead).
The immediately following block (`0x41E2DE4A` onward) is live and resolves from the
fastboot functions at `0x41E1D7xx`-`0x41E1E3xx`.

Positive control that the method works: every string of the *live* handover path
resolves, `[LK]jump to K64` (`0x41E2C4FA`, from `0x41E1AE32`),
`Do nothing now! wait for SMC done` (`0x41E2C510`, `0x41E1AE46`),
`Kernel size is bigger...` (`0x41E2C54A`, `0x41E1AE8E`-`0x41E1AEAA`),
`decompress kernel image fail!!!` (`0x41E2C6EB`, `0x41E1B17E`),
`Can't find device tree` (`0x41E2C732`, `0x41E1B204`),
`gunzip header is bigger...` (`0x41E2D50D`, `0x41E1CB1A`), and the fastboot getvar
strings `Done!!` (`0x41E2DA7D`, `0x41E1D6B6`) and `invisible on locked device.`
(`0x41E2DA61`, `0x41E1D6F6`).

Dead code with surviving `.rodata` is normal in this UFBL: the generic loader print
`mboot_android_load_bootimg_hdr, boot_hdr = NULL` (VA `0x41E2909F`) is likewise
unreferenced, while the *live* header loader at `0x41E10700` prints `part page addr
is 0x%ll...` (`0x41E290B0`, from `0x41E10770`) and `[%s] boot image header magic
error` (`0x41E29135`, from `0x41E107E6`). Amazon's UFBL carries a dead copy of the
generic `bootimg.c` text/data and a live implementation elsewhere.

**Consequence for the signature question:** there is no function to confirm
`(char *arg, void *data, unsigned sz)` against. The strings prove the *source* was
MTK `cmd_boot(arg, data, sz)` with `data` = the fastboot download buffer and
`sz` = its length, but the compiled body is absent (garbage-collected), so the
handler-ABI check cannot be made and the registration idea is void.

## Q2. What the stock handler did, and the live path to reuse

Because the body is absent, the end-to-end sequence can only be reconstructed from
the message block (inference) plus the live code it would have called (verified):

- Header from the download buffer; `page_size` must be non-zero, else
  `[FASTBOOT] Please specify the storage page-size in the boot header!`.
- Alignment arithmetic `page_size+kernel_actual(+ramdisk_actual)` and
  `kernel_size+ramdisk_size(+SCRATCH_ADDR)` with unsigned-overflow rejection, then
  `incomplete bootimage`.
- Address policy: kernel and ramdisk must lie in memory, must not overlap LK,
  must not overlap each other, and must not overlap the fastboot download image —
  exactly the `0x41E2DBF3..0x41E2DDC4` strings.
- `invisible on locked device.` (`0x41E2DA61`) is a **getvar** value, not a
  `cmd_boot` gate: its only reference is `0x41E1D6F6` inside the getvar scan
  (`0x41E1D670`-`0x41E1D708`). There is therefore **no lock/signature gate in the
  stock boot-image handler itself**, so Kaeru's unlock patch
  (`board-lidar.c` `UNLOCK_CHECK_FUNC_ADDR` = `0x41E0196C`) is not needed for a
  download-buffer boot; it stays needed only for the partition/storage paths that
  the unlock check guards.
- It ended in the same handover used by the normal `boot_a` path:
  `0x41E1AE6A` (the function documented in
  `experiments/phase-04/lk-kernel-handover-research.md` §11). Verified properties
  of `0x41E1AE6A`: `kernel_size <= 0x1000000` gate; `kernel_addr` 2 MiB-alignment
  check; backward FDT-magic scan from `0x45000000+kernel_size`; DTB copy; raw
  inflate to `kernel_addr` with `Z_STREAM_END` required; `/chosen` and `/memory`
  DTB updates; then `blx r5` with `r0`=DTB, `r1`=`[sp,#0x38]`, `r2`=DTB
  (`0x41E1BE6A`-`0x41E1BE70`). The scratch getter `0x41E110F4` returns
  `0x45000000`.
- `bootopt=` (`0x41E2C4CF`) has **no** xref: the 64-bit selection strings
  `exact`/`best`/`64Bit`/`32Bit` and `64 bit kernel can't boot at
  g_boot_hdr->kernel_addr=0x%08x` (`0x41E2C597`) are referenced, but the
  `bootopt=` keyword scan is in the dead generic copy. In the live path the
  kernel-bitness decision is therefore **not** made by parsing `bootopt=`, and
  `boot_linux` `0x41E1AE6A` is the 64-bit decompress-and-jump path directly.
  (Inference: the Amazon path skips the `bootopt=` branch; the callers are
  indirect, no direct `bl` to `0x41E1AE6A` exists in the image.)

## Q3. Would our image fit a download-buffer boot?

Header of the current images (`experiments/phase-04/pack_boot.py`, e.g.
`artifacts/phase-04/boot-lidar-lateinit-fastboot-return-mapped-pstore-bootimg.img`):
`kernel_addr 0x40080000`, `ramdisk_addr 0x44000000`, `tags_addr 0x4E000000`,
`page_size 0x800`, kernel section ~`0x42cbea`, ramdisk `0x3ed2c9`, image ~10.5 MiB.

- Kernel `0x40080000..0x4408..` is inside the mapped `0x40080000+0x04000000`
  region; ramdisk `0x44000000` ends at `0x443ed2c9`, inside the same region.
  Tags `0x4E000000` are at the start of the `0x4E000000+0x00100000` region.
- The download window is the mapped `0x44FFF000..0x4DFFFFFF` region (see Q5), and
  `fastboot_init` publishes `max-download-size` = `0x8000000` (128 MiB) from
  `0x41E1D1A0`-`0x41E1D1A2`. A 10-11 MiB image fits with ~117 MiB spare.
- Unverified: the exact `xfer_buffer` base passed to `fastboot_init`
  (`0x41E1D060`; callers `0x41E1C336` and `0x41E1C800`, argument not decoded in
  this pass). The published size and the mapping make the fit safe, but the base
  should be read from those two call sites before writing a handler that reads
  `data` directly.

So the *data* would pass the address checks; only the handler is missing.

## Q4. Risks a RAM boot would have vs. a `boot_a` boot

1. The download buffer must be large enough and mapped; the published
   `max-download-size` is the only authoritative bound (128 MiB).
2. A custom handler cannot rely on the stock `cmd_boot`'s overlap checks; it must
   re-implement at least the "does not overlap LK / the download buffer" test or
   accept that a malformed header corrupts LK.
3. `boot_linux` (`0x41E1AE6A`) needs `boot_hdr` to be the *download buffer*, not
   `0x45000000`; the normal path stages the compressed blob at `0x45000000` and
   `boot_linux` treats `0x45000000` as the gzip source. A RAM-boot handler must
   either copy/gzip-stage the downloaded image to `0x45000000` first or call a
   different entry. This is the single largest difference from the `boot_a` path.
4. Nothing in the handler touches the partition table or the boot-mode state, so
   the ramoops/pstore probes and A/B selection are unaffected (positive: a RAM
   boot does not write `boot_a`/BCB).
5. `boot_linux` rewrites `/memory` and `/chosen` (see below), so a RAM boot sees
   the same LK-authored memory node as `boot_a`.

## Q5. Region list and the 0x60000000 ramoops proposal

The stock region table lives at `0x41E2FFE4` (not `0x41E2FFC0`, which is the tail
of the preceding data). Records are 24 bytes, name pointer first, followed by the
region's values; the entries, in order:

| name | values (VA) | implied range |
| --- | --- | --- |
| `mcusys` (`0x41E28936`) | `0x41E00000`, `0x00400000` | `0x41E00000..0x41EFFFFF` (LK, 2 MiB) |
| `ram` (`0x41E2CD10`) | `0x40080000`, `0x04000000` | `0x40080000..0x4407FFFF` |
| `bootimg` (`0x41E2893D`) | `0x4E000000`, `0x00100000` | `0x4E000000..0x4E0FFFFF` |
| `bootimg` (`0x41E2893D`) | `0x44FFF000`, `0x09000010` | `0x44FFF000..0x4DFFFFFF` |
| `download` (`0x41E28945`) | `0`, `0` | unused tail marker |

**`0x60000000` is not in the list.** The highest end is `~0x4E100000`. A fetch
region at `0x60000000` is therefore **unsafe**: the same failure that disconnected
the device at `0x44400000` (`notes.md`, peek experiment) applies: a fetch goes
through `mem_region_find` plus LK reads, and an unmapped address faults. The
current `ramoops` at `0x43810000`/`0x60000` is inside `0x40080000..0x4407FFFF`
and is the only safe choice. Do not move `ramoops` to `0x60000000`, and do not
add it as a fetch region.

## Q6 (added). Does LK rewrite the DTB `/memory` node?

**Yes, on the live handover path.** In `boot_linux` immediately after the DTB is
selected and copied:

- `0x41E1B632`: `bl 0x41E1FC2E` (FDT path lookup) with `r1` = `"/memory"`
  (`0x41E2A0E7`); the node offset is kept in `sl`.
- `0x41E1B63A`-`0x41E1B64A`: the size value comes from LK's own DRAM bookkeeping —
  global `orig_dram_info` (`0x41E2A0F4`) via `0x41E11438` at `0x41E1B63C`, or the
  global at `[r4,#...]` (`mblock_info`, `0x41E2A102`) at `0x41E1B642`.
- `0x41E1B64A`-`0x41E1B65A`: `r2` = `"reg"` (`0x41E2A002`), `r3` = the built
  buffer, `[sp]` = `r0 << 4` (length = 2 cells x 8 bytes per region), then
  `bl 0x41E1FFC0`, the FDT property setter. The big-endian base/size cells are
  assembled in the loop at `0x41E1B540`-`0x41E1B5F0` from
  `ldrd r8,sb,[r8,#8]` plus a subtraction, i.e. LK writes *its own* memory
  base/size into `/memory/reg`.

A second reference to `"/memory"` exists at `0x41E11530` (helper region
`0x41E114E0`, the `orig_dram_info`/`lkb` bookkeeping), same conclusion.

So the kernel never sees the DTS literal `0x3f9c0000`; LK overwrites `/memory`
`reg`. **PLAN.md item d must stay open**, because:

- verified: the rewrite site and the property (`0x41E1B632`-`0x41E1B65A`,
  `/memory` + `reg`, value from `orig_dram_info`/`mblock_info`), and that it runs
  on the same handover our `boot_a` images use;
- unverified: the numeric value written. It is a runtime global, not a constant;
  static analysis cannot produce it. Closing item d needs one device-side read of
  the DT the kernel received (e.g. early kernel `of_...` print, or a Kaeru
  `fetch` of the copied DTB at `tags_addr 0x4E000000` with a mapped region).

The DTS value only matters if LK's setter fails (it returns a non-zero status
through the `cmp r0,#0; bne 0x41E1BEFA` checks at `0x41E1B65E`), which would make
`boot_linux` return FALSE rather than boot with the DTS value.

## What a custom handler would need (if RAM boot is still wanted)

Karat's `board-karat.c:206-255` pattern, but with the Lidar addresses:

| need | address | evidence |
| --- | --- | --- |
| register a command | `0x41E1CBBC` | `configs/amazon/lidar_defconfig` (`CONFIG_FASTBOOT_REGISTER_ADDRESS`), call at `0x41E1D0B6` |
| stage the image for `boot_linux` | `0x41E110F4` -> `0x45000000` | constant getter, called from `0x41E1AEB8` |
| memcpy | `0x41E1F270` | used by the DTB copy at `0x41E1B158` and header copies |
| handover | `0x41E1AE6A` | documented in the handover research |
| DT `tags_addr` handling | inside `0x41E1AE6A` | `0x41E1B626`-`0x41E1B6FE` |
| mem region lookup for fetch | `mem_region_find` (already in Kaeru) | `lib/fastboot/cmd_fetch.c` |

The handler must first copy the downloaded image to `0x45000000` (or adapt
`boot_linux`'s source pointer), then call `0x41E1AE6A` with
`arg0 = kernel_entry` and `arg1 = tags_addr`, and must not exceed the
`0x8000000` download bound. It should also re-check the address policy from the
dead strings (`Q4` item 2) because the stock checks are not present to reuse.

## Reproduction

All analysis was done with capstone in a Python session over
`dumps/20261110-lidar-readback/lk_a.bin`; no files were modified. String
references were resolved with `target = literal + (insn_addr + 4)`, where
`literal` is the 32-bit word loaded by the preceding `ldr rX,[pc,#imm]`; this
formula was validated against the live `fastboot_init` and handover call sites
listed under Q1.
