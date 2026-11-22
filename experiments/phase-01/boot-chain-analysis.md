# Lidar (Echo Plus 2nd Gen, MT8167) stock boot-chain analysis — Phase 1

Scope: read-only analysis of the 2026-11-10 live readback under
`dumps/20261110-lidar-readback/`. No hardware access. `boot1.bin` was parsed for
structure only; no identity values are reproduced here.

Files and hashes (verified with `sha256sum` on the local dumps):

| file | size | sha256 |
|---|---|---|
| boot0.bin | 2 MiB | `d5fc0bbbc89b7dfaa7ca39fc1d0bc8da0df4a66e2324f3a9742ba70c04f5e327` |
| boot1.bin | 2 MiB | `4c8e02060ab820652000e4ffae90c5554d88230625edc704d269bee3efeb80f3` |
| lk_a.bin | 1 MiB | `e1f541d1a793ca98d2d995f875d227998bd5ac6368e44d814f63a6515fff9d5c` |
| tee1.bin | 5 MiB | `aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e` |
| expdb.bin | 10 MiB | `e5b844cc57f57094ea4585e235f36c78c1cd222262bb89d53c94dcb4d6b3e55d` |

`lk_a.bin` and `tee1.bin` are byte-identical to `dumps/stock/lk_a.bin` and
`dumps/stock/tee1.bin`. `tee1.bin` is **not** the image with hash
`d643f053…` that the reference package calls stock TEE1; it is a different TEE
revision (see TEE build and evidence gaps).

## Boot areas and naming

**Finding: eMMC boot area 1 is the preloader container ("BOOT0" in MediaTek
tools); eMMC boot area 2 is the device identity/calibration store.**

Evidence, `boot0.bin` (2 MiB, boot area 1):

```
00000000: 454d 4d43 5f42 4f4f 5400 0000 0100 0000  EMMC_BOOT.......
00000010: 0002 0000 ffff ffff ffff ffff ffff ffff  ................
```
- `EMMC_BOOT\0` at 0x000, byte 0x0c = 0x01, u32 at 0x010 = 0x200.
- BRLYT table at 0x200: `BRLYT` 0x200, u32 version 0x208 = 1, u32 image
  offset 0x20c = 0x800, u32 image size 0x210 = 0x24600, entry magic `BBBB`
  0x214, entry type 0x218 = 0x00010005, repeated offset/size at 0x21c/0x220.
- At 0x800 sits an `MMM\x01` FILE_INFO block (header size 0x38, span field
  0x820 = 0x23c34), followed by the preloader (`preloader_lidar.bin`, below).
- `stage2.py` in mtkclient parses exactly this: `EMMC_BOOT` → u32 at 0x10 →
  `BRLYT` → u32 at +0xC → `MMM\x01` → length at +0x20, and reads it with
  `type_=1` ("boot1 area") when fetching the preloader
  (`mtkclient/stage2.py:222-234`).

**boot1.bin** does not contain `EMMC_BOOT` and contains no executable image.
It begins `beefdeed2.1\0` + u32 count 0x23 at 0x00c, followed by 33 TLV
records; the first is `board_id` at 0x010 (name[16] + u32 size + u32 type +
u32 0x124 + value). Records are `board_id, serial, mac_addr, mac_sec,
bt_mac_addr, bt_mfg, wifi_mfg, product_name, productid, productid2, bootmode,
postmode, bootcount, manufacturing, unlock_code, miccal.0-6, alscal, KB, DKB,
device_type_id, dev_flags, fos_flags, usr_flags, locale, charger_det, alsparams,
ffs_pin` (offsets 0x010-0x2bd8). Nothing in it is a boot stage.

**"BOOT0" is the 4 MiB pair.** The reference downgrade image
`reference/echo-plus-2-bootchain-v0.2.1/lidar_2019_preloader_downgrade_boot0.bin`
is 4 MiB: first 2 MiB is an `EMMC_BOOT` preloader container (build string
`20190926_195940` at 0x1f2f4), second 2 MiB is all zero. The installer
replaces "full 4 MiB BOOT0". That resolves the naming: MediaTek "BOOT0" =
boot area 1 + boot area 2; the bootable stage lives in area 1.

## BOOT0 / preloader build

Container layout in `boot0.bin`:

| offset | bytes | meaning |
|---|---|---|
| 0x000 | `45 4d 4d 43 5f 42 4f 4f 54 00` | `EMMC_BOOT` tag |
| 0x010 | `00 02 00 00` | BRLYT offset = 0x200 |
| 0x200 | `42 52 4c 59 54` | `BRLYT` |
| 0x208 | `01 00 00 00` | layout version 1 |
| 0x20c | `00 08 00 00` | first image offset = 0x800 |
| 0x210 | `00 46 02 00` | image span = 0x24600 (ends 0x24e00) |
| 0x800 | `4d 4d 4d 01 38 00 00 00` | `MMM\x01` FILE_INFO, hdr 0x38 |
| 0x808 | `FILE_INFO\0\0\0` | block name |
| 0x820 | `34 3c 02 00` | FILE_INFO span 0x23c34 (0x800 → 0x24434) |
| 0x824 | `00 00 04 00` | 0x40000 size limit |
| 0x838 | `MMM\x01`, hdr 0x0c, type 1 | sub-block (value 1 at 0x840) |
| 0x844 | `MMM\x01`, hdr 0x64, type 7 | sub-block (0x90 at 0x848, 0x1388 at 0x898) |
| 0x8a8 | `MMM\x01`, hdr 0x14, type 2 | sub-block (0, 0x10, 0x80) |
| 0x8bc | `MMM\x01`, hdr 0x30, type 8 | sub-block (value 3) |
| 0x8ec | `MMM\x01`, hdr 0x214, type 3 | sub-block; ends at 0xb00 |
| 0xb00 | `00 00 00 00 03 00 00 ea 80 21 10 00 b0 ac 10 00` | preloader code entry |
| 0xcfc | `AND_ROMINFO_v` | ROM info block |
| 0xdd0 | `AND_SECCTRL_v` | security control block |
| 0x1f7cc | `20231103_093456` | build timestamp |
| 0x2420c | `MTK_BLOADER_INFO_v28` | loader-info structure |
| 0x24227 | `preloader_lidar.bin` | image name |
| 0x24434 | first byte of 0xFF padding | end of the stage image |

- Preloader code starts at **0xb00**, not 0x400. 0x400-0x7ff is zero fill:
  `00000400: 0000 0000 …`. The first words at 0xb00 are a reset-vector style
  header (`00000000`, `030000ea` = ARM `b +0xc`, `0x00102180`, `0x0010acb0`).
- Build time string: `0001f7cc: 3230 3233 3131 3033 5f30 3933 3435 36`
  = `20231103_093456`, used by the format string
  `"\n%s Build Time: %s\n"` at 0x1f7c0. **Build date 2023-11-03 09:34:56.**
- `MTK_BLOADER_INFO_v28` at 0x2420c; mtkclient reads the image name at
  +0x1B (`stage2.py:233-235`), which lands on `preloader_lidar.bin` at
  0x24227. `V116` at 0x24264 is a structure marker, not a build number: the
  unrelated `mtkclient/.../preloader_sloane_mt8173.bin` sample carries the
  same `V116`, so it must not be reported as the preloader version.
- The string `0.1.00` at 0x20ac8 sits immediately before the format string
  `PL_VERSION = %s ` at 0x20ad1
  (`00020ac0: … 30 2e 31 2e 30 30 00 50 4c 5f 56 45 52 53 49 4f 4e …`).
  [INFERENCE] `PL_VERSION` is `0.1.00`; this is adjacency, not a parsed field.
- `AND_ROMINFO_v` at 0xcfc:
  ```
  00000cfc: 41 4e 44 5f 52 4f 4d 49 4e 46 4f 5f 76 00 00 00  AND_ROMINFO_v...
  00000d0c: 02 00 00 00 4d 54 38 31 36 37 00 ...              ....MT8167.
  00000d20: 43 55 53 54 ...                                   CUST
  ```
  Version = 2 (0xd0c), platform = `MT8167` (0xd10), project = `CUST` (0xd20).
  The fields at 0xd30-0xd40 (`01`, `0`, `0x2c`, `0x54`, `0xe0`) are not
  decoded; no version semantics are claimed for them.
- Effective image span: 0x800 + 0x23c34 = **0x24434**; the BRLYT nominal
  span of 0x24600 pads to 0x24e00 (0xFF then zero to the end of the 2 MiB
  area). Preloader code+data therefore is 0xb00-0x24433 (0x23934 bytes).

What it is: MediaTek `MT65xx Preloader` (`MT65xx Preloader` at 0x21bea,
`USB CDC ACM for preloader` at 0x21bfb), with RPMB, anti-rollback, seccfg,
RSA2048/PSS, and MMC drivers compiled in.

## LK build

`lk_a.bin` is a single MTK image:

```
00000000: 88 16 88 58 38 3d 03 00 4c 4b 00 00 00 00 00 00  ...X8=..LK......
00000020: 00 00 00 00 00 00 00 00 ff ff ff ff ff ff ff ff  ................
00000200: 07 00 00 ea a3 64 00 ea a9 64 00 ea af 64 00 ea  .....d...d...d...
```
- Magic `0x58881688` at 0x0, size 0x33d38 at 0x4, name `LK` at 0x8
  (`4c 4b 00 00`), header remainder zero, code from 0x200.
- Declared image end = 0x200 + 0x33d38 = 0x33f38.
- Build provenance string at 0x2435b:
  `/mnt/build/workspace/FOS6-mt8167-nightly-build-low-level-images/bootable/bootloader/ufbl-features/project/../features/libtinycrypt/...`
  (repeated for every compiled translation unit). This identifies the LK as an
  MT8167 `ufbl` (U-Boot-derived LK) nightly build, but the checkout has no
  commit id or human version.
- **No plaintext LK version string or version dword exists in the header.**
  Bytes 0x0c-0x27 are zero. `V1.1.4.TB` at 0x2f7a0 belongs to the devinfo blob
  (`devinfo %s data size:%d` at 0x2f7ac), not to LK.
- Trailer at 0x33e34: `4c 4b 00 01` (`LK\0\x01`) followed by 0x100 bytes of
  high-entropy data to 0x33f37. [INFERENCE] this is the signed/hashed footer
  (the preloader verifies `lk_img_size` vs `lk_size`, 0x1c2eb). It is not
  proven to contain the ARB version.
- LK is ARB-aware: it exposes `antirback_pl_version`, `antirback_lk_version`,
  `antirback_tee_version` at 0x2d5cf/0x2d5e4/0x2d5f9 and
  `androidboot.pl_version`, `androidboot.tee_version`,
  `androidboot.lk_version` at 0x29037/0x29055/0x29074.
- A small version-enum table sits at 0x2f814: `"1.2"\0` + 0, `"2.0"\0` + 1,
  `"2.1"\0` + 2, `"3.0"\0` + 3. It is not tied to LK by any string; treat its
  meaning as unknown.
- ARB version value itself is only printed at runtime:
  `[%s] Succeed to pass the LK verification, version of LK is 0x%x.` at
  0x1c423 (preloader) and `Boot Ctrl - Version : %d` at 0x1c523/0x27bfa.

## TEE build

`tee1.bin` is two concatenated signed components, both encrypted:

```
00000000: 88 16 88 58 00 d6 00 00 61 74 66 00 00 00 00 00  ...X....atf.....
00000030: 89 16 89 58 00 02 00 00 01 00 00 00 00 00 00 00  ...X............
0000d800: 88 16 88 58 00 6c 21 00 74 65 65 00 00 00 00 00  ...X.l!.tee.....
0000d830: 89 16 89 58 00 02 00 00 01 00 00 00 00 00 00 00  ...X............
```
- `atf` component: magic 0x58881688, size 0xd600, name at 0x8; secondary
  header magic 0x58891689 at 0x30 (size 0x200, type 1, field 0x10 at 0x44).
  Ends at 0xd800 (2 KiB aligned).
- `tee` component: magic at 0xd800, size 0x216c00, name `tee` at 0xd808;
  secondary header at 0xd830; field at 0xd828 = 0x600000. Ends at 0x224400.
  Everything after 0x224400 in the 5 MiB partition is zero.
- The component is encrypted/high entropy (`EET KTM @` at 0x200 is isolated noise).
  There is no plaintext TEE OS version, build id, or vendor string; a full
  string scan found only `atf` (0x8) and `tee` (0xd808).
- The preloader contains the matching verification/decryption path:
  `Error: fail to verify mtee image header` 0x22bc4,
  `Error: fail to perform pkcs pss verification for mtee image` 0x22d00,
  `verify pkcs#1 pss takes %d (ms)` 0x22d40,
  `Error: fail to calculate gcpu hw sha256 for mtee image` 0x22c80,
  `ATF verify fail` 0x1f741, `TEE verify fail` 0x1f779.
- [INFERENCE] The TEE version compared by ARB is decoded from the
  authenticated mtee header at runtime; it is not recoverable from the raw
  dump without the signing/decryption path.

## Anti-rollback exposure

**Proven from the preloader strings (all offsets in `boot0.bin`):**

| offset | string |
|---|---|
| 0x1bdd8 | `[ANTI-ROLLBACK] Processing anti-rollback data` |
| 0x1be08 | `[ANTI-ROLLBACK] Failed to read block 0` |
| 0x1be30 | `[ANTI-ROLLBACK] PL: %x TEE: %x LK: %x` |
| 0x1be7f | `[ANTI-ROLLBACK] Invalid checksum!` |
| 0x1bec6 | `[ANTI-ROLLBACK] PL version mismatch!` |
| 0x1bf2e | `[ANTI-ROLLBACK] TEE version mismatch!` |
| 0x1bf7b | `[ANTI-ROLLBACK] LK version mismatch!` |
| 0x1bfe9 | `[ANTI-ROLLBACK] Updating RPMB block...` |
| 0x1c011 | `[ANTI-ROLLBACK] Unable to update RPMB block (status)` |
| 0x1c047 | `[ANTI-ROLLBACK] Unable to update RPMB block (write)` |
| 0x1c07c | `[ANTI-ROLLBACK] RPMB block updated` |
| 0x1c0a0 | `[ANTI-ROLLBACK] Updated version: {PL: %x TEE: %x LK: %x}` |
| 0x1f8e6 | `[RPMB] Failed to initialize anti-rollback block` |
| 0x1f917 | `[RPMB] Anti-rollback block initialized` |
| 0x1f93f | `[RPMB] Valid anti-rollback block exists` |

The compared versions are exactly three: **PL, TEE, LK**. They are kept in an
authenticated **RPMB block 0** (read, checksum, compare, write back). Notes:

- `expdb.bin` is 10,485,760 bytes of **0x00 only** (single-value histogram;
  hash above). Blank expdb is consistent with the plan's note, and it proves
  this image held no ARB record at dump time. It does **not** prove ARB is
  inactive: the preloader's ARB state is in RPMB, not expdb.
- `seccfg` is referenced separately (`[%s] seccfg load fail` 0x21394,
  `[%s] SEC CFG is valid. Lock state is %d` 0x229e4). That is lock state, not
  the PL/TEE/LK version table; no version field is proven in it.
- efuse: the live read captured only indices 0x28-0x4f (0x28=<EFUSE_10>,
  0x2d=0x44210000, 0x30=0x00000001, 0x31=0x67810000, 0x34=0x00000003,
  0x3b=0x67810000, 0x3c=<EFUSE_11>, 0x3d=<EFUSE_12>, 0x3e=<EFUSE_13>,
  0x41=<EFUSE_14>, 0x42=0x80020000, 0x43=<EFUSE_15>, 0x44=<EFUSE_16>,
  0x45=<EFUSE_17>, 0x46=<EFUSE_18>, 0x4a=0x1d000000). **No captured byte or
  string ties ARB versions to a fuse.** [INFERENCE] ARB versions are RPMB-only
  on this design, because every ARB message names RPMB and none names efuse.
  Proving the fuse/SBC state needs indices below 0x28 plus the MT8167 efuse
  map, which the capture does not contain.
- [INFERENCE] The RPMB block also gates the preloader's own downgrade: a 2019
  BOOT0 on a device whose RPMB PL version is 2023 would hit
  `PL version mismatch!`. The reference kit replaces BOOT0 with a 2019
  preloader and warns that the device "may fail to boot", which is consistent
  with this gate but does not prove it.

## Can this BOOT0 host a new chain?

What the image proves it enforces:

1. **Each loaded stage is signature-checked.** LK: RSA2048 over SHA-256 with
   PKCS#1 PSS, using a "prod key":
   `RSA2048 signature of LK: (lk_size %d, lk_img_size %d)` 0x1c2eb,
   `[%s] Error: fail to do rsa2048 public key decryption.` 0x1c323,
   `SHA256 of LK:` 0x1c3b5, `[%s] Error: fail to pass pss verification.`
   0x1c3f4, `[%s] LK authenticated with prod key` 0x206c1,
   `[%s] Failed to authenticate LK: %d` 0x206e6.
2. **TEE is verified and decrypted** as an "mtee image" with the same PSS/SHA
   path plus a GCPU hardware hash (strings above). ATF and TEE verification
   failures are distinct (`ATF verify fail`, `TEE verify fail`).
3. **Cert-based loading** exists: `[%s] cert verify, part = %s, img = %s...`
   0x2283c, `[%s] seclib_img_auth_load_sig` 0x22934.
4. **SBC state is a runtime security parameter**, not a build constant:
   `sec params sbc_enabled = %d` 0x20d35, next to `sec params rpmb_state = %d`
   0x20d52.
5. DA verification is separate: `usbdl_verify_da: DA validation disabled`
   0x1c8ba, `DA validation fail` 0x1c984. That governs the download agent in
   BROM/USB download, not the on-eMMC chain.

Consequences:

- Replacing the LK or TEE images while keeping this preloader will fail unless
  the replacements carry a valid MediaTek RSA2048-PSS signature. A custom
  boot chain therefore cannot be installed as another LK/TEE image without
  that signature.
- Replacing the preloader inside BOOT0 (boot area 1) moves the trust decision
  to BROM: BROM must accept the new preloader under SBC/SLA before any of the
  above code runs. The reference kit's approach (whole 4 MiB BOOT0 replacement
  with a 2019 preloader, then Koboreru at the start of `tee1` and Kaeru in
  `expdb`) works only if that preloader accepts images that do not carry its
  expected signatures, which is exactly what the 2019 preloader's verification
  policy determines. That policy is not visible in this 2023 dump.
- `[%s] Tool connection is unlocked` (0x1f7dc) and the "DA validation
  disabled" path show the preloader can run in a tool-friendly state, but
  neither string is evidence that the boot chain itself skips verification.
- [INFERENCE] With SBC enabled and the signature check enforced, this BOOT0
  cannot host a replacement chain. With SBC disabled/unlocked (fuse + seccfg
  state unknown), or via a BROM access path that loads a modified preloader
  into RAM without writing it, hosting is plausible. Neither condition is
  proven here.

## Open evidence gaps

- The efuse read stops at 0x4f and starts at 0x28; indices below 0x28 (the
  usual SEC/SBC/SLA region on MTK) were lost, and no MT8167 efuse map is
  applied. SBC/SLA state is therefore unknown. (Superseded by the addendum:
  the full table 0x00-0x4f was read in a later BROM session, and BROM itself
  reports the derived config.)
- No RPMB read. The PL/TEE/LK ARB versions and the ARB block checksum are not
  in any dump.
- LK's ARB version dword is not located. It is not a plaintext header field;
  the 0x33e34 `LK\0\x01` trailer is unverified as a version carrier.
- TEE version/build id is not recoverable from the encrypted `atf`/`tee`
  components. The preloader prints `[ANTI-ROLLBACK] PL: %x TEE: %x LK: %x` at
  boot, which would give all three values directly.
- `tee1.bin` here (`aa2b92…`) differs from the reference package's recorded
  stock TEE1 (`d643f0…`); at least one of the two is a different TEE revision,
  so the reference's TEE assumptions must not be transplanted.
- The briefing's "preloader from ~0x400" is contradicted by the dump: 0x400 is
  zero fill and the image starts at 0xb00.
- The `AND_ROMINFO_v` tail fields (0xd30-0xd40) and the `AND_SECCTRL_v` block
  at 0xdd0 are not decoded.
- `boot1.bin` was deliberately not dumped into this report; its secret fields
  remain unexamined beyond names/sizes.

## Phase 2 must verify

1. Full efuse read (0x00-0x4f and beyond) and decode SEC/SBC/SLA bits for
   MT8167, so SBC state is proven rather than inferred.
2. Boot the stock device with UART and capture the preloader banner:
   `sec params sbc_enabled`, `sec params rpmb_state`, `SEC CFG ... Lock state`,
   and `[ANTI-ROLLBACK] PL: %x TEE: %x LK: %x`. This yields the real ARB
   versions without needing the RPMB key.
3. Authenticated RPMB block-0 read (or a preloader-side dump) to confirm the
   ARB block layout, checksum, and stored PL/TEE/LK versions.
4. BROM acceptance test on the sacrificial unit: write a BOOT0 with a valid
   layout but altered preloader bytes, and observe whether BROM refuses to
   start it. This is the only direct test of SBC at the BOOT0 level.
5. Locate the LK version field: compare the preloader's printed
   `version of LK is 0x%x` against candidate header/trailer bytes across two
   LK images.
6. Confirm TEE version reporting: boot into the TEE path and compare the ARB
   log's TEE value against the `tee` component header fields (0xd804, 0xd828).
7. Verify sector/geometry assumptions (512-byte sectors, 2 MiB boot areas,
   4 MiB BOOT0) by reading the eMMC CSD/extcsd and comparing with `gpt.bin`.

## Addendum: live BROM session, 2026-11-10

A later BROM session in the same phase produced three facts that narrow items
1 and 7 above. Source logs: `experiments/phase-01/brom-printgpt.log` and
`experiments/phase-01/efuse.log`.

- **Full efuse table.** Indices 0x00 through 0x4f were read. The rows previously
  seen (0x28-0x4f) repeat with the same values; the new low rows are
  0x0=00100000, 0x3=00000327, 0x4=00000500, 0x5=67810000, 0x6=46000000,
  0x8=000000a4, 0x9=b00000b8, 0xb=00040000, 0xc=<EFUSE_1>, 0xd=<EFUSE_2>,
  0x14=67810000, 0x15=000000b3, 0x1f=00cb0000 (as printed; mtkclient prints
  each 32-bit fuse little-endian). No MT8167 efuse map is applied, so no bit is
  named as SEC, SBC, or SLA here.
- **BROM's own security report.** During the handshake BROM printed
  target config 0xe5: SBC enabled True, SLA enabled False, DAA enabled True,
  SWJTAG enabled True, mem read auth True, mem write auth True, cmd 0xC8
  blocked True, root cert required False. This is a fuse-derived value reported
  by the boot ROM, so SBC is on and SLA is off for the device as it stands.
  It does not say what SBC accepts for a BOOT0; item 4 remains the direct test.
- **eMMC geometry.** Boot area 1 and 2 are 0x200000 bytes each, RPMB is
  0x400000, and the user area is 0x1c8000000 bytes (0xE40000 sectors of 512
  bytes). That matches the `gpt.bin` header fields (`first_usable_lba` 0x22,
  `last_usable_lba` 0xE3FFDE, `backup_lba` 0xE3FFFF) and the 2 MiB boot0.bin
  read, so the geometry assumption in item 7 is confirmed from both sides.
  The backup GPT was read at LBA 0xE3FFDF-0xE3FFFF and its entry array matches
  the primary array byte for byte.
