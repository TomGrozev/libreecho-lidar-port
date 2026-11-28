# Lidar boot image: appended DTB inventory

Phase 1, read-only analysis. Source image: `dumps/20261110-lidar-readback/boot_a.bin`,
16 777 216 bytes, sha256 `eec8da659fd81352c62e22eb9e2fac174efd180ab03e5ab6c88e1f0135df090c`
(byte-identical to `dumps/stock/boot_a.bin`).

Everything below was produced by local parsing of that file plus `lk_a.bin`,
`boot_b.bin`, `gpt.bin` and `dumps/stock/cache.bin`. No hardware was touched and no
partition was written. Parsers: `experiments/phase-01/dtb/parse_boot.py` (boot header +
FDT walk), `dtb_diff.py` (variant diff), `lk_probe.py` / `lk_window.py` (LK table
extraction). Raw parser output: `experiments/phase-01/dtb/boot-parse.json`.

## 1. Boot image header

`ANDROID!` magic at 0x000; the 32 bytes at 0x008..0x028 decode as a v0 header.

| Field | Offset | Value |
| --- | --- | --- |
| magic | 0x000 | `ANDROID!` |
| kernel_size | 0x008 | 6 227 381 (0x005F05B5) |
| kernel_addr | 0x00C | 0x40080000 |
| ramdisk_size | 0x010 | 4 117 193 (0x003ED2C9) |
| ramdisk_addr | 0x014 | 0x44000000 |
| second_size | 0x018 | 0 |
| second_addr | 0x01C | 0x40F00000 |
| tags_addr | 0x020 | 0x4E000000 |
| page_size | 0x024 | 2048 |
| header_version | 0x028 | 0 (`dt_size` field, therefore zero) |
| os_version | 0x02C | 0x0E04119C |
| name | 0x030 | empty |
| cmdline | 0x040 | `bootopt=64S3,32N2,64N2 buildvariant=user veritykeyid=id:f3530e18f64d11fc25eb2dd762979f078de990bf` |
| id | 0x240 | `024b43b8 1ac38193 15f3573f 5001f23e 2ef4d056` + zero padding |
| extra_cmdline | 0x260 | empty |

This is an MTK-flavoured Android v0 image: `header_version = 0` means there is no
separate `dtb` section and no `dtb_idx` field. The DTBs are appended inside the kernel
section instead (section 3).

## 2. Section layout

Page size 2048. Offsets are absolute in `boot_a.bin`.

| Range | Size | Content |
| --- | --- | --- |
| 0x000800 | 512 | MTK kernel header: magic 0x58881688, size 0x005F03B5 (6 226 869), name `KERNEL` |
| 0x000A00 | 5 167 882 | gzip stream (`1f\8b\08`), decompresses to 11 981 248 bytes; the image begins with the ARM64 Image header (`ARMd` at +0x38) |
| 0x4EE50A | 1 060 523 | 19 concatenated FDT blobs, no padding between them |
| 0x5F0DB5 | – | end of kernel section (0x800 + kernel_size) |
| 0x5F1000 | 4 117 193 | gzip ramdisk, ends 0x9DE7C9 |
| 0x9DE800 | 1 077 (0x435) | DER X.509 certificate, then zeros to the 16 MiB partition end |

Two facts matter for a reimplementation:

- The gzip stream ends exactly at 0x4EE50A, the first DTB byte. The appended DTB list is
  therefore not "somewhere after the kernel": it starts at the byte after the compressed
  kernel and runs to the exact end of the kernel section. `kernel_size` covers
  MTK header + gzip + all DTBs.
- `second_size` is 0 but there is a 1 077-byte DER certificate at 0x9DE800, exactly at the
  page-aligned offset a v0 parser would call the second stage. A strict v0 parser cannot
  see it. It contains no DTB and is not a second stage.

## 3. The 19 appended DTBs

Every FDT magic hit in the image (19 of 19) parses cleanly; no candidate was rejected.
All blobs share FDT header version 17, `last_comp_version` 16, `boot_cpuid_phys` 0,
`totalsize` equal to the blob length, and are contiguous from 0x4EE50A to 0x5F0DB5.

| # | Offset | Size | Root `model` | Root `compatible` | sha256 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0x4EE50A | 54 242 | Amazon Lidar Proto | `amzn,lidar-proto`<br>`amzn,lidar` | `0d4b9fca8557ca8568e97f52c8dccf91d6b72a06735f945098278ece97bfa6e9` |
| 1 | 0x4FB8EC | 53 982 | Amazon Lidar HVT | `amzn,lidar-hvt`<br>`amzn,lidar` | `50460e09d7033ce776205a163e013ef3fdc92d9bb1122b95f46b80a946d70830` |
| 2 | 0x508BCA | 54 726 | Amazon Lidar EVT | `amzn,lidar-evt`<br>`amzn,lidar` | `8bb44900ed657e9f2545942b2cfa3acb39f40e5fd96addf6ea7255bcb18cf848` |
| 3 | 0x516190 | 53 986 | Amazon Lidar DVT | `amzn,lidar-dvt`<br>`amzn,lidar` | `8067c574ee6ac09511c6689e95ad9be6b812ac5bbe9f1a16204fe6567d7df87c` |
| 4 | 0x523472 | 54 016 | **Amazon Lidar PVT** | `amzn,lidar-pvt`<br>`amzn,lidar` | `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f` |
| 5 | 0x530772 | 53 218 | Amazon Sapphire Proto | `amzn,sapphire-proto`<br>`amzn,sapphire` | `5e12807938e90b14e1697e059672fa36af102e38e92f6bdef9964a9074b16338` |
| 6 | 0x53D754 | 53 214 | Amazon Kyanite Proto | `amzn,kyanite-proto`<br>`amzn,kyanite` | `8639eb35f9949ef4c132cfc6df8ea0d53acec805e829cbef747ca89817bd158f` |
| 7 | 0x54A732 | 50 241 | Amazon Pablo Proto | `amzn,pablo-proto`<br>`amzn,pablo` | `84d874f9fbbb9e3622a9b6a264413c02df5b80602f69d9586f330605e1b99023` |
| 8 | 0x556B73 | 49 645 | Amazon Pablo EVT | `amzn,pablo-pvt`<br>`amzn,pablo-dvt`<br>`amzn,pablo-evt`<br>`amzn,pablo` | `a5da3a8263968acfedc8b0404b6bc8eef870842b28508bce0c6389427d7f8112` |
| 9 | 0x562D60 | 53 812 | Amazon Sapphire HVT | `amzn,sapphire-hvt`<br>`amzn,sapphire` | `3b303edd1fb11ffbb6119875ecf89fd236c2d8f97ad9b62db1255ffbda43ddc2` |
| 10 | 0x56FF94 | 53 932 | Amazon Kyanite HVT | `amzn,kyanite-hvt`<br>`amzn,kyanite` | `5f473ab200a884f2b033a85f49cd58802ca533df0a61335d679262de727ea4e6` |
| 11 | 0x57D240 | 61 892 | Amazon Octave pre-HVT | `amzn,octave-prehvt`<br>`amzn,octave` | `0094643b2fcf8cacb4af7953187aa75b1800db01963fa3e4266d6988c319b849` |
| 12 | 0x58C404 | 61 999 | Amazon Octave HVT | `amzn,octave-hvt`<br>`amzn,octave` | `b23154ac25110ef653258a6628cdceba75d7f75e0490d19c2d2b804f426dcef3` |
| 13 | 0x59B633 | 61 995 | Amazon Octave HVT 2.0 | `amzn,octave-hvt2`<br>`amzn,octave` | `507db4c8b9e6ca9f836abe5bfa20a114d7808da0a0500b4ab2054af0923ff0c6` |
| 14 | 0x5AA85E | 60 488 | Amazon Octave EVT | `amzn,octave-pvt`<br>`amzn,octave-dvt`<br>`amzn,octave-evt`<br>`amzn,octave` | `1c5fb5876d772fb15aa8fab64f8971c5134807dce70b2dd9ba146d585158b05e` |
| 15 | 0x5B94A6 | 60 456 | Amazon Octave PRQ | `amzn,octave-prq`<br>`amzn,octave` | `d75a48e54cba3d781d6b33208643d775f01f6b46210fdcfb1f6f6784feb81ae9` |
| 16 | 0x5C80CE | 60 515 | Amazon Megalo | `amzn,megalo-prq`<br>`amzn,octave` | `e4bdf6a723cc4d8801cabced0f1f143ffc496b3a59295ffbe3d88462b8f96b26` |
| 17 | 0x5D6D31 | 53 256 | Amazon Sapphire EVT | `amzn,sapphire-pvt`<br>`amzn,sapphire-dvt`<br>`amzn,sapphire-evt`<br>`amzn,sapphire` | `6f57a91491d9d3975b24604c6bc15a4b57792660d23d14d0cea572770854a00f` |
| 18 | 0x5E3D39 | 53 372 | Amazon Kyanite EVT | `amzn,kyanite-pvt`<br>`amzn,kyanite-dvt`<br>`amzn,kyanite-evt`<br>`amzn,kyanite` | `30c7a69e98e33a3d2b15bb5c8d509f4f4ee55ba4538c9e4427d7e6bc3daaae8d` |

Extracted blobs: `experiments/phase-01/dtb/dtb_<index>_<offset>.dtb` (local only).

`boot_b.bin` (sha256 `e83621a9df5126a5e57e36fecfc21339ed0054a2e6776397a3ac0149b02e983a`)
carries 17 DTBs, not 19: entries 0..14 identical to the table above, then Sapphire EVT and
Kyanite EVT. Octave PRQ (#15) and Megalo (#16) are absent. Slot A is the newer image.

## 4. The production Lidar DTB

| Property | Value |
| --- | --- |
| Boot image | `boot_a.bin` |
| Index in appended list | 4 |
| Offset | 0x00523472 (5 387 378) |
| Size / FDT `totalsize` | 54 016 (0xD300) |
| End | 0x00530772 |
| sha256 | `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f` |
| Model | `Amazon Lidar PVT` |
| Compatible | `amzn,lidar-pvt`, `amzn,lidar` |
| Local file | `experiments/phase-01/dtb/dtb_04_000523472.dtb` |

The hash was computed both from the extracted file and from the 54 016-byte slice of
`boot_a.bin`; the two match.

The five Lidar variants differ structurally, so the choice is not cosmetic:

| Variant | `uart1@11006000` | `tmp108@49` / `tmp108@4a` on i2c@1100b000 | tweeter thermal zone | thermistor nodes | tsl2540 `als_alg_variant` |
| --- | --- | --- | --- | --- | --- |
| Proto | disabled | present | no | 0,1,2,3 | 0 |
| HVT | okay | present | no | 0,1,2,3 | 0 |
| EVT | okay | present | yes | 0..4 | 0 |
| DVT | okay | absent | yes | 1,3,4 | 2 |
| PVT | okay | absent | yes | 1,3,4 | 3 (+`als_auto_gain`) |

DVT and PVT have identical node sets. They differ only in `model`, `compatible`, the
TSL2540 calibration properties (`als_alg_variant`, `als_auto_gain`, white/black
coefficients). No other structural difference exists between them.

## 5. How the boot wrapper selects the DTB

Selection happens in LK (`lk_a.bin`), not in the kernel and not through cmdline. Evidence,
all offsets inside `dumps/20261110-lidar-readback/lk_a.bin`:

1. Board-id to compatible table at 0x00033020..0x000331A3. Nine records of 43 bytes,
   layout `char board_id_hex[17]; char compatible[26]`:

   | Offset | board_id string | compatible |
   | --- | --- | --- |
   | 0x33020 | `0150001400020018` | `amzn,lidar-pvt` |
   | 0x3304B | `0150001400040018` | `amzn,lidar-pvt` |
   | 0x33076 | `0150000100020018` | `amzn,lidar-hvt` |
   | 0x330A1 | `0150000200020018` | `amzn,lidar-evt` |
   | 0x330CC | `0150001300020018` | `amzn,lidar-dvt` |
   | 0x330F7 | `0150000100040018` | `amzn,lidar-hvt` |
   | 0x33122 | `0150000200040018` | `amzn,lidar-evt` |
   | 0x3314D | `0150001300040018` | `amzn,lidar-dvt` |
   | 0x33178 | `ffffff0000000000` | `amzn,lidar` (generic fallback) |

   Only the PVT rows map to the production compatible; the generic fallback is the last
   row. The 16-character board-id keys match the 16-byte size of the idme variable
   `board_id` declared in LK's idme descriptor table at 0x0002F830 (`board_id`, size
   0x10, followed by `serial`, `mac_addr`, `mac_sec`, `bt_mac_addr`).

2. Log strings that spell out the algorithm:

   | Offset | String |
   | --- | --- |
   | 0x0002C818 | `compatible` |
   | 0x0002C83F | `Found %s match compatible=%s (primary=%s) at %p offset=%d` |
   | 0x0002C87A | `board_id read failed ret=%d` |
   | 0x0002C897 | `Couldn't find any device tree` |
   | 0x0002C8B6 | `Using best matching dtb (primary=%s) at %p match=%d` |
   | 0x0002C90C | `dtb_addr = 0x%08X, dtb_size = 0x%08X` |
   | 0x0002CA69 | `%s: Cannot find device(%s) in dtb` |
   | 0x0002CAB4 | `%s: idme_get_var_external returned(%d) for dt_prop(%s)` |
   | 0x0002C7D8 | `Error: dtb size %d larger than max size %d` |
   | 0x0002C803 | `setup_fdt failed=%d` |
   | 0x0002C640 | `odmdtbo` (plus `load overlay dtbo failed !`) |

3. Mechanism, as read off the above: LK reads the idme variable `board_id`, looks it up in
   the 9-row table to obtain a *primary* compatible (`amzn,lidar-pvt` on a PVT board),
   walks every appended FDT and scores each one by matching root `compatible` entries
   against that primary, then boots the best-scoring blob and passes its address and size
   to the kernel (`dtb_addr`/`dtb_size`). The `offset=%d` in the log line is the index in
   the appended list, not a byte offset. If `board_id` cannot be read, or no DTB matches,
   the `ffffff0000000000` row yields the generic `amzn,lidar`, which every Lidar blob
   carries, so the first Lidar blob (index 0, Proto) would win a first-match tie.
   [INFERENCE] Tie-breaking is first-match because all five Lidar blobs match `amzn,lidar`
   exactly once and the log prints only a match count, not a tie-break rule.

4. The kernel never sees the index. The LK-supplied cmdline recorded in the device's own
   boot log contains no `dtb=` token:
   `console=tty0 console=ttyMT0,921600n1 earlycon=uart8250,mmio32,0x11005000 vmalloc=496M
   androidboot.hardware=mt8167 androidboot.secure_cpu=1 androidboot.unlocked_kernel=false
   androidboot.rpmb_state=1 androidboot.pl_version=0x0001 ... bootopt=64S3,32N2,64N2
   buildvariant=user ... androidboot.serialno=<SERIAL_A>` (977 bytes, stored at
   `dumps/stock/cache.bin` 0x4909AA). Selection is invisible from userspace except through
   the booted DTB's contents.

### Which DTB did this unit actually boot

`dumps/stock/cache.bin` holds a captured kernel boot log (`Linux version 4.4.22+ ...
#1 SMP PREEMPT Wed Aug 22 05:55:47 UTC 2018`, build `NS6501`, `ro.build.lab126.project=
lidar_fireos_ship_6501`, `ro.product.device=lidar`) starting at 0x490000.

The TSL2540 driver echoes a value it read from the device tree:

```
tsl2540 0-0039: als_alg_variant value is 3
```

at `cache.bin` offset 0x49748B. Across the five Lidar DTBs `als_alg_variant` is 0 (Proto),
0 (HVT), 0 (EVT), 2 (DVT), 3 (PVT), so the booted device tree is the PVT one, index 4.
Two weaker signals agree with the DVT/PVT family and exclude Proto (uart1 disabled there):
`11006000.uart1: ttyMT1 at MMIO 0x0 ...` proves uart1 is enabled, and the only lm75 client
is `2-0048` (`tmp112em`), where Proto/HVT/EVT additionally expose `tmp108@49` and
`tmp108@4a` on the same bus.

One log line does not fit: `gpio-privacy: No input event configured` (boot log, timestamp
0.540678) appears for a node that all three late variants (EVT/DVT/PVT) populate with
`gpios`. Since it
contradicts EVT/DVT/PVT equally and contradicts PVT's `als_alg_variant` value, it is
recorded as unexplained and is not used as evidence. [INFERENCE] The driver most likely
tests the parent `gpio-privacy` node for a `gpios` property that no variant defines,
which would make the message variant-independent.

## 6. Confidence

High confidence (directly observed):

- 19 appended DTBs at the listed offsets, contiguous, 0x4EE50A..0x5F0DB5, all parsed with
  version 17 headers; every model and compatible string is quoted verbatim from the blobs.
- The production Lidar tree is `amzn,lidar-pvt`, boot image index 4, offset 0x523472,
  54 016 bytes, sha256 `b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f`.
- Selection is made by LK from the idme `board_id` value via the 0x33020 table; there is
  no dtb index in the header, cmdline, or bootconfig.
- This unit booted the PVT tree, per `als_alg_variant value is 3`.

Medium confidence:

- The exact scoring and tie-break rule of the LK matcher, and the fallback path when idme
  is unreadable, are reconstructed from log strings and the table, not from disassembly.
- The 16-character board-id key layout (`0150 0014 0002 0018` as four 16-bit fields) is
  undecoded; the unit's own `board_id` is not present in any dump we hold, so the idme
  value for this device is not available offline.

## 7. Reproduction

```
python3 experiments/phase-01/dtb/parse_boot.py     # header, layout, 19 DTBs, hashes
python3 experiments/phase-01/dtb/dtb_diff.py       # lidar variant node/property diff
python3 experiments/phase-01/dtb/lk_probe.py       # LK board-id table + selection strings
python3 experiments/phase-01/dtb/lk_window.py      # hexdump of the table and string cluster
```

Outputs: `experiments/phase-01/dtb/boot-parse.json`, `dtb-inventory.json`,
`dtb_diff.txt`, `lk_probe.txt`, `lk_window.txt`, `lk_strings_dtb.txt`,
`kernel-cmdline.txt`. The stock boot log from my unit (2,189 lines) was
excluded from this repository for privacy; only the short quotes in this document
are kept.
