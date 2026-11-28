# Phase 1 notes: live read-only boot-chain inventory

Date: 2026-11-10. Device: Echo Plus 2nd Gen, codename Lidar, MT8167, eMMC.
Purpose: record a read-only inventory of the stock boot chain before any write is planned.
All work in this phase was read-only. No partition was written, erased, or formatted, and the
device was not reset by this session.

## Tool and evidence trail

My mtkclient checkout at `mtkclient/` (commit `118a000a83ea31c4f427fe5225abfe964546e05e`,
with a local patch to `mtkclient/Library/DA/xflash/xflash_lib.py` that forwards DA log frames and
relaxes status parsing) and its virtualenv were used unchanged. Command syntax comes from that
tool's own `--help` and read implementation; no new syntax was invented.

- `experiments/phase-01/read-inventory.sh` records every read command used.
- `experiments/phase-01/prior-mtkclient-printgpt.log` is a copy of `mtkclient/logs/log.txt` from
  my earlier successful session. It contains `BROM mode detected.` (line 191), the Kamakiri
  BootROM handshake, and the patched-loader handshake.
- `mtkclient/hwparam.json` and `mtkclient/.state` from that session record `hwcode` `0x8167`
  (33127), `flashmode` `XFLASH`, `flashtype` `emmc`, `flashsize` 7650410496, and the target config
  (`sbc` true, `sla` false, `daa` true, `memread`/`memwrite` true).
- The live reads below reused the download agent that session left running (the device enumerated
  as `0e8d:2001` on USB, not `0e8d:0003`). `mtkclient printgpt` connected to it directly.
- Each read command is a separate mtkclient invocation. The tool writes `hwparam.json` and
  `.state` next to its working directory and does not rewrite them while the same DA is resident.

## Reads

New device-read directory: `dumps/20261110-lidar-readback/`.

```
mtkclient/.venv/bin/python mtkclient/mtk.py printgpt
mtkclient/.venv/bin/python mtkclient/mtk.py r gpt <out>/gpt.bin
mtkclient/.venv/bin/python mtkclient/mtk.py r tee1,expdb,lk_a,lk_b,boot_a,boot_b,misc \
    <out>/tee1.bin,<out>/expdb.bin,<out>/lk_a.bin,<out>/lk_b.bin,<out>/boot_a.bin,<out>/boot_b.bin,<out>/misc.bin
mtkclient/.venv/bin/python mtkclient/mtk.py r boot0 <out>/boot0.bin --parttype boot1
mtkclient/.venv/bin/python mtkclient/mtk.py r boot1 <out>/boot1.bin --parttype boot2
```

MediaTek's `BOOT0` is eMMC boot area 1 (mtkclient `--parttype boot1`, full 2 MiB area) and
`BOOT1` is eMMC boot area 2 (`--parttype boot2`). `boot0.bin` holds the preloader (`EMMC_BOOT`
tag at 0x0, `BRLYT` BROM layout header at 0x200, `AND_ROMINFO_v`/`MT8167` at 0xcfc). `boot1.bin`
starts `beefdeed2.1` and holds manufacturing identity and calibration data. That file is local
only and is not described in detail here.

After the user power-cycled the device with the action button held, a fresh BROM session ran:

```
mtkclient/.venv/bin/python mtkclient/mtk.py printgpt            # > brom-printgpt.log
mtkclient/.venv/bin/python mtkclient/mtk.py ro 0x1C7FFBE00 0x4200 <out>/gpt_backup.bin
mtkclient/.venv/bin/python mtkclient/mtk.py da efuse            # > efuse.log
```

`rs` is unusable in this checkout because its subparser never declares the output filename; `ro`
takes a byte offset and length instead. The offset 0x1C7FFBE00 is LBA 0xE3FFDF, the first sector
of the backup partition-entry array, and 0x4200 bytes cover 33 sectors up to the backup header at
LBA 0xE3FFFF.

## Hash comparison with the old stock dump

| File | Result |
| --- | --- |
| boot_a.bin, expdb.bin, lk_a.bin, misc.bin, tee1.bin | identical SHA-256 to `dumps/stock/` |
| gpt.bin | `dumps/stock/gpt.bin` is 16896 bytes; the refreshed read is 90112 bytes. The first 16896 bytes are identical, the rest is zero padding. GPT header fields unchanged. |
| gpt_backup.bin | `dumps/stock/gpt_backup.bin` is byte-identical to `dumps/stock/gpt.bin`, so the old file is a second read of the primary table at LBA0, not the backup table. The new read starts at LBA 0xE3FFDF and its header at LBA 0xE3FFFF carries `my_lba` 0xE3FFFF and `alternate_lba` 1; its entry array is byte-identical to the primary array. The GPT is unchanged on both copies. |
| boot0.bin, boot1.bin, lk_b.bin, boot_b.bin | no copy in the old stock dump; new reads |

`tee1.bin` is `aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e`, matching the hash
recorded in `PLAN.md`. `expdb.bin` is blank (zeros and 0xFF), consistent with the plan's note that
the reference expdb was empty. The device is therefore in unmodified stock state for every
partition compared.

Full sizes and SHA-256 for every file: `experiments/phase-01/manifest.json` and
`experiments/phase-01/hashes.txt`.

## Immutable stock boot-chain backup

`dumps/20261110-lidar-readback/stock-boot-chain-backup/` holds `boot0.bin`, `tee1.bin`,
`expdb.bin`, `gpt.bin`, and `gpt_backup.bin` as byte-identical read-only copies (mode 444) with a
read-only `SHA256SUMS`. These are the Phase 2/3 restore sources. They are local only.

## Analysis results

- Boot image, appended DTBs, and DTB selection: `experiments/phase-01/dtb-analysis.md`.
  The production tree is `amzn,lidar-pvt` (index 4 in `boot_a.bin`, offset 0x523472, 54016 bytes,
  SHA-256 `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f`). LK selects it from
  the `idme` `board_id` through a table at `lk_a.bin` 0x33020. The unit's boot log shows the PVT
  tree was active (`tsl2540 ... als_alg_variant value is 3`).
- `boot1.bin` carries a `board_id` whose value equals the PVT row of the LK table at 0x3304B
  (the row that maps to `amzn,lidar-pvt`), which agrees with the boot log. This closes the open
  question of the device's own board_id; the exact value is identity data and stays out of
  reports.
- Preloader build, LK and TEE builds, and anti-rollback exposure:
  `experiments/phase-01/boot-chain-analysis.md`.
- Full efuse table indices 0x00-0x4f: `experiments/phase-01/efuse.log`. This closes the partial
  capture from the first session. The values still need an MT8167 efuse map before any bit is
  named; nothing in the table is called a security bit here.
- Live BROM geometry from `brom-printgpt.log`: eMMC ID `Q2J95E`, boot areas 0x200000 each, RPMB
  0x400000, user area 0x1c8000000 (7,650,410,496 bytes, matching `hwparam.json`).

## Gate status

The Phase 1 gate holds: BOOT0, stock LK, and stock TEE are now known from live reads, and no
offset is treated as final. No write plan exists.

Checklist status:

- [x] `experiments/phase-01/` and a new device-read directory created.
- [x] My mtkclient commands recorded; no invented syntax.
- [x] BROM entry at `0e8d:0003` with the action button: captured live in `brom-printgpt.log`,
      which logs `BROM mode detected.` and the Kamakiri handshake for this session.
- [x] `hwcode` `0x8167` printed live in the same session (`HW code: 0x8167`), alongside target
      config 0xe5: SBC enabled True, SLA False, DAA True, mem read/write auth True.
- [x] BOOT0, BOOT1, refreshed GPT, tee1, expdb, lk_a, lk_b, boot_a, boot_b, misc read.
- [x] BOOT0, tee1, expdb, GPT saved as the immutable backup.
- [x] Refreshed images compared against the old dump hashes.
- [x] BOOT0 build and anti-rollback exposure analysed (`boot-chain-analysis.md`).
- [x] Production Lidar DTB identified (index 4, `amzn,lidar-pvt`).
- [x] Manifest with sizes and SHA-256 produced.
- [x] Backup GPT read (LBA 0xE3FFDF-0xE3FFFF) and checked against the primary GPT entries.
- [x] Full efuse table 0x00-0x4f captured to `efuse.log`.

## Device state after this phase

The last command, `da efuse`, closed the download agent on exit, so the device enumerates in
preloader mode again (`0e8d:2001`) and needs another action-button power-cycle before any further
read. Nothing was written at any point, and the device was not reset by any command in this phase.

Remaining read-only gaps, all scheduled for later phases and none blocking the Phase 1 gate:

- RPMB block 0 holds the PL/TEE/LK anti-rollback versions and has not been read.
- The efuse table lacks an MT8167 map, so SBC/SLA fuse bits are not named; the live BROM target
  config is the stronger current evidence (SBC True, SLA False).
- UART output from a stock boot would print the ARB versions directly; no UART capture exists yet.

## Phase 0 note

Phase 0 ran after this phase, on 2026-11-10; its record is `experiments/phase-00/notes.md`. The
gap noted during Phase 1, with only `repos/LibreEcho/` cloned and no `feature/lidar-support`
branches, is closed there: the four required repositories are cloned on that branch, and
`repos/LibreEcho/` is clean at `4f5445934679d68863fc0c723b990326fc9ff3d1`.
