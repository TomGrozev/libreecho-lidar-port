# OTA and install contract: Platform tools and Product producers

Read-only investigation. Paths under `repos/LibreEcho-Platform/tools/mt8163-arm32/` unless marked Product.
No device command ran.

## 1. State left by a successful install

All files are owned by root: recovery and PID 1 run as root. The installers set no umask, so
directories and unsealed files get the recovery default (0755/0644 for TWRP, and the pushed
mode for browser uploads). Only the sealed generation and current pointer have explicit modes.

TWRP `recovery-install/src/META-INF/com/google/android/update-binary`:

| Path | Mode | Content |
|---|---|---|
| `/cache/libreecho-install-receipt` | default | appended `key=value`; final readback `result=installed phase=install userdata_sectors=... reboot_required=1 local_package=... local_install_command=... first_boot=...`, plus `target`, `target_check`, `feature_preflight`, `v3_generation` (`:53,94-108,899-905`) |
| `/cache/libreecho-install.log` | default | human log (`:54`) |
| `/data/libreecho/generations/<tx>/target.manifest`, `.sig`, `COMPLETE` | 0400 | signed v3 manifest, 128-hex signature, manifest sha256 (`:760-800`) |
| `/data/libreecho/generations/<tx>/features/<f>/payload.squashfs`, `manifest.json` | 0400 | exact signed hashes, five features only |
| generation directories | 0500 | sealed (`:798-804`) |
| `/data/libreecho/update/current` | 0600 | transaction id + newline (`:804-807`) |
| `/data/libreecho/update/incoming/local-install.ota.tar` | copied mode | release OTA tar, at most 32 MiB (`:67,812-855`) |
| `/data/libreecho/update/staging` | absent on v3 | v3 path returns before creating it |
| `/data/libreecho/features` | absent on v3 | same |

`/cache` also holds the host-pushed bundle directory, untouched.

Direct install `recovery-install/src/libreecho-direct-install.sh`:

| Path | Mode | Content |
|---|---|---|
| `/cache/libreecho-direct/receipt`, `receipt.buf`, `receipt.tmp` | default | atomic `key=value`; final `result=installed phase=finalize format_state=formatted hardlinked=<n> features=<csv> local_package=<path>` plus protocol/target/release/device digest (`:119-128,260-300,1439-1443`) |
| `/cache/libreecho-direct/transaction.state` | default | `protocol,target,release,bundle_manifest_sha256,device_digest,format_state=formatted,phase=finalized` (`:762-789`) |
| `/cache/libreecho-direct/install.log`, `upload-index`, `feature-plan`, `mke2fs.out` | default | run evidence (`:119-128`) |
| `/data/libreecho/incoming/<name>` | pushed mode | upload landing zone, retained as hardlink source (`:1035-1049`) |
| `/data/libreecho/generations/<tx>/...` | 0400 files, 0500 dirs | same sealed tree (`:1225-1239`) |
| `/data/libreecho/update/current` | 0600 | transaction id (`:1238-1241`) |
| `/data/libreecho/update/incoming/local-install.ota.tar` | pushed mode | hardlink (`:1393-1399`) |
| `/data/libreecho/update/staging`, `/data/libreecho/features` | empty 0755 | created at initialize (`:1067-1069`) |
| `/data/libreecho` root | default | initialize creates it |

No install path writes `update/pending`, `feature-commit`, `installed`,
`committed-manifest`, or `generations/<tx>.pin`. The booted image writes those later.

What first boot needs:

- `adopt_staged_local_install` (`initramfs/libreecho-init:1801-1878`) requires
  `update/staging/manifest` and a `staging/features/` directory, no
  `feature-commit`/`pending`/`installed`, and the staged `boot_sha256` equal to the sha256 of
  the running slot device. The v3 installers create neither, so this function is a no-op for
  a v3 install.
- `commit_fresh_install` (`:1890-1950`) requires `update/pending` and `update/feature-commit`,
  no `installed`/`committed-manifest(.sig)`, pending slot equal to the running slot, a
  successful `libreecho-bootctl confirm`, and `staging/bootctl.readback`. It then runs
  `commit-after-confirm` and `activate-committed`. It is called only from the legacy schema-2
  branch (`:2039-2042`), not the v3 branch (`:1974-2004`). A v3 install therefore activates
  the committed generation directly and leaves confirmation to the first-install worker.
- `libreecho-generation verify` (`initramfs/libreecho-generation:169-188`) requires
  `target.manifest`, `target.manifest.sig`, `COMPLETE`, and exactly the five
  `features/<f>/{manifests,payloads}` entries, with matching hashes, no symlinks, and
  `transaction_id` equal to the directory name. It does not read or require a `.pin` file.
  The pin is written by `assemble` (`:297-330`) and removed by install/commit
  (`libreecho-update:577`, `libreecho-generation-transaction:392-394`).
- The `/cache` receipt is not read by the booted image. No file under
  `tools/mt8163-arm32/initramfs/` mentions `/cache`; the installer states the booted OS
  cannot mount it (`update-binary:821-823`).

## 2. Empty, formatted `LIBREECHO_DATA` userdata, no staged tree

Init identifies userdata by `mmcblk0p16`, `PARTNAME=userdata`, size rules and ext4 label
`LIBREECHO_DATA` (`libreecho-init:9-58`), then mounts it (`:969-1000`). Failure leaves
`DATA_MOUNTED=0`; adbd still starts before this point (`:748-900`).

- `--image-profile development`: adbd, FunctionFS and the USB/TCP policy start regardless of
  data. The OTA health worker is disabled (`:3401-3413`), so no slot confirmation ever runs.
  The image reaches `adb shell`. The web graph starts if the UI bundle is present. A later
  `libreecho-update install` uses `bootctl_status`, which dies `current_slot_not_confirmed`
  when the running slot has success=0 (`libreecho-update:400`). A development image
  therefore needs an explicit BCB confirmation before any OTA install.
- `--image-profile ota`: the health worker runs. With no pending it chooses first-boot only
  when the image's `/etc/libreecho/first-install-confirm` matches the target and the service
  profile is production (`init:2780-2830`; marker written by
  `build_recovery_image.py:965-969`). It records `first-install.pending`, waits for
  startup-ready, then needs three passing probe rounds (`:3253-3347`). If the probes pass it
  confirms the slot and records `first-install.confirmed`.
- A local `libreecho-update install PACKAGE` on empty data fails at
  `generation_manifest_mismatch`, because it requires an already published
  `generations/<tx>/target.manifest` matching the package (`libreecho-update:533-548`).
  `libreecho-update-fetch install` succeeds because it downloads the control tar, verifies
  it, then runs `libreecho-generation assemble` to publish the generation before calling
  `libreecho-update install` (`libreecho-update-fetch:1290-1315`). Its install also requires
  a confirmed running slot (`libreecho-update:400`). `libreecho-generation verify` does not
  refuse for a missing pin; only `assemble` creates the pin.

So an ota-profile image with UI and adbd can reach shell and confirm first boot; it cannot
install a standalone local package until something publishes that package's generation, and
it cannot install anything while the slot is unconfirmed.

## 3. OTA v3 bundle production

Device-required tar: exactly `manifest`, `manifest.sig`, `boot.img`, regular files, boot 16 MiB
(`libreecho-update:313-340`).

Manifest keys, in this exact canonical order (`libreecho-target-manifest:108-150`):

```
format=libreecho-ota-v3
manifest_version=1
board=<target>
soc=mt8163
architecture=armv7
image_profile=ota
transaction_type=system
transaction_id=<txn-...>
release=<token>
version=<token>
update_channel=dev|stable
service_profile=production|diagnostic
minimum_updater_schema=3
commit_policy=after-slot-confirm
boot_filename=boot.img
boot_size=16777216
boot_sha256=<hex64>
feature_ids=airplay2,tts,wakeword,stt,assistant
feature_<f>_asset, _size, _sha256, _manifest_asset, _manifest_size,
feature_<f>_manifest_sha256, _daemon_path, _daemon_sha256   (five times)
config_schema=<uint>
```

The five feature IDs are fixed. A bundle cannot declare a feature absent or disabled:
`feature_ids` must equal the exact list, every size must be greater than zero, and every
asset name must be `libreecho-<slug>-base-<f>-<sha>.payload.squashfs` or the matching
`.manifest.json` (`libreecho-target-manifest:151-174`). Product v3 enforces the same five
(`Product build/ci/ota_v3_product.py:17,26`; `build/build.sh:2485-2487` refuses a v3 build
without all five and a production profile). There is no `feature_policy`, `action` or
`activation` key in v3; Product rejects unknown keys (`ota_v3_product.py:96-120`).

Signing key: 64 lowercase hex characters (32-byte Ed25519 seed)
(`Platform ota/make_ota_bundle.py:29-35`). Product also accepts 128 hex
(seed plus public key) (`ota_v3_product.py:235-239`). The shipped public key file is 64
lowercase hex plus newline; the builder and the C verifier enforce that
(`build_recovery_image.py:945-952`, `ota/libreecho_update_verify.c:45-84`). The archive
stores all three members mode 0644 (`ota_v3_product.py:248`).

Verification order on device:

1. `libreecho-update install` checks tar membership, size, signature with
   `/usr/local/libexec/libreecho-update-verify` and `/etc/libreecho/ota-public-key.hex`,
   then calls `libreecho-target-manifest check` (grammar, board, SoC, architecture,
   feature set, asset identities) and compares the signed channel to
   `/etc/libreecho/update-channel` (`libreecho-update:326,533-548`).
2. It requires the generation directory to exist and its manifest hash to equal the staged
   manifest, then runs `libreecho-generation verify`, which calls `target-manifest check`
   again and re-hashes the whole tree (`libreecho-update:546-555`;
   `libreecho-generation:169-188`).
3. It checks boot size, `ANDROID!` magic, and boot sha256, then writes the inactive slot,
   writes schema-3 `pending`, clears the pin, and activates the BCB (`:555-580`).
4. Confirmation later runs `libreecho-update confirm` → `feature-transaction verify-running`
   → `validate_pending` → `verify_generation` → `verify_boot` → required services, then
   `bootctl confirm` and `commit` (`libreecho-update:658-676`;
   `libreecho-generation-transaction:187-201,335-397`).

Product-only: `build/ci/ota_v3_product.py` (v3 emitter and signer), `plan-target-manifest.py`,
`sign_ota_candidate.py` (v2 handoff only), `target_registry.py`/`release/target.schema.json`,
and `build/build.sh:2470-2560`. Platform `ota/make_ota_bundle.py` produces only v1/v2, and
`libreecho-target-manifest` rejects v1/v2 as `legacy_manifest_unsupported`.

Minimal host recipe for a new target and a lab key:

1. Produce `boot.img` (16 MiB, `ANDROID!`).
2. Build a candidate catalog JSON with `features.<id>.payload|manifest = {path,sha256,size}`
   for all five features (`plan-target-manifest.py:17-57`).
3. Run `plan-target-manifest.py --target <id> --candidate-catalog ... --boot-image boot.img
   --release <tag> --version <ver> --update-channel dev --config-schema 1 --output
   target.manifest --asset-output-dir ota-assets` (`plan-target-manifest.py:63-73`).
4. Run `ota_v3_product.py --run <dir> --signing-key <64hex-file> --public-key <64hex-file>
   --expected-key-sha256 <sha> --output <run>.ota.tar`
   (`ota_v3_product.py:226-260`).
5. Put the matching public key in the image as `/etc/libreecho/ota-public-key.hex` and stage
   `libreecho-update-verify`.

The Product emitter is not target-generic today: it hardcodes `soc=mt8163`,
`architecture=armv7`, `service_profile=production`, a `radar-puffin-*` release tag, and a
registry of `radar_puffin`/`biscuit` (`ota_v3_product.py:26-30`; `build/build.sh:487`).
A Lidar bundle needs those constants and the release-tag check changed, or a small standalone
emitter that writes the canonical key list above and signs it with PyNaCl.

## 4. OTA-profile confirmation probes and components

Probe loop, `libreecho-init:3253-3375`:

- wait up to 180 s for `/run/libreecho/startup-ready`; absence is a report only unless
  `HEALTH_STRICT_SERVICES=1` (`:3272-3286`).
- data mount: `/proc/mounts` contains `/data` (`:3288-3291`).
- adb: if the dev TCP transport is configured, `adb_tcp_ready`; otherwise FunctionFS
  endpoints must be ready (`:3292-3297`).
- web: `/etc/init.d/libreecho-web.init status` must pass (`:3298-3301`).
- service graph: `ota_health_services_ready`; a degraded graph is accepted by default and
  only fails under `HEALTH_STRICT_SERVICES=1` (`:3302-3310`). Three passing rounds are
  required before confirm (`:3314-3329`).
- first boot confirms the slot when 3 rounds pass (`:3334-3350`); OTA confirmation calls
  `libreecho-update confirm` (`:3365-3375`). OTA confirmation is production-only; a
  diagnostic OTA boot skips it (`:2808-2815`).

Components needed:

- adbd, busybox, musl loader, bootctl, update verifier, OTA public key, boot envelope,
  zImage, System.map, DTB: all mandatory builder inputs
  (`build_recovery_image.py:2696-2716,2805-2813`).
- FunctionFS/configfs and `/etc/libreecho/adb-transport`: staged with adbd
  (`:580-620`); init uses them at `:733-900`.
- UI bundle: the only source of `/usr/local/sbin/libreecho-web` and
  `/etc/init.d/libreecho-web.init`; without it the web probe and the service graph cannot
  pass (`init:2077-2083`, `:3298-3301`). The bundle must satisfy the startup contract,
  including `mark_startup_ready` and `/run/libreecho/startup-ready`
  (`build_recovery_image.py:1143-1365`).
- mDNS runtime: builder-mandatory for `--service-profile production`
  (`build_recovery_image.py:3001-3006`); init starts it only in production and treats
  failure as degraded (`init:1745-1765`).
- Network tools, SSH, Wi-Fi, feature payloads: optional for the probes. Feature payloads
  are not needed to confirm a slot; a missing generation or degraded feature graph keeps the
  web graph running (`init:1974-2004,2087-2185`). A strict graph would additionally need
  networkd, audiod, micd, ledd, buttond and the payload daemons (`:2139-2169`).

Minimal ota-profile image that can confirm first boot and a later OTA: production service
profile (confirmation is production-only), UI bundle, mDNS runtime, adbd, boot control and
update tools, and a signed v3 manifest target. Add the five feature assets only when the OTA
must actually install them; the bundle itself always carries all five.

## 5. Builder profile values

`build_recovery_image.py:2705-2713`:

- `--image-profile development|ota` writes `/etc/libreecho/image-profile` (`:953-955`).
  `development` disables the OTA health worker and active-device ping; `ota` enables both
  (`init:3401-3424`; `init:1075-1095` reads it). `update-fetch watch` also exits unless the
  profile is `ota` (`libreecho-update-fetch:1317-1320`).
- `--service-profile diagnostic|production` writes `/etc/libreecho/service-profile`
  (`:956-958`; `init:67,561-563`). `production` binds the web UI on `0.0.0.0:8080`, starts
  shared discovery and local services, and is required for first-install/OTA confirmation
  (`init:2196-2233,3401-3424,3455-3482`). `diagnostic` runs `logd timed web` only and skips
  confirmation.
- `--feature-policy exclude|preserve|redistributable|community-noncommercial` writes
  `/etc/libreecho/feature-policy` (`:959-961`; `init:85`). `exclude` requires diagnostic and
  collapses the graph to `logd timed web` (`init:2128-2135`). The other three select the
  payload graph; `preserve`/`community-noncommercial` include wakeword, `redistributable`
  excludes the wakeword payload (`build_recovery_image.py:3009-3045`; `init:2136-2169`).
- `--update-channel dev|stable` writes `/etc/libreecho/update-channel` and rewrites
  `ota-source.conf` (`:962-981`). `dev` requires the adbd transport
  `usb-functionfs-and-tcp` with TCP 5555 and enables the TCP listener; `stable` requires
  `usb-functionfs-only` (`:580-583`; `init:733-738`). The signed manifest channel must equal
  the image channel or install dies `update_channel_mismatch`
  (`libreecho-update:326`).

## 6. Protected partitions

- The two installers write only `boot_a`, `boot_b` and `userdata`
  (`update-binary:31-35,52,281-295,812-900`;
  `libreecho-direct-install.sh:39-48,720-729,1353-1358`). `system_a`, `system_b`, `cache`,
  `misc` are checked for presence only in the TWRP installer (`update-binary:52,281-288`);
  they are never opened for write.
- No flow writes `expdb`, `lk_a`, `lk_b`, `tee1`, `tee2`, `preloader` or `persist`. The TWRP
  installer prints that `expdb` is present and never written (`:293-295`); `bootctl`
  reads `expdb` only to prove the Kaeru payload before a bootloader command
  (`ota/libreecho_bootctl.c:362-430`).
- BCB writes exist only in `libreecho-bootctl`: sector 1 of `misc` at offset 512, bytes
  `0x160..` (`ota/libreecho_bootctl.c:18-21,248-265,352-403`). Callers are
  `libreecho-update install` (`activate`, `:555-580`), `confirm` (`:658-676`),
  `commit_fresh_install` (`init:1917-1922`), and the health worker's first-boot confirm
  (`init:3334-3340`). `reboot-bootloader` additionally writes a one-shot command at
  `misc` offset 0 (`libreecho_bootctl.c:490-510`), but only after proving the Kaeru payload
  in `expdb`; it never writes `expdb` itself.
- The Lidar reboot contract in the assignment (TOPRGU/syscon-reboot-mode, no misc write) is
  not implemented by this MT8163 `libreecho-bootctl`. `init`'s reboot supervisor calls
  `bootctl reboot-bootloader` (`init:1095-1120`), so a Lidar port must replace that path
  rather than inherit it.
