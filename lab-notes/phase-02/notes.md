# Phase 2 report: experimental boot-chain construction

Date: 2026-11-10. Workspace: `/workspace/libreecho`.
Purpose: build and host-check the restore tool and both stage images before a device write.

## Gate status

**Met.** The restore tooling and the Kaeru stage pass host checks. The Koboreru port
builds, and its four patch sites and all device addresses are derived from the 2019 donor
and agree with the reference kit's hardware-proven image for that donor. The crafted
image's layout matches the kit's. The preloader route is decided: the signed 2019 preloader,
area 1 only. No device was written or booted; all evidence is host-side static analysis or
host tests.

## What was verified

### Restore tooling

Location: `experiments/phase-02/restore/`. Tests: 45, all passing.

```
cd experiments/phase-02/restore && ../venv/bin/python test_lidar_restore.py
Ran 45 tests in 0.095s
OK
```

Implemented and tested: exact device identity, partition size, source size and SHA-256
gates; per-write readback; atomic manifest, plan, state and result files; a prefix-validated
journal; structural resume; BOOT0 sector 0 written last; sector 0 is the final write of the
whole run, not only of boot0; a writable boot0 without `sector0_last` is rejected; boot area
2 is never written; `expdb` is refused after a chain install. The planner compares the
manifest's `partition_bytes` with the backend's actual size where the backend reports one,
so a geometry mismatch fails before the first write; the mtkclient adapter reports no size,
so only the manifest-side checks run there. The apply tests cover boot0, tee1, expdb and gpt
with the header written last. The mtkclient backend is read-only and cannot write in Phase 2.

### Kaeru stage

Repository: `repos/kaeru`, branch `feature/lidar-support`, commits `e7a9cd5` and `66704e6`
(base `2909a08`). The commits add `board/amazon/board-lidar.c` and
`configs/amazon/lidar_defconfig`, and wire MT8167 into `soc/Kconfig`,
`board/amazon/Kconfig` and `board/amazon/Makefile`. No donor binary is committed.

Build and check commands are recorded in `artifacts/phase-02/kaeru/manifest.json`. The
checker result:

```
python experiments/phase-02/kaeru/check_payload.py \
  artifacts/phase-02/kaeru/lidar-kaeru.bin dumps/20261110-lidar-readback/lk_a.bin
45 PASS lines
all checks passed
```

The corrected image is 221776 bytes, SHA-256
`6743a0bad7e7655c366508a4d3f0b62efd1a81d7f561733c29cc3f5f004a4513`. The donor `lk_a.bin`
is unchanged at SHA-256
`e1f541d1a793ca98d2d995f875d227998bd5ac6368e44d814f63a6515fff9d5c`. The patch targets
`0x41E33C34` from the `platform_init` caller at `0x41E19EE2`, matching the header's
destination address.

The unlock check is at `0x41E0196C`, not the kit's `0x41E01968`. At `0x41E01968` the
bytes are the last dword of a string-offset table; they do not decode as a function
prologue. `0x41E0196C` is `push {r4, lr}; sub sp, #0x100` and calls the `unlock_code`
path. The checker now asserts the prologue bytes, so a shifted donor fails the build check.
The kit's address does not match this readback.

#### Wrong-target build and independent target checks

The image first installed to the unit on 2026-11-14 was a wrong-target build. It reported
237216 bytes, SHA-256
`b084a808b11fa03058f75250648daa27979ed0cc7ec348a98458804db4d2d27f`, with a 22988-byte
Kaeru sub-image. Its stage 1 and stage 2 carry the radar addresses (`0x4BD...` base)
from `radar_defconfig`, not the Lidar addresses in `lidar_defconfig`. It reached the
device because an earlier checker asserted only header, branch and signature structure
and did not check the target.

The root cause was a stale generated config. `lidar_defconfig` omitted
`CONFIG_FASTBOOT_INFO_ADDRESS`, `CONFIG_BOOTMODE_ADDRESS` and
`CONFIG_VIDEO_PRINTF_ADDRESS`. At the time these configs had no Kconfig defaults, so
`make lidar_defconfig` produced empty values, `silentoldconfig` failed to settle the
`.config`, and the build fell back to the previous radar autoconf. The compiler then
read the radar addresses for the MT8167 board.

Two checks now run independently of each other. The defconfig check parses
`lidar_defconfig` and the generated `.config` and requires both to name `AMAZON_LIDAR`
with no `AMAZON_RADAR`. The stage checks require every Lidar address literal to appear
in stage 1 and stage 2 and require the radar literals to be absent. On the installed
image the enhanced checker exits 1 with 22 failures, most of them
`stage1-rejects-radar-target` and `stage2-rejects-radar-target`; on the corrected image
it exits 0 with 45 passes. The wrong-target evidence is preserved under
`experiments/phase-03/logs/kaeru-wrong-target/`.

The fix has two parts. `lib/Kconfig` now gives `FASTBOOT_INFO_ADDRESS`,
`BOOTMODE_ADDRESS` and `VIDEO_PRINTF_ADDRESS` a `default 0x0`, and the board code treats
a zero value as absent. A clean `lidar_defconfig` build now compiles `board-lidar.o`
with the Lidar addresses and produces the corrected image above. The corrected image is
host-verified only; it has not been booted or installed.

Fastboot command coverage is not a gap. `getvar:` belongs to the stock LK, which Kaeru
patches in place; the 7548-byte stage image is only the added code. The stage image's
command table does contain `oem kaeru-version`, registration runs from
`common_early_init()`, and the checker asserts the string is present.

### Koboreru stage

Repository: `repos/amonet-koboreru`, branch `feature/lidar-support`. The build produces a
2448-byte stage image at `0x00101000`. The crafted image is 1115664 bytes, SHA-256
`9e260dff2cb788cdff71ef62669121955ad932933f246d435260fdb7ca11d58f` (stage image
`ca7d8b198f01af693a9eecf69cadd7f9d36844b2917a45079e930f268750b28f`).
`check_tee_image.py` reports 15/15 checks passed.

These hashes are per-build, not reproducible ones: `main.c:15` embeds `__TIME__`. Comparing
builds in this session, every byte outside those time-string digits was identical; size,
structure and every checked field matched.

All four patch sites and the preloader function addresses were derived from the 2019 donor
and agree with the reference kit's hardware-proven image for the same donor. Three values
are witness-only: `PAYLOAD_ADDR`, `BDEV_ADDR` and `DRAM_BUF` come from the kit image, because
the donor has no literal for them; `BSS_START` is the donor startup's bss base. The crafted
sub-image size `0x102C04` and the forged bdev fields match the kit's byte for byte. The checks are
still structural: headers, partition table, embedded stage image, bss, device list and
block-device fields. They do not prove the stage image runs. The image is truncated from the
donor's `0x216C00` bytes to `0x102C04` by design.

The port sources that produce this stage image are uncommitted: the tree is at head `9a617f1`
(`fix Lidar port review findings`) over base `d51af73`, and the deliverable is in
uncommitted modifications to `devices/lidar.c`, `include/devices/lidar.h`, `tee.c`,
`include/preloader.h`, `platform/mt8167/*`, `create_tee_image.py`, plus the deletion of the
repository's `AGENTS.md`. A build from `HEAD` alone would
not reproduce this image. The manifest records the exact provenance: base and head commits
and `sha256(git diff HEAD --binary)` =
`c7bfc1f219c128bbea191754cc08ff109294d678d52d518a51a3556d7a343a35`.

## Donor and preloader decision

Decision: the Lidar chain replaces the stock 2023 preloader with the signed 2019 preloader
from the reference kit (`reference/echo-plus-2-bootchain-v0.2.1/`). It does not port Koboreru
to the stock 2023 BOOT0.

Evidence:

- The 2023 preloader verifies the PL, TEE and LK signatures, enforces RPMB anti-rollback, and
  BROM reports secure boot enabled. The 2019 image contains the same security components:
  a string comparison finds `[ANTI-ROLLBACK]`, `RSA2048`, the ATF/TEE verify-failure messages
  and `sbc_enabled` in both. Verification is therefore not what distinguishes the routes. What
  differs is the layout: bss is `+0x5040` and rodata shifts by `+0x4a4` to `+0x6b8`, so the
  kit's 20 offsets do not transfer, and no patch site has been derived for the 2023 text. The
  stock-BOOT0 port is blocked by missing derived offsets for that layout, not by the mere
  presence of verification.
- Every public Echo MT8163/MT8167 port writes an older preloader to BOOT0: amonet for Dot 2
  (biscuit), Echo 2 (radar), Show 5 (checkers), kamakiri for Dot 3 (donut), and the Plus 2
  Lidar kit. None patches the stock preloader in place. The Koboreru mechanism stays the same:
  the tee1 header sits outside the signature and is loaded before verification, and the Koboreru
  stage makes the preloader's RAM copy start the locally built LK, ATF and TEE in place of the
  stock signed images.

  Sources: [amonet biscuit](https://github.com/R0rt1z2/amonet/blob/mt8163-biscuit/modules/main.py#L256-L294),
  [amonet radar](https://github.com/R0rt1z2/amonet/blob/mt8163-radar/modules/main.py#L256-L294),
  [amonet checkers](https://github.com/R0rt1z2/amonet/blob/mt8163-echo-show/modules/main.py#L252-L287),
  [kamakiri donut](https://github.com/R0rt1z2/kamakiri/blob/mt8516-donut/modules/main.py#L33-L83),
  [Lidar kit install doc](https://github.com/davidwatters/echo-plus-2-unlock/blob/v0.2.1/docs/ONE_SESSION_BOOTCHAIN_INSTALL.md),
  [Echo model matrix](https://github.com/Gamer92000/echo-dot-assist/blob/main/devices/MODELS.md).
- The unit's stock area 1 SHA-256 `d5fc0bbb...` matches the reviewed November 2023 build string
  `20231103_093456`. The kit's allowlist hash `d5c5192e...` covers the 4 MiB composite; the
  difference is the device-unique area 2, not the build.

Write rule: write only BOOT0 area 1, the first 2 MiB of the 2019 image, and keep the unit's
BOOT1. The 2019 image's area 2 is all zeros (0 non-zero bytes). This unit's `boot1.bin` has
1894 non-zero bytes of identity data. The kit's full-4-MiB write would erase that data. The
full-4-MiB path stays a fallback and needs separate approval.

Open Phase 3 decision: the first hardware session's stage-image set. The source-built images
are the deliverable. The kit's images are hardware-proven and remain reference-only; using
them for a bring-up run needs separate approval.

## Review findings and fixes

Two-axis review of the Koboreru commit and the restore tool. Findings applied:

- The restore tool treated `sector0_last` as an optional manifest policy. A writable boot0
  could therefore write the header first. The guard now requires the policy, and the plan
  moves the sector-0 item after every other partition.
- A failure while writing the result file replaced the original apply error. The original
  error is now kept, with the result-file failure attached as a note.
- Journal creation skipped the parent-directory fsync, and a zero-byte journal blocked
  resume. The tool now fsyncs the directory and treats an empty journal as absent.
- The default mtkclient root was a hard-coded home path. It is now derived from the
  workspace layout, with `--mtkclient-root` as the override.
- The Koboreru GPIO placeholder entries used pin 0. Pin 0 is valid, so the IES lookup
  returned the entry and the PUPD path shifted by `pupd - 2` with `pupd == 0`. Both entries
  now match no pin.
- The fingerprint comment sat below `#pragma once` in two headers. It is now first.
- The device header labelled `PAYLOAD_ADDR` as proven and left several OPEN addresses
  unfenced. The comments now match `addresses.md`.
- The TEE entry setter was aliased to the patched loader, so the loader would call itself
  forever. A distinct setter is now derived: `0x00216634` stores the entry and tail-calls
  the trustzone jump setup. The stage image calls it after setting the secmem size, matching
  the kit.
- The Kaeru defconfig used `CONFIG_FASTBOOT_INFO_ADDRESS`, an address the evidence marks as
  inference only. Commit `66704e6` removed it from `lidar_defconfig` and made
  `fastboot_info()` a no-op stub when the config is absent or zero. The later wrong-target
  diagnosis went further and gave `FASTBOOT_INFO_ADDRESS`, `BOOTMODE_ADDRESS` and
  `VIDEO_PRINTF_ADDRESS` a `default 0x0` in `lib/Kconfig`, so an omitted entry can no longer
  leave the generated config unsettled (see "Wrong-target build and independent target
  checks" above).
  The unlock check address remains a define in the board file, matching the sibling
  board style; moving it to a header is a style follow-up.

Open review items, not fixed: duplicated identity-field lists and backend guards, the
redundant `source_offset` plan field, the journal loop variable name, and the backend
partition-size check. They are quality issues, not gate blockers.

## Blockers

None for the host gate. The stage image and crafted image are not hardware-verified, and that
is the Phase 3 question.

## Next actions

1. Request Phase 3 approval. Phase 3 starts with the same-byte restore drill and a stock
   boot confirmation, before any chain write.
2. Decide the first hardware session's stage-image set: source-built images, or the kit's
   hardware-proven images for a reference-only bring-up under separate approval.
3. Keep the donor dumps and kit binaries out of commits. Phase 3 has not started.
