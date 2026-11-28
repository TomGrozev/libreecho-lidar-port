# LibreEcho-Platform `tools/mt8163-arm32` runtime and install map

Scope: everything under `repos/LibreEcho-Platform/tools/mt8163-arm32/` named in the
task, plus the kernel marker driver and its Kconfig. All paths below are relative to
`repos/LibreEcho-Platform/`. Read-only investigation; no device or build was run.

---

## 1. Boot control: BCB, slot switch, success, layouts, running slot

### 1.1 BCB location and byte layout

`tools/mt8163-arm32/ota/libreecho_bootctl.c:18-21`
- `BCB_SECTOR_OFFSET 512`: sector 1 of `misc`.
- `BCB_IN_SECTOR 0x160`: BCB starts 0x160 bytes into that sector.
- Absolute offset into `misc` is `512 + 0x160 = 0x360` (also stated in
  `ota/README.md:37-52`, `drivers/misc/mediatek/echo_fastboot_marker.c:23`,
  `build_recovery_image.py:997`).

7-byte record (`libreecho_bootctl.c:196-201`, `ota/README.md:37-46`):

| byte | mask | field |
|---|---|---|
| 0 | (none) | must be `0` |
| 1-3 | (none) | magic `"ABB"` |
| 4 | (none) | version, must be `1` |
| 5 | 0x0f / 0x70 / 0x80 | slot A: priority / tries / success |
| 6 | 0x0f / 0x70 / 0x80 | slot B: priority / tries / success |

Accessors: priority is the low nibble, tries is bits 4-6 (3 bits), success is bit 7
(`libreecho_bootctl.c:203-222`). `bcb_valid()` requires byte0=0, `"ABB"`, version=1
(`:196-201`).

Selection (`:224-234`): take the higher-priority slot; it is bootable if
`success==1` or `tries>0`; otherwise take the other slot if bootable; else `-1`.
Priority is only a tie-breaker between A and B, so a successful priority-14 fallback
loses to a priority-15 target with tries.

### 1.2 Switching and confirming

`activate()` `libreecho_bootctl.c:305-324`:
- refuses when no selected slot, or when the current slot has `success=0`;
- refuses target == current;
- writes current slot `priority=14, tries=0, success=1`
  (`slot_metadata(14,0,1)`) and target `priority=15, tries=3, success=0`
  (`slot_metadata(15,3,0)`).

`confirm()` `:326-359`:
- target must be `a`/`b` and not already successful;
- requires the target still has tries, or the other slot is successful;
- writes target `priority=15, tries=0, success=1`.
- It deliberately does not require the BCB's next-boot selection to equal the target,
  because LK decrements tries before boot, so the final permitted attempt can run with
  tries=0 while `selected_slot()` already names the fallback. It also does not clear
  the other slot's success bit.

Readback is always part of the write: `write_sector()` opens `O_SYNC`, `pwrite`s the
512-byte sector, `fsync`s, re-reads and `memcmp`s (`:248-265`). `status` prints
`selected_slot`, `inactive_slot`, `slot_suffix`, and priority/tries/success for both
slots (`:267-303`).

### 1.3 `fixed-a` vs slotted A/B

Two layouts are supported; the tool validates the legacy Amonet contract first, then
the pinned one (`libreecho_bootctl.c:154-193`). The names and sizes differ, the device
nodes do not.

| | legacy Amonet | pinned upstream chain |
|---|---|---|
| misc | p8 `misc` 1025 | p8 `misc` 1025 |
| persist | p9 `persist` 32768 | p9 `persist` 32768 |
| slot A store | p10 `boot_a_x` 32768 | p10 `boot_a` 32768 |
| slot B store | p11 `boot_b_x` 32768 | p11 `boot_b` 32768 |
| wrappers | p17 `boot_a` 225280, p18 `boot_b` 225280 | absent |
| userdata | p16 `userdata` 2137088 | p16 `userdata` 2137088 |

Tables: `libreecho_bootctl.c:40-56`. Status output (`:267-303`):

- amonet: `boot_store_mode=slotted`, `slot_a_image=/dev/mmcblk0p10`,
  `slot_b_image=/dev/mmcblk0p11`, `wrapper_a=/dev/mmcblk0p17`,
  `wrapper_b=/dev/mmcblk0p18`. Amonet redirects LK's `boot_a`/`boot_b` reads to the
  `_x` stores, so the OS image belongs in p10/p11 (`ota/README.md:5-30`).
- pinned: `boot_store_mode=fixed-a`, both `slot_a_image` and `slot_b_image` are
  `/dev/mmcblk0p10`, `backup_image=/dev/mmcblk0p11`, wrappers `-`. Measured on
  hardware (issue #231): LK always loads the `boot_a` store and the BCB only selects
  the reported suffix and try accounting, so p11 is a recovery copy, not a second
  executable store (`libreecho_bootctl.c:280-297`,
  `test_issue_231_fixed_boot_store.py:1-18`). The updater implements that in
  `libreecho-update:388-423,425-455`: back up the committed image p10 to p11, then
  write the candidate to p10.

Because the pinned store is fixed-a, `activate b` still selects suffix B; binary
rollback of the image is done by the transaction and runtime copy-back, not by LK.

### 1.4 How the running slot is derived

Preferred source: `/proc/cmdline`, pattern `androidboot.slot_suffix=_([ab])`
(`tools/mt8163-arm32/initramfs/libreecho-init:202-211,1777-1791`,
`:2768-2785`). The underscore is part of the pattern because this LK family was
measured writing the key with an empty value (`init:1770-1776` comment).

Fallback when cmdline does not say: parse `libreecho-bootctl status`'s
`selected_slot=` (`init:1783-1788`, and the OTA worker at `init:2777-2783`). Boot-health
records also call `bootctl status` directly (`init:175-178`). `status [a|b]` accepts a
caller-supplied running slot and then reports that as selected (`bootctl:466-486`).

### 1.5 Partition validation

`validate_partition()` (`bootctl:113-173`) requires:
- the device node is a block device;
- `/sys/class/block/<name>/size` matches the contract exactly, except userdata:
  userdata may be 2137088..33554432 sectors and 2137088 exactly (floor rule)
  (`:84-110`; rationale: stock Radar userdata 2588639, #257 / Platform #249);
- `<sysfs>/uevent` contains a complete `PARTNAME=<name>` line.

A unit matching neither set fails with the Amonet contract diagnostics; probing the
unused layout is silent (`:154-193`).

---

## 2. MT8163-specific storage constants (every one used by these pieces)

These are the constants the runtime currently trusts. Per PLAN Phase 5 they must be
re-measured on MT8167, not copied. The observed MT8163/Radar GPT is in
`initial-install-vm/initial_install_vm.py:28-51`:

| p | first LBA | sectors | name |
|---|---|---|---|
| 1 | 2048 | 2048 | kb |
| 2 | 4096 | 2048 | dkb |
| 3 | 32768 | 2048 | lk_a |
| 4 | 49152 | 10240 | tee1 |
| 5 | 65536 | 2048 | lk_b |
| 6 | 81920 | 10240 | tee2 |
| 7 | 98304 | 20480 | expdb |
| 8 | 118784 | 1025 | misc |
| 9 | 131072 | 32768 | persist |
| 10 | 163840 | 32768 | boot_a / boot_a_x |
| 11 | 196608 | 32768 | boot_b / boot_b_x |
| 12 | 229376 | 32768 | recovery |
| 13 | 294912 | 1572864 | system_a |
| 14 | 1867776 | 1572864 | system_b |
| 15 | 3440640 | 1605632 | cache |
| 16 | 5046272 | 2605023 | userdata (physical) |
| 17 | 0x6D9C00 | 0x37000 (225280) | boot_a wrapper (Amonet only) |
| 18 | 0x710C00 | 0x37000 (225280) | boot_b wrapper (Amonet only) |

Other constants:

| constant | value | anchor |
|---|---|---|
| boot image / slot | 16 MiB = 16777216 bytes = 32768 sectors | `initramfs/libreecho-update:83-84`; `recovery-install/src/.../update-binary:50`; `libreecho-direct-install.sh:67`; `build_install_bundle.py:55` |
| misc BCB | p8, byte 0x360, 7 bytes | `ota/libreecho_bootctl.c:18-21`; `build_recovery_image.py:997` |
| bootloader_message command | p8, byte 0, 32 bytes | `libreecho_bootctl.c:371,440` |
| expdb | p7, 20480 sectors | `libreecho_bootctl.c:373-374` |
| expdb Kaeru header | 48 bytes; magic `88 16 88 58`; MTK payload size LE32; image name `"LK\0"` at +8 | `libreecho_bootctl.c:376-397`; `test_reboot_bootloader.py:23` |
| userdata legacy sizes | 2137088 and 2153472 sectors | `init:16-29`; `libreecho-update:15-30`; `update-binary:48`; `libreecho-direct-install.sh:65` |
| userdata floor/ceiling | 2137088..33554432 sectors | `init:16-17`; `libreecho-update:15-16`; `bootctl:84` |
| userdata non-legacy label | ext4 label `LIBREECHO_DATA` at byte 1024 (magic 0xEF53 @+0x38, volume name @+0x78) | `init:31-48`; `libreecho-update:32-49` |
| TWRP reshape target | 2153472 sectors | `libreecho-direct-install.sh:66`; `update-binary:49` |
| userdata GPT type | `0FC63DAF-8483-4772-8E79-3D69D8477DE4` | `libreecho-direct-install.sh:68` |
| GPT guards | first usable 34, backup reserve 34 | `libreecho-direct-install.sh:69-70` |
| cache | p15, 1605632 sectors (README says 784 MiB) | `recovery-install/README.md:64-70`; `test_direct_userdata_install.py:174` |
| system_a | p13 | `initramfs/libreecho-vendor-import:23-24` |
| OTA public key hex | 32 bytes hex file | `ota/ota-public-key.hex`; `libreecho_update_verify.c` |
| OTA manifest cap | 64 KiB | `libreecho_update_verify.c:9` |
| OTA tar cap | 32 MiB | `libreecho-update:350-351` |
| OTA tar members | exactly `manifest`, `manifest.sig`, `boot.img` | `libreecho-update:351-354`; `ota/README.md:246-252` |
| boot.img magic | `ANDROID!` (`414e44524f494421`) | `libreecho-update:380-382`; `make_ota_bundle.py:180` |
| OTA manifest limit | <=32768 bytes | `initramfs/libreecho-target-manifest:114` |

Caveat worth flagging: `libreecho-init:9-14`, `libreecho-update:7-12` and
`stage_feature_root.sh:9-16` say the one-shot installer writes the
`LIBREECHO_DATA` label, but both current installers format with `-L userdata`
(`update-binary:588`; `libreecho-direct-install.sh:1032`). That is harmless only
because both format to a legacy exact size (2153472), which skips the label check
(`init:51-58`). A non-legacy size (for example stock Radar 2588639) must already carry
`LIBREECHO_DATA`, which neither installer produces. Test matrix documents this:
`test_userdata_geometry.py:120-139`.

---

## 3. First boot, userdata, and what `libreecho-init` does

### 3.1 Who formats userdata

Only recovery installers format it. Nothing in the booted image does.

- Legacy TWRP zip: `format_userdata()` `recovery-install/src/META-INF/com/google/android/update-binary:574-592`.
  - requires the sector count to be exactly one of `2137088 2153472`, else tells the
    operator to run the prepare phase;
  - unmounts `/data` and `/sdcard` first;
  - `mke2fs -F -t ext4 -L userdata`.
- Direct protocol v2: `format_userdata()`
  `recovery-install/src/libreecho-direct-install.sh:1025-1034`; reachable only from
  `phase_initialize` (`:1036-1076`), guarded by `[ "$PHASE" = initialize ]`, and the
  persisted transaction state (`formatting` vs `formatted` at `:1042-1051`).
- Prepare phase reshapes the GPT entry to 2153472 sectors with a single
  `sgdisk --delete --new --change-name --typecode` invocation and requires a reboot
  before formatting (`libreecho-direct-install.sh:954-1022`); legacy equivalent
  `update-binary:450-490`.
- Guards: exact contract sizes and fingerprint (`:734-...`), table and device checks,
  bundle-not-on-userdata (`update-binary:844-855`), digest and data preflight before
  any write, and the exclusive format path above.

### 3.2 `libreecho-init` boot sequence

The initramfs is the complete userspace; there is no pivot root and no overlay. The
script itself runs as PID 1 (the tail keeps a sleep/wait loop alive,
`init:3500-3509`). It creates `/dev` character nodes before first stderr use
(`init:105-132`), then:

1. mount `proc`, `sysfs`, `devpts` if absent (`init:137-139`).
2. wait up to 10 s for `mmcblk0p16`, then `mknod` every `/sys/class/block/mmcblk0*`
   node from sysfs major:minor (`init:943-966`). This happens before
   `userdata_mount()` is defined and used.
3. `userdata_mount()` (`init:969-1001`):
   - calls `userdata_identity` (PARTNAME plus size floor plus label rule, `init:51-58`);
   - rejects with `userdata-size-unsupported` or `userdata-not-libreecho`
     (`init:980-986`);
   - `mount -t ext4 -o rw,nosuid,nodev,noatime /dev/mmcblk0p16 /data`
     (`init:993-1000`); never formats or repairs (`init:964-968` comment).
4. if mounted, run `libreecho-data-cleanup` (advisory) and set `DATA_CLEANUP_OK`
   (`init:1007-1025`).
5. write the boot-health, boot-count and boot-history records with the current BCB
   state (`init:1027-1045`; definitions `:147-320`). `boot-health` records mode (ota,
   first-boot, none), running slot, selected slot, pending slot, both slots'
   priority/tries/success, boot count, and probe verdict.
6. vendor import (`init:1046-1062`, see section 7), hostname, SSH supervisor, image
   profile.
7. start the independent reboot-request supervisor (`init:1095-1126`) which polls
   `/tmp/reboot.request` for `fastboot` or `reboot`.
8. feature transaction activation, TWRP-install adoption, and fresh-install commit
   (`init:1974-2045`), then the service graph.
9. OTA profile only: background `ota_health_confirm_worker` (`init:3434-3443`,
   definition `:2234`); persistent local services wait for
   `/run/libreecho/startup-ready` and `/run/libreecho/ota-health-settled`
   (`init:3456-3495`).

There is no overlayfs use anywhere in these scripts (confirmed by search); persistent
state lives under `/data/libreecho`, image policy under `/etc/libreecho`.

### 3.3 First-boot confirmation

- The image ships `/etc/libreecho/first-install-confirm` with
  `schema=1 / mode=first-install / board=<target>`
  (`build_recovery_image.py:965-967`; validator `init:344-350`).
- On the first OTA-profile boot with no pending OTA, the worker checks the marker,
  requires `SERVICE_PROFILE=production`, derives the selected slot from the BCB,
  refuses an already-confirmed slot, hashes the selected slot store (p10 or p11), and
  writes `/data/libreecho/update/first-install.pending` with `slot` and
  `boot_sha256` (`init:2796-2896`).
- It then waits for `startup-ready` up to 180 s; for a first install a missing marker
  is degraded rather than fatal (`init:3253-3289`), probes `/data`, adb/ffs, web and
  services up to six times requiring three passes, and on success calls
  `libreecho-bootctl confirm <slot>` and records `first-install.confirmed`
  (`init:3337-3366`). A failed first boot is never rebooted, because there is no
  confirmed fallback (`init:3367-3374`).
- Separately, `commit_fresh_install()` completes the feature commit on the installing
  boot, but only after the pending record matches the running slot; it calls
  `bootctl confirm` first and writes `bootctl.readback` (`init:1890-1945`).

---

## 4. Install flow today (TWRP recovery installer) and initial-install VM

### 4.1 Legacy single-run installer (`update-binary`, run via `twrp install`)

`main()` `update-binary:844-913`:

1. requires the bundle directory not to be on userdata (it formats it later).
2. selects `bundle.manifest` by zip name (target-qualified), or the legacy generic.
3. `check_device`: all of `boot_a boot_b userdata misc cache system_a` exist,
   `boot_a` and `boot_b` are exactly 32768 sectors, expdb is only reported
   (`update-binary:277-298`, `:52`).
4. `check_payloads`, `check_target`, `preflight_features`: hashes for the boot
   image, OTA key, install manifest and every feature payload and manifest, target
   `getprop` comparison (override file `/cache/libreecho-allow-cross-target`), all
   before the first write (`:299-...`).
5. if userdata size is exactly `2137088` or `2153472`: format (unmount `/data`,
   `/sdcard`), remount and prove `/data` is the real userdata node, then
   `write_boot_slots` and `stage_features` / `stage_local_package`.
6. `write_boot_slots()` `:593-620`: image must be exactly `32768*512` bytes; `dd
   bs=4096` to `/dev/block/by-name/boot_a` and `boot_b`; `sync`; SHA-256 readback
   must equal the source.
7. stage the signed OTA `manifest` and `manifest.sig`, feature files and the
   `local-install.ota.tar` into `/data/libreecho/update/staging`.
8. emit `/cache/libreecho-install-receipt`; the installer never writes the BCB,
   never activates, never writes expdb, LK, TEE, preloader, GPT, persist, recovery,
   or system_*.
9. first boot adopts and commits the staged tree (`init:1801-1878`), binding the
   staged signed manifest's `boot_sha256` to the hash of the running slot store;
   a mismatch refuses adoption.
10. else prepare-only: `resize_userdata()` to 2153472 and receipt
    `reboot_required=1`; rerun in recovery after reboot.

### 4.2 Direct-userdata protocol 2 (`libreecho-direct-install.sh`)

Four explicit phases (`V3-CONTRACT.md:47-105`), guarded by
`/cache/libreecho-direct/transaction.state` written before the first mutation
(`:1025-1060` region, `V3-CONTRACT.md:130-160`):

1. `prepare`: verify identity, `sgdisk` reshape to 2153472; no data write.
2. `initialize`: the only format path; `mke2fs -F -t ext4 -L userdata`; remount and
   create `/data/libreecho/{update,staging,features,incoming}`.
3. `transfer`: create `incoming/`, check free space for the declared transfer set.
4. `finalize`: validate every uploaded file by digest, write both boot slots with
   `dd bs=4096` plus SHA-256 readback (`:1341-1362`), place the signed manifest and
   hardlink features and local package, then mark `finalized`. No format is
   reachable. `--dry-run` runs all checks and writes nothing.

The browser extracts the helper from the zip on the host (TWRP's toybox `unzip`
extracts nothing), pushes helper and manifest to `/cache/libreecho-direct`, uploads
payloads to `/data/libreecho/incoming`, and reads `receipt.result`, never the
helper exit status (`recovery-install/README.md:150-235`; `V3-CONTRACT.md:6-45`).

### 4.3 Host side and bundle

`recovery-install/build_install_bundle.py` builds `<bundle>/libreecho-install.zip`,
`bundle.manifest`, `SHA256SUMS`, `bundle.json`, the 16 MiB boot image, feature
payloads and manifests, and the OTA key (`build_install_bundle.py:1-60,524-587`). It
fails closed on non-16-MiB boot, missing payloads, no features, traversal paths, or
a bundle that does not match its own manifest; `--check` re-verifies without
rebuilding (`:602-644`). Reproducible bytes.

### 4.4 `initial-install-vm`

A host-side fixture, not device runtime (`initial-install-vm/README.md:1-120`).
It:
- writes the observed physical MT8163 GPT into a 4 GiB sparse eMMC image and a real
  ext4 `userdata` (`initial_install_vm.py:28-51,155-174`);
- runs a deterministic mocked BROM/Amonet install and transforms the GPT to the LK
  logical view (p10/p11 to `*_x`, p17/p18 to `boot_a`/`boot_b`) (`:176-218`);
- applies redirected fastboot writes to both payload slots, validates the exact
  16 MiB Android-v0 and `bootopt` envelope, and reads the payloads back
  (`:202-237`);
- optionally boots the image under QEMU against the eMMC and checks GPT names and
  payload hashes (`:240-298`).
It records `transaction.json`, `emmc.img`, `boot.img`; it does not prove BROM,
Download Agent, RPMB or real silicon.

---

## 5. OTA: bundle, signature, write, confirm, rollback

### 5.1 Bundle contents and signature

Runtime contract (`ota/README.md:244-252`; `libreecho-update:340-386`;
`initramfs/libreecho-target-manifest:113-175`):

- exactly three tar members: `manifest`, `manifest.sig`, `boot.img` (tar listing
  must equal that list, `libreecho-update:351-354`);
- `manifest` is canonical `key=value`, <=32768 bytes for the v3 checker
  (`libreecho-target-manifest:114`); signature is a lowercase hex Ed25519 signature
  over the exact manifest bytes;
- `manifest.sig` is verified by `libreecho_update_verify.c`, a thin libsodium
  `crypto_sign_verify_detached` wrapper against the 32-byte hex public key
  (`:95-133`), staged at `/etc/libreecho/ota-public-key.hex`;
- `boot.img` must be exactly `BOOT_SIZE=16777216`, start with `ANDROID!`, and its
  SHA-256 must equal `manifest:boot_sha256` (`libreecho-update:376-386`);
- the manifest must be `format=libreecho-ota-v3`, `manifest_version=1`,
  board matching `/etc/libreecho/target`, `soc=mt8163`, `architecture=armv7`,
  `image_profile=ota`, `minimum_updater_schema=3`,
  `commit_policy=after-slot-confirm`, exactly the five feature IDs, and the full
  pinned key set (`libreecho-target-manifest:113-175`). v1/v2 are explicitly
  rejected (`libreecho-update:317-338`; `libreecho-target-manifest:120`).

`ota/make_ota_bundle.py` writes legacy v1/v2 deterministic tars
(manifest, manifest.sig, 16 MiB boot.img; v2 uses a control tar from
`feature_manifest.py`) (`:16-20,150-247`). The current device refuses v1/v2, so
the shipping v3 bundle is produced by the release pipeline, not by this script
(`ota/V3-CONTRACT.md:243-250`). This is a documented format split, not a runtime
path.

### 5.2 Write path (`libreecho-update install`)

`install_package()` `libreecho-update:533-591`:

1. `require_userdata`: identity and `/data` actually mounted (`:193-201`); take
   `/data/libreecho/update/install.lock`.
2. `state_write verifying`; `extract_and_verify`:
   - regular package, <=32 MiB, exact members, single-link regular files;
   - Ed25519 verification unless `--allow-unsigned` (which the GitHub fetch path
     never passes; and `install` itself refuses the flag, `:663-668`);
   - manifest format, board, channel and service profile checks; size, magic, hash.
3. v3 only: generation must exist with byte-identical `target.manifest`, verified by
   `libreecho-generation verify`; take the generation `.pin`.
4. `bootctl_status()` `:388-423`: read `selected_slot` and `inactive_slot`; selected
   must be `success=1`; choose the inactive slot's store; on `boot_store_mode=fixed-a`
   set backup=p11, write=p10 (both slots map to p10).
5. `backup_running_boot()` `:425-455`: only fixed-a. SHA-256 the current p10 16 MiB,
   require it equals the `current` generation's signed `boot_sha256`, copy p10 to p11
   with `dd ... conv=fsync`, re-hash p11.
6. `dd if=staging/boot.img of=$write_device bs=4096 conv=fsync`, then SHA-256 readback
   of the written 16 MiB (`:559-562`).
7. write `pending` schema 3 (`slot`, `transaction_id`, `manifest_sha256`) atomically,
   release the pin (`:564-579`).
8. `libreecho-bootctl activate <target>` (`:584`), state `reboot-pending`,
   `UPDATE_READY`.

No other partition is written; userdata and update state are on the existing
filesystem.

### 5.3 Confirmation

`libreecho-update confirm` `:610-628`:
- `pending` must exist;
- `libreecho-feature-transaction verify-running` must pass for the pending slot;
- `libreecho-bootctl confirm <slot>`;
- `libreecho-feature-transaction commit`;
- state `installed`, then relabel a `reboot-pending` check record to `up-to-date`.

The init health worker drives it: on an OTA boot with `pending`, it chooses
`CONFIRM_MODE=ota`, requires the production service profile, and after three stable
probes (data mount, adb/ffs, web, service graph; `init:3288-3336`) calls
`libreecho-update confirm` (`init:3377-3386`). Failure keeps the slot unconfirmed,
writes a restart record, and reboots into the fallback (`init:3388-3421`).

### 5.4 Rollback and fallback

- If the bootloader fell back, the running slot differs from `pending.slot`. The
  worker publishes rollback evidence and either runs the version-matched helper's
  `fallback` under the update locks, or preserves `pending`, `feature-commit` and
  staging for operator recovery (`init:2899-2953`; `ota/README.md:96-242`).
- Terminal records: `rolled-back`, bounded `rolled-back-history.<sha>` retention (16
  records / 8192 bytes), state `rolled-back`, check record relabelled
  `update-held-after-rollback`.
- On fixed-a, a rollback would still leave the candidate in p10, so
  `restore_committed_boot_store()` asks `libreecho-feature-transaction
  restore-boot-store`; only an exact signed-hash match restores p11 to p10, then the
  boot reboots once into the restored image (`init:1948-1972`; issue #231 test
  `test_issue_231_fixed_boot_store.py:1-18`).
- Confirm itself never reboots; the OTA worker does.

---

## 6. Reboot-to-fastboot and recovery entry

### 6.1 No `FASTBOOT_PLEASE` anywhere

- The current source writes no `FASTBOOT_PLEASE` and no expdb byte. Tests pin that
  for init, update, the host helper and the driver
  (`test_issue_195_no_expdb_marker.py:21-56`).
- The development kernel driver
  `drivers/misc/mediatek/echo_fastboot_marker.c` only resets the BCB record at
  misc offset `0x360` to `00 41 42 42 01 7f 7e` (slot A 15/7/0, slot B 14/7/0), on a
  postcore initcall thread, retrying until `/dev/mmcblk0p8` appears, with vfs
  write, fsync and readback (`:23-90,113-124`). It resets both slots to
  `success=0`, which is exactly why PLAN Phase 5 forbids it in the Lidar kernel
  (`PLAN.md:484-489`). Kconfig is `drivers/misc/mediatek/Kconfig:133-139`; Makefile
  `:163`; enabled today only in `arch/arm/configs/mt8163_arm32_defconfig:519`.
- The OTA README documents the same: expdb holds the Kaeru payload, so
  `FASTBOOT_PLEASE` is not a valid marker; the dev kernel may still reset misc BCB
  (`ota/README.md:441-462`).

### 6.2 The actual reboot path

1. Host: `tools/mt8163-arm32/adb-reboot-fastboot.sh` runs
   `adb -s <serial> shell 'printf fastboot > /tmp/reboot.request'`; the device does
   the only flash write (no dd or mmcblk in the host script).
2. Device: `reboot_request_loop()` (`init:1095-1126`) reads and removes
   `/tmp/reboot.request`; on `fastboot` it runs
   `/usr/local/sbin/libreecho-bootctl reboot-bootloader`, and only on success
   `sync` plus `reboot -f`; logs `reboot-request-fastboot-accepted` or
   `...-refused`. The marker `/run/libreecho/recovery-mode` is separate (physical
   button AP).
3. `request_bootloader()` (`libreecho_bootctl.c:414-464`):
   - refuses unless `boot_layout == "pinned"`;
   - `kaeru_payload_present()`: validate p7 `expdb` PARTNAME and size 20480; open
     read-only; read 48 bytes; require `88 16 88 58`, any payload size, and `"LK\0"`
     at +8 (`:376-397`). expdb is only ever opened `O_RDONLY`.
   - read misc sector 0; `misc_command_replaceable()` accepts only an empty command
     or an identical `bootonce-bootloader` (`:399-412`);
   - write `bootonce-bootloader\0...` into the 32-byte command at offset 0, `fsync`,
     read back; then re-read the BCB sector and require it byte-identical
     (`:414-464`).
4. Kaeru consumes `bootonce-bootloader`, enters fastboot and clears it, so
   `fastboot reboot` returns to LibreEcho (`ota/README.md:441-462`;
   `test_reboot_bootloader.py:1-16`).

### 6.3 Recovery access point (button AP)

`recovery-ap/libreecho-recovery-button.c` is an evdev detector, not a bootloader
path. It watches `KEY_HELP` (138) by default, opens the node non-blocking, requests
`CLOCK_MONOTONIC`, reads the held-key bitmap once with `EVIOCGKEY`, and arms
`/run/libreecho/recovery-mode` after a 5000 ms hold; bounds are a 2000 ms startup
press-window and a 12000 ms absolute maximum (`:62-64,225-275,303-380`). It writes
only that tmpfs marker and refuses a non-tmpfs marker path (`:193-...`, `:396-401`).
Build and pinning plus the AP probes are host and overlay pieces
(`recovery-ap/README.md:1-150`). There is no TWRP recovery partition use in this
path.

---

## 7. Vendor import (`initramfs/libreecho-vendor-import`)

- Reads from `system_a` = `/dev/mmcblk0p13`, sysfs `/sys/class/block/mmcblk0p13`
  (`:23-24`).
- Requires `/data` mounted; requires p13 to be a block device with
  `DEVTYPE=partition` and `PARTNAME=system_a` (`:455-459`).
- Mounts it read-only, no atime, exec, suid or device:
  `mount -t ext4 -o ro,noload,nosuid,nodev,noexec "$SYSTEM_A_DEV"
  /tmp/libreecho-stock-system-a` (`:462-464`), then scans four layout prefixes in
  order: `etc/firmware`, `vendor/firmware`, `system/vendor/firmware`,
  `system/etc/firmware` (`:30,266-330`).
- The pinned set is 4 files (spec TSVs under `initramfs/vendor-assets/`):
  `ROMv2_lm_patch_1_0_hdr.bin`, `ROMv2_lm_patch_1_1_hdr.bin`,
  `WIFI_RAM_CODE_8163`, `WMT_SOC.cfg` (`:108-190`; `BUNDLE_ID=mt8163-v181-stock-v1`,
  `:17`).
- Each source is SHA-256 and size checked, copied into a 0700/0600 staging dir,
  re-verified, then installed to `/lib/firmware` mode 0600 by atomic rename, with
  `WIFI_RAM_CODE` as an alias of `WIFI_RAM_CODE_8163` (`:366-414`).
- If no pinned revision matches, an explicit forced-import marker
  (`force-unverified-owner-local-import-v1`, `:466-477`) allows a structurally
  complete set and persists only the hash and size manifest to
  `/data/libreecho/config/vendor-assets.tsv` (`:417-440`). Vendor bytes are never
  redistributed and `system_a` is never written.
- Status is written to `/run/libreecho/vendor-import.status` (`:46-60`).

---

## 8. ARM32 userspace on an ARM64 kernel: what carries over

### Runs unchanged as ARM32 userland under `CONFIG_COMPAT`

These are pure POSIX/shell or portable C with no architecture probe:

- `initramfs/libreecho-init`, `libreecho-update`, `libreecho-vendor-import`,
  `libreecho-target-manifest`, `libreecho-update-fetch`, `libreecho-data-cleanup`,
  and the rest: BusyBox `sh` (`init:1`, `libreecho-update:1`); only `/proc/cmdline`,
  `/proc/mounts`, sysfs and block nodes are used. No `uname`, `/proc/cpuinfo` or
  `/proc/version` appears in any of them (search returned no matches).
- `ota/libreecho_bootctl.c`: POSIX `open/pread/pwrite/fsync` on `/dev/mmcblk0p8`,
  `/sys/class/block/*/{size,uevent}`; no ioctls, no struct ABI, `_FILE_OFFSET_BITS 64`
  only. The 0x360 and 512 offsets are below 2 GiB, so the 32-bit binary is safe.
- `ota/libreecho_update_verify.c`: libsodium, byte buffers; arch-neutral.
- `recovery-install` shell scripts: POSIX/mksh (no bashisms); they depend on
  TWRP-provided `sgdisk`, `mke2fs` and `sha256sum`, not on kernel arch.
- `adb-reboot-fastboot.sh`: host-side bash.
- `libreecho-recovery-button.c`: portable C, but its I/O ABI is 32-bit
  `struct input_event` (16 bytes) and a 32-bit `unsigned long` key bitmap
  (`:19-21,56-67,308-380`). Built as ARM32 it relies on the kernel's 32-bit
  `compat_ioctl` and evdev path; it would be wrong if rebuilt natively for arm64
  without changing the event and timeval layout. `EVIOCGKEY` and `EVIOCSCLOCKID` are
  best-effort and degrade gracefully when rejected (`:32-36,89-123`).
- The install and OTA state machine assumes only the 16 MiB Android-v0 image and the
  byte layout above; it never inspects kernel arch.

### Arch-specific or ARM32-kernel assumptions

- `build_recovery_image.py:2419-2423` rejects any initramfs ELF whose identity is
  not `(class=1, machine=40)` (ELF32 ARM). `verify_recovery_image.py:2215-2222`
  applies the same rule (`:2321-2380` requires the recovery-AP binaries to be
  static ARM32 ELF). A 32-bit userspace satisfies this on an ARM64 kernel; a 64-bit
  userspace would not.
- The v3 target manifest hard-codes `soc=mt8163`, `architecture=armv7`
  (`libreecho-target-manifest:136-141`); `make_ota_bundle.py` writes the same. These
  are image and target identity fields, not runtime probes; they must be re-decided
  for the MT8167/ARM64 profile rather than inherited.
- `drivers/misc/mediatek/echo_fastboot_marker.c` is kernel code: its constants
  (p8, 0x360) are device-specific and its `vfs_write` and `set_fs(KERNEL_DS)` pattern
  depends on the kernel version's `set_fs` support, not on the CPU arch. It must stay
  out of the ARM64 Lidar defconfig per `PLAN.md:484-489`; enabling it would reset both
  BCB success bits every boot and break confirmation.
- `build_install_bundle.py`, `initial_install_vm.py` and the `test_*` files are host
  Python; they encode MT8163 GPT and partition expectations but do not run on the
  device.
- No `/proc/cpuinfo` or `uname -m` check exists on the boot or update path. The only
  `uname` reference in the tree is a qualification metadata field
  (`QUALIFICATION.md:36`), and `/proc/cpuinfo` is used by an unrelated Bluetooth
  test (`bluetooth-runtime-test.sh:10`), not by these runtime pieces.

---

## Architecture in one paragraph

Stock LK reads one 16 MiB Android-v0 image from `boot_a` (p10) on the pinned chain
and consults the 7-byte Amazon BCB at `misc` (p8) plus 0x360 for the reported slot
suffix, priority and tries. The image's initramfs is the whole ARM32 userspace;
`libreecho-init` is PID 1, mounts `/data` from `userdata` (p16) only after
PARTNAME, size and label validation, never formats, records boot health, imports
vendor firmware read-only from `system_a` (p13), and runs the feature and service
graphs. Recovery installs are TWRP shell installers that format ext4 userdata
(after an optional sgdisk reshape) and write both 32768-sector boot stores with
SHA-256 readback; first boot adopts and confirms. OTA is a signed v3 bundle whose
only boot payload is a 16 MiB `boot.img`; `libreecho-update` writes the inactive
store (p10 with a p10 to p11 backup on fixed-a), readback-verifies it, records
`pending`, and calls `libreecho-bootctl activate`, which writes 14/0/1 for the
running slot and 15/3/0 for the target; the next boot's health worker calls
`confirm` (15/0/1) or the bootloader falls back and init finalises a rollback.
Fastboot entry uses Kaeru's one-shot `bootonce-bootloader` at misc+0 after a
read-only expdb payload check; `FASTBOOT_PLEASE` and expdb writes are gone, and the
optional dev kernel marker only resets the BCB retry counters (and is banned from
the ARM64 Lidar kernel).
