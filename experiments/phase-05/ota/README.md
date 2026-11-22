# Lab OTA v3 chain for Lidar

Host-only experiment. Nothing here ran against a device. It produces a v3
`target.manifest`, its Ed25519 signature, an `.ota.tar` in the shape
`libreecho-update` accepts, and the staged generation tree the host installer
would leave on userdata.

Paths are relative to the workspace root `/workspace/libreecho`.

## Lab key

`artifacts/phase-05/ota/lab-key/` (never in a source repo):

| File | Mode | Content |
|---|---|---|
| `ed25519-seed.hex` | 0600 | 32-byte Ed25519 seed, 64 lowercase hex plus newline |
| `ed25519-public.hex` | 0644 | 64 lowercase hex plus newline |

The original lab key (`25be6d6b…b30a9a7d`, file sha256 `420e9763…5b724f28`) was lost
with `artifacts/phase-05/` and its seed is unrecoverable. The lab key was rotated on
2026-11-22 (step 37, `experiments/phase-06/hw-20261121/step37-rekey/`). The durable
copy of the new key lives in `keys/ota-lab/` (workspace-local, never committed).

* public key hex: `42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18`
* public key file sha256: `3efab6b623594c5ea582e2d40f3bda0ec224702593f91fe4acaee4d457b67e0a`

Images built before the rotation carry the old public key and can no longer verify
new bundles; rebuild them from this directory's scripts with the new key present.

Generated with `repos/LibreEcho-Platform/tools/mt8163-arm32/ota/generate_ota_key.py`.
A Lidar image needs this public key copied to `/etc/libreecho/ota-public-key.hex`
at image build time (`tools/mt8163-arm32/build_recovery_image.py:945-952` enforces the same format).

## Feature assets

Source is the published dev release
`radar-puffin-build-65bc886-7892d5b54f009bc6-f9910964ec9928af`
(`https://github.com/aslater3/LibreEcho/releases/download/<tag>`). Its signed
v3 manifest is the trust anchor.

`fetch_lab_assets.py` verifies the signature over
`upstream/upstream-target.manifest` with the released
`*-ota-public-key.hex`, then downloads the five payloads and their feature
manifests named by that signed manifest and checks every size and sha256. The
provenance record is `artifacts/phase-05/ota/assets/provenance.json`:

* upstream manifest sha256 `8160d7c2043e1a6ce1949164d1207564fbd06b255129b7ee168186c87631bf13`
* upstream public key file sha256 `524c2b6343438b6ccffca8a8c7f0b9f36e6ec9a2ee37424364b6bfeef96d7f40`
* payload bytes are identical between the `radar-puffin` and `biscuit` asset
  sets of that release, so they are target-independent armv7 userspace, not a
  per-target build. The lab manifest therefore reuses those bytes and hashes
  and only changes the content-addressed asset prefix from `radar-puffin` to
  `lidar`, as `libreecho-target-manifest` requires.
* the feature manifests carry the daemon path and daemon sha256, so the lab
  manifest takes those values from the signed payload metadata instead of
  inventing them.

Total asset set: 235,638,074 bytes.

## Emitter

`make_lab_ota.py` writes the canonical key order of
`tools/mt8163-arm32/initramfs/libreecho-target-manifest:108-174` for
`board=lidar soc=mt8167 architecture=armv7 image_profile=ota`, signs it, packs
`manifest`, `manifest.sig`, `boot.img` (mode 0644, USTAR, that order) and
seals a generation tree (`target.manifest`, `target.manifest.sig`, `COMPLETE`,
`features/<f>/{manifest.json,payload.squashfs}`, files 0400, dirs 0500).

Product reuse was checked first and rejected: `release/targets/` has no Lidar
descriptor, `build/ci/target_registry.py:7` lists only `radar_puffin` and
`biscuit`, and `build/ci/ota_v3_product.py:66` hardcodes `soc=mt8163`. No
argument or import makes those emit `board=lidar soc=mt8167`. The emitter
duplicates only the canonical field list and the Product transaction-id
formula, so no Product or Platform file changed.

The lab bundles were emitted from the built images (`lab-v1` from the v1 image,
`lab-v2` from the v2 OTA payload image):

```sh
uv run --with pynacl python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image artifacts/phase-05/images/boot-lidar-v1.img \
  --feature-catalog artifacts/phase-05/ota/lab-run/feature-catalog.json \
  --release lidar-lab-v0.2.5 --version 0.2.5 \
  --update-channel dev --service-profile production --config-schema 1 \
  --signing-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output artifacts/phase-05/ota/lab-v1/lidar-lab-v0.2.5.ota.tar

uv run --with pynacl python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image artifacts/phase-05/images/boot-lidar-v2.img \
  --feature-catalog artifacts/phase-05/ota/lab-run/feature-catalog.json \
  --release lidar-lab-v0.2.6 --version 0.2.6 \
  --update-channel dev --service-profile production --config-schema 1 \
  --signing-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output artifacts/phase-05/ota/lab-v2/lidar-lab-v0.2.6.ota.tar
```

Assets are fetched by `fetch_lab_assets.py` from the upstream release base above into
`artifacts/phase-05/ota/assets`; the catalog records their hashes.

The catalog maps each feature to its payload and manifest path plus the hashes
from the signed upstream manifest; the emitter re-hashes the files and fails on
any mismatch. `--update-channel dev` must equal the image's
`/etc/libreecho/update-channel` or install dies `update_channel_mismatch`.

## Host verification (run, passing)

```sh
cc -O2 -Wall -o artifacts/phase-05/ota/lab-run/libreecho-update-verify \
  repos/LibreEcho-Platform/tools/mt8163-arm32/ota/libreecho_update_verify.c -lsodium

G=artifacts/phase-05/ota/lab-v2/generations/txn-12fb3f0f4e9fd5a6c15b948f
artifacts/phase-05/ota/lab-run/libreecho-update-verify \
  artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  "$G/target.manifest" "$G/target.manifest.sig"     # ota_manifest_signature=PASS
```

* appended byte: `ERROR: OTA manifest signature rejected` (exit 1)
* one-byte `release=` change: same rejection (exit 1)
* `libreecho-target-manifest check`: exit 0. The script hardcodes
  `BB=/bin/busybox`, and the host has no `/bin/busybox`, so the check ran from a
  copy at `/tmp/lidar-target-manifest-shim` with line 3 changed to
  `${BB:-/tmp/bb/busybox}` and `/tmp/bb/busybox` as an `exec "$@"` shim. The
  repo file is unchanged. The real host busybox wrapper belongs to
  `experiments/phase-05/host-tests.md` (other agent).
* `libreecho-generation verify` over the whole tree: exit 0, same shim method
  (`TARGET_MANIFEST` pointed at an executable `/bin/sh` wrapper for the shim).

Device-side equivalents need no shim.

## Delivery route on Lidar (USB adb, no network)

`adb reverse` is not available with this adbd. The pinned source is AOSP
`platform/system/core` commit `4f247d753a8865cd16292ff0b720b72c28049786`
(2012-12-19, `tools/mt8163-arm32/adbd/SOURCE.lock`); its `adb/*.c` has no
`reverse` service, which `adb reverse` needs. The LibreEcho patch also removes
the device local smart-socket listener. `libreecho-generation assemble` would
instead need HTTPS to one of its allowlisted release bases, so a host HTTP
server cannot serve it either.

The route is push the sealed generation tree, then install from a pushed
package. `libreecho-update install` only requires the published generation to
exist and hash-match; it never reads the feature assets from the package.

Device preconditions: the image is `--image-profile ota --service-profile
production` so first boot confirmed the running slot (`libreecho-bootctl
status` shows `slot_<selected>_success=1`), and `/data` is mounted
(`/proc/mounts` has `/data`). adbd runs as root from init
(`initramfs/libreecho-init:749-792`), so the shell writes are root writes.

Host:

```sh
serial=<adb serial>
tx=txn-12fb3f0f4e9fd5a6c15b948f
run=artifacts/phase-05/ota/lab-v2
adb -s "$serial" push "$run/generations/$tx" /data/libreecho/generations/
adb -s "$serial" push "$run/lidar-lab-v0.2.6.ota.tar" \
  /data/libreecho/incoming/local-install.ota.tar
```

Device, as root:

```sh
tx=txn-12fb3f0f4e9fd5a6c15b948f
g=/data/libreecho/generations/$tx
chmod 0400 "$g/target.manifest" "$g/target.manifest.sig" "$g/COMPLETE" \
  "$g"/features/*/manifest.json "$g"/features/*/payload.squashfs
chmod 0500 "$g" "$g/features" "$g"/features/*
/usr/local/sbin/libreecho-generation verify "$g"
/usr/local/sbin/libreecho-update install \
  /data/libreecho/incoming/local-install.ota.tar      # prints UPDATE_READY slot=...
sync
reboot
```

After the reboot the booted image's health worker runs
`libreecho-update confirm` once three probe rounds pass; confirmation calls
`feature-transaction verify-running`, `bootctl confirm` and `commit`. Check
`libreecho-update status` for `generation=$tx` and `ota_transaction_state=none`,
and `cat /data/libreecho/update/current` for the same transaction id.

Notes:

* `libreecho-update install` requires the running slot confirmed. A
  `development` image never confirms itself, so it needs an explicit BCB
  confirmation first; this is why the lab image uses the `ota` profile.
* adb push does not guarantee modes; the chmod above matches the sealed device
  assembly (0400/0500). `libreecho-generation verify` checks content and set,
  not modes.
* The package must be at most 32 MiB and contain exactly `manifest`,
  `manifest.sig`, `boot.img`; ours is 16,793,600 bytes.

Source changes required for this route: none. The MT8163 `libreecho-bootctl` reboot contract
did not fit Lidar; the shared runtime now has a `lidar` layout whose reboot-bootloader path
calls `reboot(RESTART2, "bootloader")` (`experiments/phase-05/notes.md`). That is the
recovery reboot path, not generation publication.
