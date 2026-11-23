# LK → kernel handover research: why some Lidar images never reach `primary_entry`

Date: 2026-11-15. Scope: research only. No code changes, builds, commits, flashes, or
hardware commands were performed for this note. It explains the observed entry-probe
results from the bootloader (LK/UFBL) and Linux ARM64 boot contracts, and ranks the
experiments that can discriminate between the remaining explanations.

## Bottom line

1. The entry probe is a **pre-C, pre-MMU store at the first instruction of
   `primary_entry`** (`repos/LibreEcho-Linux/arch/arm64/kernel/head.S:49-107`). Its
   absence in a capture proves that either LK never jumped, or it jumped somewhere
   other than the expected Image entry, or the bytes it jumped to were not the bytes
   under test. It cannot be explained by any kernel initcall ordering.
2. `CONFIG_MFD_SYSCON` and `CONFIG_REGMAP_MMIO` cannot cause a failure before
   `primary_entry`. `syscon_init` is a `postcore_initcall`
   (`repos/LibreEcho-Linux/drivers/mfd/syscon.c:378`), and initcalls run from
   `do_basic_setup()` inside `kernel_init_freeable()`
   (`repos/LibreEcho-Linux/init/main.c:1429-1461`, `:1681`), which is reached only
   after `start_kernel()`, `setup_arch()` and a working MMU. **Therefore the syscon
   Kconfig is not causal for the missing pre-entry marker.** The correlation is a
   property of the *image bytes and sizes* that the two builds produced, not of the
   syscon code itself.
3. An offline replay of LK's pre-jump logic (section 8) shows the DTB collection is
   byte-identical across every artifact and that both the backward magic scan and the
   gzip inflate succeed on all five. The content-dependent LK stages therefore cannot
   distinguish the working and failing images, so the failure lies after a successful
   handover preparation: entry not taken, entry not at the expected address, or the
   probe bytes lost before the fetch.
4. The captured evidence is consistent with a **failed or aborted LK handover**, not
   with a kernel that entered and crashed later: the working control's capture has a
   `DBGC` console record and a full Linux console, while every failing syscon capture
   has neither `DBGC`, `PSIG`, nor the entry marker.
5. The highest-value next step is offline: replay LK's exact DTB-trim + gunzip logic
   on the failing and control images. That can confirm or kill the main hypothesis
   without another flash.

## Evidence classes

- **Proven (local artifact or source fact)**: directly read in this repository.
- **Inferred**: follows from the cited source and the measured evidence, but was not
  observed in a controlled experiment here.
- **Unknown**: no primary source located.

## 1. What the measured images contain

The boot images were parsed here; values are from the Android v0 header plus the
kernel's own ARM64 Image header. They match the packer's construction:
`experiments/phase-04/pack_boot.py:781` gzips the Image, `:795` computes the ramdisk
offset as `PAGE_SIZE + align_up(kernel_size, PAGE_SIZE)`, `:803-804` writes the MTK
header size as `len(gzip_kernel) + len(dtb_collection)`, and `:819-823` writes the
v0 header and ramdisk. `gzip_deterministic` at `pack_boot.py:264-273` emits a
fixed-header gzip stream.

| Artifact | SHA-256 (prefix) | `kernel_size` | ramdisk offset | decompressed Image | Image header `image_size` |
| --- | --- | --- | --- | --- | --- |
| `boot-lidar-no-syscon-entry-control.img` | `f7c4d33d` | `0x42dcdf` | `0x42e800` | `0x7e6200` (8 282 624) | `0x850000` |
| `boot-lidar-syscon-entry-probe.img` | `07521890` | `0x430395` | `0x431000` | `0x7e6200` (8 282 624) | `0x850000` |
| `boot-lidar-syscon-small-entry-probe.img` | `7f6a89ca` | `0x42686d` | `0x427800` | `0x7d6200` (8 217 088) | `0x840000` |
| `boot-lidar-lateinit-fastboot-return-mapped-pstore-bootimg.img` | `9c837a8d` | `0x42cbea` | `0x42d800` | `0x7d6200` | `0x840000` |
| `boot-lidar-no-syscon-flushed-control.img` | `7c6c0fc1` | `0x42cded` | `0x42d800` | `0x7d6200` | `0x840000` |

All five use `kernel_addr = 0x40080000`, `ramdisk_addr = 0x44000000` and a
`0x3ed2c9`-byte stock ramdisk. The decompressed Image is written at
`0x40080000`; even the largest ends at `0x40866200`, i.e. 8,282,624 bytes, far below LK's
28 MiB decompression allowance (below) and far below LK's own base at `0x41E00000`.

Note on the task's "kernel region" values: the supplied figures (for example
`0x42ecdf` for the no-syscon entry control and `0x426aed` for the small syscon image)
differ from the parsed header values by small, non-constant amounts. The parsed
headers above are reproducible from the artifacts and are used as fact here; the
supplied region list is treated as a transcript of the experiment log, not as header
truth. The qualitative ordering it reports is unchanged: the small syscon image has
the smallest kernel section, so a single upper bound on `kernel_size` cannot explain
both failure sets.

## 2. The Linux side of the contract

- ARM64 Linux has **no decompressor**; the bootloader must decompress the Image:
  `repos/LibreEcho-Linux/Documentation/arm64/booting.rst:63-64`.
- The decompressed Image begins with a 64-byte header including `image_size`
  ("Effective Image size"): `Documentation/arm64/booting.rst:75-80`.
- At least `image_size` bytes from the start of the Image must be free for the kernel:
  `Documentation/arm64/booting.rst:138-139`.
- The handover contract is `x0 = DTB`, `x1..x3 = 0`, MMU off, D-cache off, image
  cleaned to the PoC: `Documentation/arm64/booting.rst:161`, `:173-180`.
  The kernel's own comment repeats this: `arch/arm64/kernel/head.S:49-62`.
- A misaligned physical placement only disables KASLR and prints a firmware bug
  warning (`arch/arm64/kernel/setup.c:332`); it does not prevent entry. That warning
  is present in the working control console, so the working path has the same
  placement warning yet runs to late init.
- The entry probe executes before `preserve_boot_args` and before any C code, with
  the MMU still off, so its store is Device-nGnRnE and its 16 bytes reach the PoC
  without cache maintenance (`arch/arm64/kernel/head.S:95-107`). If those 16 bytes
  are absent, `primary_entry` did not execute at that physical address.

## 3. The LK handover path

The device's own LK is an Amazon UFBL build (strings reference
`FOS6-mt8167-nightly-build-low-level-images/bootable/bootloader/ufbl-features`, read
from `dumps/20261110-lidar-readback/lk_a.bin`, e.g. at file offset `0x2435b`). The
LK image is ARM (A32), linked at `0x41E00000`: the boot vector at file `0x200`
branches to `0x41e00024`, and the mt8163 LK source documents the same layout,
"LK start: 0x41E00000, Kernel Start: 0x40080000"
(`app/mt_boot/mt_boot.c:548-551` of
https://github.com/R0rt1z2/android_bootable_bootloader_mt8163/blob/b93a47086ff462177535082e5db3d5725111bfec/app/mt_boot/mt_boot.c).

The closest public source for this LK generation shows the exact sequence used by
MT8167-class devices:

1. **Header load.** `mboot_android_load_bootimg_hdr("boot", CFG_BOOTIMG_LOAD_ADDR)`
   reads the v0 header (`mt_boot.c:1191-1193`).
2. **Stage the compressed image.** For a 64-bit kernel,
   `kimg_load_addr = target_get_scratch_address()` and the whole boot-image contents
   are read from the partition to scratch (`mt_boot.c:1200-1208`,
   `platform/mt8163/load_image.c:940-1000`). The eMMC read starts after the v0 header
   page and copies `g_bimg_sz` bytes.
3. **2 MiB alignment gate.** LK refuses a 64-bit kernel whose `kernel_addr` is not
   2 MiB aligned (`mt_boot.c:500-506`). `0x40080000` passes.
4. **Appended-DTB discovery.** LK scans *backwards* from `zimage_addr + kernel_size`,
   byte by byte, for the FDT magic and treats everything from the match to the end as
   the appended DTB data; the public source reduces `zimage_size` by that distance
   (`mt_boot.c:508-544`). The device UFBL does **not** reduce it: the decompressor is
   called with the header's full `kernel_size` (section 11). The device parser is also
   newer:
   its strings include `get dtb_addr`, `dtb_addr = 0x%08X, dtb_size = 0x%08X`,
   `Error: dtb size %d larger than max size %d`, `using best matching dtb`, and
   `Parsing all dtbs...` (`lk_a.bin` offsets `0x2c6xx-0x2c9xx`).
5. **Decompress into `kernel_addr`.** `decompress_kernel(zimage_addr,
   g_boot_hdr->kernel_addr, kernel_size, 0x1C00000)` using the header's plain
   `kernel_size` (the device binary does not subtract the DTB distance; section 11);
   on any error LK prints
   `decompress kernel image fail!!!` and spins forever (`mt_boot.c:544-556`). The
   public implementation uses zlib `inflate(..., Z_FINISH)` with `avail_in` limited to
   `zimage_size` and `avail_out` limited to the passed size, and requires
   `Z_STREAM_END`
   (`app/mt_boot/decompressor.c:31-98` of the same repository). It does not verify a
   decompressed-size field; it merely requires the whole stream to fit.
6. **DTB validation and copy.** The selected DTB must have `FDT_MAGIC`, its size must
   not exceed a compile-time maximum, and its end must stay below the framebuffer
   base; otherwise LK prints an error and returns FALSE (`mt_boot.c:558-580`).
7. **Jump.** `boot_linux_fdt` eventually calls `lk_jump64(entry, tags, 0,
   KERNEL_64BITS)` (`mt_boot.c:919-974`). Every failure in steps 4-6 is a silent
   stall or a loop, not a visible console message on this product, because LK's
   UART is not exposed.

The device LK binary confirms this same code family, including checks that the older
public source lacks. Exact strings in `lk_a.bin`:

| File offset | String |
| --- | --- |
| `0x2c74a` | `Kernel size is bigger than allowed limit (%d)` |
| `0x2c8eb` | `decompress kernel image fail!!!` |
| `0x2c90c` | `dtb_addr = 0x%08X, dtb_size = 0x%08X` |
| `0x2d70d` | `gunzip header is bigger than expectation! Error!` |
| `0x2dd13` | `(page_size + kernel_actual + ramdisk_actual) unsigned overflow!!` |
| `0x2ddf3` | `invalid kernel & ramdisk address: images overlap` |
| `0x2debb` | `(boot_hdr->kernel_size + boot_hdr->ramdisk_size + SCRATCH_ADDR) unsigned overflow!!` |
| `0x2df72` | `invalid ramdisk address: overlap with the download image` |

(Offsets are file positions within the dumped image; add `0x41E00000 - 0x200` for the LK
virtual address.)

**Important consequence.** Steps 4-6 are the only places where LK behaviour depends
on the kernel bytes rather than on the header's address fields. The header's
addresses are identical across the working and failing images (`0x40080000`,
`0x44000000`, tags `0x4e000000`), and all sizes stay inside every plausible limit:
the largest kernel section is `0x430395`, the ramdisk is 4,117,193 bytes, and
the decompressed Image is 8,282,624 bytes against a 28 MiB output allowance. What *does*
change between builds is the compressed byte stream (size and content) and the DTB
collection.

## 4. What the captures prove

The pstore/ramoops window used by these probes is base `0x43810000`, size `0x60000`
from `experiments/phase-04/notes.md:809-861`. The probe marker address
`0x43860700` is `0x50700` bytes into that window, i.e. inside the pmsg zone.

- `dumps/20261115-lidar-phase4/ramoops-no-syscon-entry-control.bin` contains
  `PROBE-ENTRY!` at file offset `0x50700` (physical `0x43860700`), a `DBGC` header at
  offset `0`, another at `0x40000`, and a full Linux console beginning at `0x4000c`
  (`Booting Linux on physical CPU ...`, `Linux version 6.1.178+`,
  `Machine model: MT8167B`). This proves LK decompressed the Image, jumped to
  `primary_entry`, and the kernel later reached console/ramoops init.
- `ramoops-syscon-entry.bin`, `ramoops-syscon-small-entry.bin`,
  `ramoops-syscon-flushed.bin`, `ramoops-syscon-pmsg.bin` and
  `ramoops-syscon-start-kernel.bin` contain **no `DBGC`, no `PSIG`, no `PROBE-ENTRY!`,
  and no Linux text** (full scan of all 0x60000 bytes in each file). The failure is
  therefore at or before the handover, not in a later initcall.
- The earlier RAM-marker experiments established that warm-reset RAM reads are not a
  reliable channel (`notes.md:578-621`), so this note relies on the fetch-based
  ramoops captures, which are byte-exact for the mapped window (`notes.md:809-861`).

The probe's own contract makes its absence meaningful: it is the first instruction of
the entry point, before the kernel stack, before BSS clearing, before any use of the
DTB (`arch/arm64/kernel/head.S:95-107`). A kernel that "hangs very early" but after
entry would still leave the marker unless something overwrote those 16 bytes, which
is a separate, testable possibility (H3 below).

## 5. Why syscon cannot be the cause

`syscon_init` is registered with `postcore_initcall`
(`drivers/mfd/syscon.c:378`). Initcall levels run in `do_initcalls()` from
`do_basic_setup()` (`init/main.c:1429-1461`, called at `:1681`), inside
`kernel_init_freeable()`, which runs as the idle/kernel thread after `start_kernel()`
has set up the MMU, memory, timers and the console. Anything a syscon build adds
becomes observable only there. The entry probe runs orders of magnitude earlier.
Consequently:

- If the failing syscon images never reached the probe, syscon is not the mechanism.
- If they did reach the probe and the marker was lost, syscon could at most affect
  memory reuse much later, after the probe had already written.
- Either way, the discriminating variable is the image the packer produced, not the
  two Kconfig symbols. This is the central research conclusion.

Two corollaries follow. First, the failure sets should not be pooled: the small syscon
image also removes MUSB, which is an independent variable. Second, a "syscon build"
is just a differently-sized, differently-compressed Image plus a possibly different
DTB; only those LK-visible differences matter.

## 6. Ranked hypotheses with falsifying tests

H1 and H2 were replayed offline after this ranking was drafted and did not survive
(section 8). H3 and H4 are now the leading explanations. None of the remaining tests
requires a blind flash first.

### H1: LK's decompression input was truncated or the stream was rejected (REFUTED, section 8)

LK computes the gzip input length by subtracting the appended-DTB distance from
`kernel_size` (`mt_boot.c:508-544`). In the newer mt8167 parser this pass is richer
(`Parsing all dtbs...`, `dtb_size`, board-id matching), and a false or mis-sized FDT
boundary truncates `zimage_size`. zlib `inflate(Z_FINISH)` then returns
`Z_BUF_ERROR`, not `Z_STREAM_END`, and LK spins in `decompress kernel image fail!!!`
(`decompressor.c:31-53`, `mt_boot.c:551-556`). This mechanism is content- and
size-dependent, which is exactly the shape of the evidence: the failures do not
follow a size threshold, and the working control has the same entry bytes and the
same `image_size` class as the large failing image.

Falsifying tests, offline first:

1. Reproduce LK's backward scan over each image: start at
   `kernel_section + kernel_size`, scan down for `d0 0d fe ed`, compute
   `dtb_size`, and check whether the resulting `zimage_size` still inflates to
   `Z_STREAM_END` with the exact `0x1C00000` output limit. If a failing image
   truncates and the controls do not, this is proven without hardware.
2. Independently, inflate each full gzip stream with `avail_in` cut at every FDT-magic
   candidate and record the zlib return code.
3. On hardware, only if (1)/(2) do not discriminate: repack the failing syscon Image
   with the working control's exact DTB collection and with a different gzip level;
   a marker appearing in either variant isolates content/length from code.

### H2: LK's appended-DTB validation rejects the rebuilt collection (REFUTED, section 8)

The mt8167 LK parses all appended DTBs and selects by board id, and refuses a DTB
larger than `max size` (`lk_a.bin` strings `0x2c7d8`, `0x2c8b6`; public analogue at
`mt_boot.c:558-580`). The packer replaces appended blob index 4 and rebuilds the
19-blob collection (`pack_boot.py:637-650`, `:781-804`), so the collection's layout
and total size change with every build. A parse/selection failure returns before the
jump.

Falsifying test: pack the failing syscon kernel with the stock 19-DTB collection
byte-identical (and with the working control's collection), then check the entry
marker. Also validate each collection offline with `libfdt` and compare board-id
properties against the stock DTBs, plus the LK string's max-size rule.

### H3: The marker address was reused/overwritten, or the tested image was not the one that ran

Two independent risks. First, `0x43860700` is only reserved if the booted DTB carries
the matching reserved-memory/ramoops node; a differently-built DTB could let early
memblock or ramoops initialization clear that page *after* the probe wrote it. Second,
the project has a documented history of A/B fallback invalidating conclusions
(`notes.md:471-500`), and the failing images were judged by "no marker" rather than by
a readback of the flashed slot in the same session.

Falsifying tests:

1. Make the probe store to two distant addresses, at least one inside a region
   reserved in every candidate DTB (for example two pages in the `0x43030000`-adjacent
   reserved window is not safe; use an address also written by the later milestone
   probe and cross-check both), then require both to be absent before declaring no
   entry.
2. Before every test, `fastboot getvar current-slot`/BCB check and a `boot_a` readback
   hash equal to the artifact under test; record `misc` BCB bytes as in
   `notes.md:486-500`.
3. Diff the reserved-memory nodes of the failing DTB against the working control's.

### H4: The handover honours the ARM64 `image_size` field and rejects/misplaces the image

The large syscon image has `image_size = 0x850000`, the working large control also
reports `0x850000` (per the task evidence), and the small syscon image `0x840000`.
The kernel contract requires `image_size` bytes free from the Image start
(`booting.rst:138-139`). LK's public code ignores this field (it uses the boot header's
compressed `kernel_size`), but the mt8167 UFBL is a newer fork and may not.

Falsifying test: patch only the Image header's `image_size` field of the failing
syscon build to `0x840000` (no code change) and to `0x850000` on a working build; if
entry behaviour changes, the field is being consumed. This is a one-field, offline
repack, and it cleanly separates header metadata from kernel code.

### H5: The small syscon failure is a different bug (MUSB removal), not syscon

The small image also drops MUSB; it has the smallest compressed kernel and the same
decompressed length class as the working baseline. If the large failing image's cause
does not apply to the small one, pooling them is the error.

Falsifying test: rebuild the small configuration with MUSB enabled (and with syscon
still on), keeping the DTB fixed; if it starts working, the small failure belongs to a
separate variable. This is lower priority because it explains only one of the two
failure sets.

## 7. Recommended next actions, in order

1. ~~Offline LK replay (H1/H2).~~ Done, see section 8: both hypotheses are refuted.
2. **Reserved-memory audit (H3).** Diff the reserved-memory and ramoops nodes of the
   failing and control DTBs. The collections are byte-identical today, so this checks
   whether the probe builds ever shipped a different collection, and whether the
   fetched page can be reused before ramoops reclaims it.
3. **Header-field experiment (H4).** Repack one failing image with the ARM64
   `image_size` forced to the control value, leaving `res5` and the PE entry
   unchanged; if entry behaviour changes, the handover is reading that field.
4. **One hardware A/B (H3).** Two-address probe plus slot/BCB readback so a negative
   result is unambiguous. This is now the primary remaining device test, because LK's
   pre-jump logic is proven identical for the sampled images.

## 8. Offline replay results (2026-11-15)

Script: `/tmp/lk_handover_replay.py`, read-only, run with
`python3 /tmp/lk_handover_replay.py`. It parses each boot image, replicates the
backward magic scan from `kernel_section + kernel_size` (`mt_boot.c:508-544`), reads
the selected FDT totalsize, and inflates with the exact 0x1C00000 cap and
`Z_FINISH` semantics (`decompressor.c:31-98`). It tests the input pointer both at the
MTK header start (`avail_in = zimage_size`) and after it (`avail_in = zimage_size -
0x200`).

Reproduction (all five artifacts unless noted):

- Kernel section starts at file offset `0x800`; the MTK header occupies `0x200` bytes
  (magic `0x58881688`, length field equals `kernel_size - 0x200`); gzip starts at
  `0xa00`.
- 19 appended DTBs parse contiguously from the gzip end to the kernel-section end.
  The collection is 1,018,698 bytes with SHA-256 prefix `2d98181e7eeb7406` in **all
  five artifacts**, and the blob sizes are identical everywhere:
  `0xd3e2 0xd2de 0xd5c6 0xd2e2 0x359f 0xcfe2 0xcfde 0xc441 0xc1ed 0xd234 0xd2ac
  0xf1c4 0xf22f 0xf22b 0xec48 0xec28 0xec63 0xd008 0xd07c`.
- The backward scan finds exactly the 19 blob starts and no other `d0 0d fe ed`
  sequence anywhere between the gzip start and the section end. It therefore selects
  the last blob (index 18) every time, with `dtb_size = 0xd07c`.
- Inflate from the gzip start reaches stream end in every artifact, consumes exactly
  the gzip length, and ignores trailing DTBs. With `avail_in = zimage_size` the unused
  trailing bytes are 965,838; with the pointer after the MTK header they are 965,326
  (the 18 earlier DTBs). The difference is the 512-byte MTK header.

| Artifact | scan start | chosen DTB | `dtb_size` | `zimage_size` | gzip consumed | unused (pointer after MTK hdr) |
| --- | --- | --- | --- | --- | --- | --- |
| no-syscon entry control | `0x42e4df` | `0x421463` | `0xd07c` | `0x420c63` | `0x334f95` | 965,326 |
| syscon entry probe | `0x430b95` | `0x423b19` | `0xd07c` | `0x423319` | `0x33764b` | 965,326 |
| syscon small entry probe | `0x42706d` | `0x419ff1` | `0xd07c` | `0x4197f1` | `0x32db23` | 965,326 |
| lateinit mapped bootimg | `0x42d3ea` | `0x42036e` | `0xd07c` | `0x41fb6e` | `0x333ea0` | 965,326 |
| no-syscon flushed control | `0x42d5ed` | `0x420571` | `0xd07c` | `0x41fd71` | `0x3340a3` | 965,326 |

Decompressed kernel images match their headers: 8,282,624 bytes and `image_size
0x850000` for the two large images, 8,217,088 bytes and `0x840000` for the other
three. The decompressed Image begins with `MZ`-compatible code0/code1, has
`text_offset = 0`, magic `0x644d5241` at offset `0x38`, and `res5 = 0x40` pointing at
a PE header (`PE\0\0` at `0x40`), so the build is EFI-capable; entry is still at the
start of the decompressed image, identical for all artifacts.

Consequences:

- **H1 does not survive.** No false FDT magic exists inside the gzip data or the DTB
  bodies, so the scan cannot truncate the stream; it selects the real last DTB. Inflate
  reaches stream end for the failing artifacts exactly as for the controls, so LK's
  `decompress kernel image fail!!!` path cannot fire on these files.
- **H2 does not survive.** The DTB collection is byte-identical (same SHA-256, same
  sizes) across working and failing builds, so any deterministic parse, board-id
  selection, or max-size rejection sees the same input and cannot discriminate them.
- **Packer consequence.** Under the public mt8163 logic LK copies only the last
  appended DTB (index 18) and ignores the earlier blobs, including the replaced index
  4. If the mt8167 UFBL parses all blobs instead, the collection still being identical
  across builds makes its decision identical as well.
- What remains is the jump or the evidence chain: handover preparation succeeds
  identically for the sampled images, and the probe bytes are either never executed at
  `0x40080000` or are overwritten before the fetch. That is H3/H4 territory.

Caveat: this models the public `mt_boot.c` scan. The device LK has a newer parser
(`Parsing all dtbs...` strings), but identical inputs across all five artifacts mean
any deterministic parser must reach the same decision for working and failing builds.

## 9. Reserved-memory and ramoops audit (2026-11-15)

Method: a minimal FDT parser walked `/reserved-memory` in all 19 appended blobs of
the control collection (the objects are byte-identical across the five artifacts, so
one collection covers every image). Script: `/tmp/audit_ramoops.py` (read-only).

### 9.1 Which blob carries the probe window

Only **blob index 4**, the packer-replaced LibreEcho DTB, carries the
`ramoops@43810000` node:

| Blob | Model | Nodes | Reserved ranges |
| --- | --- | --- | --- |
| 4 | `LibreEcho Lidar` | 89 | `0x43000000` ATF/secmon `0x30000`; `0x4df00000` ram-console `0x10000`; `0x444f0000` minirdump `0x10000`; `0x43810000` ramoops `0x60000` |
| 0-3, 5-18 | Amazon board names | 342-457 | `0x43000000` ATF `0x30000`; `0x44400000` ram_console `0x10000`; `0x44410000` mediatek,pstore `0xe0000`; `0x444f0000` minirdump `0x10000` |

Blob 4 is the only one with `/reserved-memory/ramoops@43810000` and the only one
with a `secmon@43000000` node in addition to `atf@43000000`. Its ramoops properties
are `record-size = 0x40000`, `console-size = 0x10000`, `pmsg-size = 0x10000`
(`repos/LibreEcho-Linux/arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:85-92`).
The stock blobs instead describe `mediatek,pstore` at `0x44410000` size `0xe0000`
and `mediatek,ram_console` at `0x44400000`.

### 9.2 Zone layout and capture consistency

`ramoops_probe` lays out one dmesg record first, then console, then pmsg
(`fs/pstore/ram.c:772-798`). With the blob 4 sizes the window maps exactly as the
capture shows:

| Window offset | Size | Zone | Capture evidence |
| --- | --- | --- | --- |
| `0x00000`-`0x3ffff` | `0x40000` | dmesg record | `DBGC` header at `0` |
| `0x40000`-`0x4ffff` | `0x10000` | console | `DBGC` at `0x40000`, text at `0x4000c` |
| `0x50000`-`0x5ffff` | `0x10000` | pmsg | marker at `0x50700` (pmsg + `0x700`) |

This matches the control capture offsets and the DTS comment that records end at
`0x43870000` (`libreecho-lidar.dts:77-84`).

### 9.3 Does blob 18 versus blob 4 matter

Yes, decisively for whether the probe window is reserved. Under the public mt8163
logic the backward scan copies the **last** appended DTB (index 18, section 8).
Blob 18 is the stock Kyanite EVT tree with no `ramoops@43810000` node; its pstore
reservation is `mediatek,pstore` at `0x44410000`, which
`experiments/phase-04/notes.md:780-786` identifies as an unmapped hole in LK's
mappings. Selecting blob 18 would therefore give the kernel no reservation at
`0x43810000`, and its pstore channel would target `0x44410000`.

The control capture proves this did not happen: the console record contains
`ramoops: using 0x60000@0x43810000, ecc: 0` and an
`OF: reserved mem: OVERLAP DETECTED` between `atf@43000000` and
`secmon@43000000` (`dumps/20261115-lidar-phase4/kernel-console-438.log:8-9`,
`:88`). The log's node names also match blob 4, whose nodes are named
`atf@43000000` and `secmon@43000000`; the stock blobs name theirs
`atf-reserved-memory@43000000` and have no `secmon` node. The `secmon` node and the
ramoops node exist only in blob 4, so the booted tree carried blob 4's
reserved-memory. This matches the DTS
comment that LK scores appended DTBs against the idme board_id table and that the
replacement must keep `amzn,lidar-pvt` to be selected
(`libreecho-lidar.dts:23-27`); the device LK also contains `model` and `MT8167B`
strings, so an LK rewrite of `/model` plausibly explains why the log says
`Machine model: MT8167B` while blob 4 says `LibreEcho Lidar` (inference, not
proven).

Two consequences:

- The probe channel's reservation depends on the scoring selection of blob 4, not
  on the public last-blob rule. A flow that ever fell back to stock selection would
  silently move pstore to `0x44410000` and make the `0x43810000` capture
  meaningless.
- Since all five artifacts embed the identical 19-blob collection, selection cannot
  differ between working and failing builds. This confirms, from the DTB side, that
  the reservation handling is not the discriminator between them.

Evidence caveat: no appended blob has `model = "MT8167B"`, so the console record's
model is either LK-rewritten or the console zone predates the tested boot. The
`PROBE-ENTRY!` store at `0x50700` is the current-boot-specific evidence; console
provenance should not be used to date a boot.

### 9.4 Safe second marker address

Only two reserved ranges are identical in **all 19** candidate DTBs:

- `0x43000000`, size `0x30000`: ATF/secure firmware. Rejected: firmware-owned,
  possibly protected from non-secure writes.
- `0x444f0000`, size `0x10000`: `minirdump`, present in every blob, with no driver
  binding in this kernel (`grep` over the tree finds it only in the DTS). Rejected by
  no other node: `pstore@44410000` ends exactly at `0x444f0000`, and the ramdisk
  ends at `0x443ed2c9`, so the region is clear of both.

Proposed marker: **`0x444f0800`** (`minirdump` base + `0x800`). It is inside the
first page, away from any minidump header, and is a physical store executed with the
MMU off like the existing probe.

Fetching it requires a new window, because the current image publishes only
`ramoops` (`repos/kaeru/board/amazon/board-lidar.c:38-42`). Add
`{"minirdump", 0x444f0000, 0x10000}` to `mem_regions[]`, then:

```sh
fastboot oem fetch-enable
fastboot fetch minirdump dumps/<date>/minirdump-444f.bin
```

The raw marker offset is then **`0x800`** in a `0x10000`-byte dump of
`0x444f0000`. Caveat: `0x444f0000` is outside the two LK mappings documented at
`notes.md:780-786` (`0x40080000..0x4407ffff` and `0x44fff000..0x4dffffff`), so the
fetch translation (`mem_region_find` plus `oem peek`) must be verified for this
range before relying on it. The MMU-off store itself is unaffected by that caveat.

If changing the fetch window is not available, the only in-window choice is the
dmesg record tail, for example `0x4383ff00` (dump offset `0x2ff00`), which is outside
console (`0x43850000`) and pmsg (`0x43860000`). This is weaker: the record is
pstore-owned and shares the reservation being tested, and a full crash dump could
overwrite it.

### 9.5 Same-region dual markers

Two markers inside `0x43810000..0x4386ffff` share both the reservation and any
whole-window clear, so they add little: they only distinguish a pmsg-zone rewrite
from a record-zone rewrite. A marker in `minirdump` tests a different reservation,
so it separates "handover never ran or wrong slot" from "this ramoops window was
lost or reused". The cross-region pair is the informative experiment.

## 10. Unresolved questions

- Whether the mt8167 UFBL actually scans for a single FDT magic or parses the whole
  collection; the strings show a newer parser but its exact algorithm is not public.
- ~~The concrete value passed to `Kernel size is bigger than allowed limit (%d)` and
  which field it bounds.~~ Resolved in section 11: it bounds the boot header's
  `kernel_size` at `0x1000000`; exceeding it returns FALSE, it does not spin.
- ~~Whether LK validates the decompressed ARM64 Image header or only the compressed
  stream.~~ Resolved in section 11: this UFBL validates no decompressed length, CRC,
  or Image header. Its only post-inflate checks are on the copied DTB.
- Why the control console says `Machine model: MT8167B` although no appended blob has
  that model; LK contains `model` and `MT8167B` strings, so an LK rewrite is
  plausible, but it is not proven and the console may predate the tested boot.
- Whether LK selects blob 4 deterministically on every boot. The collection is
  identical across artifacts and only blob 4 carries the ramoops reservation, so a
  deterministic selection applies the same reservation everywhere; a stock-selection
  fallback would move pstore to `0x44410000`.
- Whether LK's fetch translation can read `minirdump` at `0x444f0000`, which lies
  outside the two documented mappings. The MMU-off marker store does not depend on
  this, but a capture from that window does.

## 11. Device-LK pre-jump audit and the new controlled pair (2026-11-15)

Read-only disassembly of `dumps/20261110-lidar-readback/lk_a.bin` with capstone
(A32 + Thumb-2), mapping `VA = 0x41E00000 + (file_offset - 0x200)`. No hardware, no
source edits. This section answers what the shipped UFBL actually inspects after
inflate, and how a deterministic LK can still end up with different observations.

### 11.1 The handover function and its arguments

`0x41E1AE6A` is the Android-boot / appended-DTB / kernel handover function (Thumb-2,
frame `0x11bc`). Its first argument is stored at `[sp,#0x18]` (`0x41E1AE7E`) and is
later loaded into `r5` and called at `0x41E1BE70`:

```
41e1be6a  mov  r2, r5            ; arg1 = DTB/tags destination
41e1be6c  ldr  r1, [sp, #0x38]
41e1be6e  ldr  r5, [sp, #0x18]   ; arg0 = kernel entry
41e1be70  blx  r5
```

So the jump target is caller-supplied; nothing in the decompressed Image computes it.
`0x41E110F4` is a constant getter, `mov.w r0,#0x45000000; bx lr`, i.e. the compressed
kernel blob is staged at `0x45000000`.

Header gates in the same function:

- `0x41E1AE9E`: `r2 = [boot_hdr+8]` (v0 `kernel_size`); if `> 0x1000000`
  (`0x41E1AEA0`), print `Kernel size is bigger than allowed limit (%d)`
  (file `0x2c74a`, VA `0x41E2C54A`) and take the common FALSE return at
  `0x41E1BEFA`. It does not spin.
- `0x41E1AEDA`: `r1 = [boot_hdr+0xc]` (`kernel_addr`); a zero low-19-bit field prints
  two diagnostics and spins at `0x41E1AEF6`.
- `0x41E1AED0`: `[sp,#0x14] = kernel_size` (clamped to `0x1000000`). Except for a
  later reuse after decompression, this is the value loaded at `0x41E1B170` as the
  decompressor's source length. **The appended-DTB distance is not subtracted.**

### 11.2 DTB discovery runs on the compressed blob

`0x41E1AF44`-`0x41E1B134` walks backwards from `0x45000000 + kernel_size`,
checking the on-disk magic bytes `d0 0d fe ed` one byte at a time
(`0x41E1AF64`-`0x41E1AF80`), with a 1 MiB start bound (`r8 = end - 0x100000`), a
`0x80000` scan/size cap (`0x41E1AF5E`, `0x41E1AF8A`-`0x41E1AF96`), compatibility
matching over candidates (`0x41E1B0C4`-`0x41E1B126`), a `Using best matching dtb
(primary=%s) at %p match=%d` print (file `0x2c8b6`) and a `memcpy` of the selected
blob to the function's second argument (`0x41E1B158`, helper `0x41E1AE58`).

Consequences: the scan sees the *compressed* stream, not the decompressed Image;
`dtb_size = end - magic` includes any trailing bytes; and the selected DTB is copied
to a caller-provided destination before decompression starts.

### 11.3 Decompression: raw inflate, Z_STREAM_END only

`0x41E1B162`-`0x41E1B176` selects the path:

- If the header descriptor word is zero, the alternate branch
  `0x41E1B186`-`0x41E1B190` copies `kernel_size` bytes from `0x45000000` through
  `0x41E1F270` instead of inflating; the images under test take the gunzip branch at
  `0x41E1B176`.
- Otherwise `gunzip(src=0x45000000, dst=[boot_hdr+0xc], srclen=kernel_size,
  dst_cap=0x1C00000)` at `0x41E1B176` (wrapper `0x41E1CB38`, gzip-header parser
  `0x41E1CAC4`, inflate wrapper `0x41E1CA1C`).

The wrapper behaviour is unambiguous:

- `0x41E1CA1C`: `memset(z_stream, 0, 0x38)`, `inflateInit2_` with raw-deflate
  `windowBits = -15`, then `next_in`/`avail_in` from the source and `next_out`/
  `avail_out` from the destination.
- `0x41E1CA7C`: `bl 0x41E20D88` (`inflate`) with `r1 = 4` (`Z_FINISH`).
- `0x41E1CA80`: `cmp r0, #1`; `0x41E1CA84`: `beq 0x41E1CA9A`. Only `Z_STREAM_END`
  is accepted.
- Success (`0x41E1CA9A`): `r3 = next_out - dst`, stored into the local length word,
  `inflateEnd`, return 0. There is no comparison of that length with any expected
  value.
- Failure: print `inflate() error, returned %d` (file `0x2d6cd`) and return -1.

There is no CRC check (raw inflate never reads the gzip trailer), no decompressed
size/Image-header check, and no destination clear beyond the 0x38-byte `z_stream`.
On a gunzip error the caller prints `decompress kernel image fail!!!` (file `0x2c8eb`)
and executes `b .` at `0x41E1B184`, i.e. a permanent spin, not a fastboot return.
Trailing DTB bytes after the deflate stream are simply unused input, so the public
"zimage_size reduced by dtb distance" mechanism cannot fire in this binary.

### 11.4 After inflate, only the copied DTB is checked

`0x41E1B194`-`0x41E1B222` operates on the function's *second* argument (the copied
DTB), not on `kernel_addr`:

- byte-swapped first word must equal `0xd00dfeed`; otherwise print
  `Can't find device tree. Please check your kernel image` (file `0x2c932`) and spin
  at `0x41E1B20A`.
- `dtb_size = [dtb+4]` big-endian (`0x41E1B1B8`), then `dtb_end = dtb + dtb_size`
  is compared against a runtime global memory bound (`0x41E1B1E2`-`0x41E1B1F0`);
  if above, print `[ERROR] dtb end address (0x%08X) is beyond the memory (0x%08X).`
  (file `0x2c96a`) and return FALSE (`0x41E1BEFA`).
- build the bootargs/cmdline buffer, call `0x41E1AC44` (DTB setup/`fdt_check_header`
  family: it calls `0x41E19784`, `0x41E20170`, `0x41E1F620`); nonzero returns FALSE.

No branch in this sequence reads `kernel_addr` content, decompressed length, `image_size`,
`text_offset`, or the PE/entry fields. The only return-FALSE exits in the pre-jump path
are the `kernel_size > 16 MiB` gate, the `dtb_end > memory bound` gate, and the DTB
setup failure; the two content-dependent failures (inflate error, bad copied-DTB
magic) spin.

### 11.5 The controlled results

Recorded from the 2026-11-15 device runs (no reruns):

| run | artifact | result |
| --- | --- | --- |
| no-syscon control `017540d5` | entry probe page `0x43ff0000`, marker `0x43ff0800`, ramoops marker `0x43860700` | fastboot return, both ENTRY markers, Linux console |
| syscon mapped `1119e33f` | same probe layout | Action released, both markers absent; `boot_a` readback byte-exact `1119e33f` |
| no-syscon padded control | zeros padded to syscon `kernel_size 0x4268e7`, `ramdisk_offset 0x427800`, MTK/Android sizes+ID updated | fastboot return: exact size/layout excluded |
| syscon gzip6 `f23822e3` | same decompressed Image `fa90a628` | failed, both markers absent |
| syscon gzip0 stored-deflate `17b16b93` | same decompressed Image | failed, fastboot return |

The matched Images have the same first 64 bytes, `image_size 0x840000`, the same
`primary_entry` file offset (`0x9DD90`) and the same marker instructions. Their
uncompressed lengths differ: `0x7d5a00` vs `0x7d6200` (the earlier working baseline is
also `0x7d6200`; the large working/failing pair is `0x7e6200`). DTBs are identical
within each pair.

### 11.6 How deterministic LK can still produce different observations

LK's pre-jump decision is a function of the boot header fields, the *entire compressed
blob* and the DTB bytes. The public path writes that function as if only header fields
mattered. The new controls held the DTB bytes and the header size/layout constant, and
the two gzip encodings both reach `Z_STREAM_END`; section 8 already showed the backward
scan selects the same last DTB and inflate consumes exactly the gzip stream in every
artifact. With the full `kernel_size` passed as `avail_in` and trailing bytes ignored,
the compressed representation is not an LK branch either, provided inflate succeeds.

Therefore, for a pair with identical header addresses/sizes, identical DTB collection
and a decompressed Image that hashes equal, deterministic LK must reach the same
`blx r5` with the same entry, DTB and tags. A missing marker then cannot be a branch in
the pre-jump code. The surviving explanations are:

1. **The run did not boot the artifact under test.** The byte-exact `1119e33f`
   readback rules out a wrong byte image in the slot, but not A/B/BCB selection at boot
   time.
2. **The marker page was reused or cleared after the store (H3).** The probe store is
   the first instruction at `primary_entry`; a later clear of the same reserved page
   produces an identical "no marker" observation.
3. **The decompressed kernel images are not actually identical.** The length pair
   `0x7d5a00`/`0x7d6200` differs by `0x800` in the tail even though first 64 bytes,
   `image_size`, entry bytes and markers match. LK never inspects that difference, so
   this is a post-jump kernel difference (or a difference in the DTB the kernel itself
   consumes), not an LK rejection.
4. **The jump environment differs in a register/mode not reconstructed here.** This
   function sets `r1=[sp,#0x38]`, `r2=dtb`, `r5=entry`; `r0` comes from earlier code and
   callers are indirect, so a caller-side register difference remains possible even
   with identical arguments to this function.

The "Action released" symptom is host-side and fits a FALSE return better than the two
spin paths, but a kernel reset/hang can also drop the fastboot gadget. Of the three
FALSE-return gates, `kernel_size` and `dtb_end` are equal in the padded control and the
DTB bytes are identical, so those gates cannot discriminate the syscon image from the
control; that leaves the DTB setup gate only if a byte-level DTB difference is later
found, otherwise explanation 1, 2 or 3.

### 11.7 Ranked next tests, all offline first

1. **Full v0 header diff.** Compare every field of the control/syscon/gzip6/gzip0
   artifacts: `kernel_size`, `kernel_addr`, `ramdisk_size`, `ramdisk_addr`,
   `second_*`, `tags_addr`, `page_size`, `header_version`, `os_version`, `name`,
   `cmdline`, `id`. Confirm `kernel_addr` (gunzip destination and jump argument),
   `tags_addr` (DTB destination) and `page_size` are identical; confirm the
   `kernel_size <= 0x1000000` gate.
2. **Replay the device scan, not the public one.** Start at
   `0x45000000 + kernel_size`, apply the 1 MiB window and the `0x80000` cap, select by
   compatibility, and use `dtb_size = end - magic`. Record selected offset, size,
   `dtb_end` versus the runtime memory bound, and `fdt_check_header` on the copied
   blob. This is the only remaining byte-level way the pre-jump path can differ.
3. **Hash and length the decompressed kernel images** for each controlled pair. Equal
   hashes plus equal DTB bytes prove the pre-jump path identical for that pair; then
   only H3/A-B/kernel-tail explanations remain. If they differ, diff the `0x800` tail
   and test whether it overlaps the Image's own appended data or the copied DTB.
4. **Re-audit the marker pages against the DTB actually selected** (last appended blob,
   per section 8) for the syscon runs, not only the control. A page reserved in the
   control DTB but not in the syscon DTB would make a post-store clear possible even
   with identical store instructions.
5. **Only after 1-3 are equal, return to hardware:** dual-region marker plus immediate
   readback, BCB/slot verification, and a capture that distinguishes the spin paths
   (no fastboot gadget) from a FALSE return (fastboot remains alive).

### 11.8 Correction: marker absence is not proof, and a reset-based discriminator

Sections 11.5 and 11.6 and the Phase 4 notes treat a missing ENTRY marker pair as proof
that the handover never reached `primary_entry`. That inference is too strong.

The persistence control is the no-syscon run `017540d5`: both markers were written at
entry, the full kernel booted, late init issued the proven Kaeru watchdog reset, and
the following fastboot fetch read both pages intact. Persistence is therefore proven
only for that path: a deliberate late reset followed by the boot chain's own fastboot
return.

The failing syscon runs were read after a different path: a failed boot, manual BROM
entry with DA download/self-test, then fastboot recovery and fetch. The notes already
record that the BROM/DA path overwrote RAM in the earlier cold-entry reads (which is
why a BROM-only peek was later required). That path may clear both marker pages
(`0x43ff0800` and `0x43860700`) before the read. A missing pair after it is consistent
with a post-store clear of both pages, with a wrong slot, or with a pre-jump stall; it
does not conclusively prove that `primary_entry` never ran.

The device-binary audit is unaffected. Sections 11.3-11.4 show the shipped UFBL accepts
any stream that ends in `Z_STREAM_END`, never compares the decompressed length, and
never reads `kernel_addr` content, `image_size`, `text_offset` or the PE/entry fields.
"LK inspected and rejected the decompressed kernel image" remains refuted independently of
any RAM marker.

To get an entry signal that a later BROM/DA pass cannot erase, the observable is moved
to the entry itself. A new build-time config option inside the existing
`CONFIG_LIBREECHO_LATEINIT_FASTBOOT` `head.S` block adds, immediately after the two
marker stores and before `bl preserve_boot_args`:

1. a 5-second busy-wait on `CNTFRQ_EL0`/`CNTPCT_EL0`, the sequence already used in
   `early_entry_ram_marker_reset.S`; then
2. the hardware-proven Kaeru stage2 TOPRGU reset (`TOPRGU = 0x10007000`): `0x1971` to
   `+0x08`, `0x22000014` to `+0x00`, `dsb sy`, `0x1209` to `+0x14`, then spin.

Order a matched no-syscon control first, carrying the same gate. It must return to
fastboot after roughly the delay plus normal boot, with no BROM entry and no power
cycle. That validates the delay and reset sequence on-device and separates it from
both the boot chain's own watchdog and an ordinary fastboot return.

Then, for the syscon image, a fastboot return at the delayed time proves that
`primary_entry` executed the reset, with no dependence on marker persistence; the
reset is the signal, so a later BROM/DA clear is irrelevant. Absence of that return
within the delay plus margin, against a control that did return, supports no execution
of `primary_entry` (or a hang before the reset write), replacing the inconclusive
marker read. Timing also discriminates: a reset much earlier than the delay would
indicate the boot chain's watchdog, not this probe. Markers stay useful as supporting
data but no longer carry the conclusion alone.
