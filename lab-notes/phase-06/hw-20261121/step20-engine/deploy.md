# Step 20: deploy the Lidar audio-engine feature payload

Host-only build record, 2026-11-21. Nothing in this file has been run on the
device: there was no adb/fastboot access and no write approval for this step.

## Artifacts

| Item | Value |
|---|---|
| Payload | `artifacts/phase-06/features-airplay2-lidar/libreecho-lidar-base-airplay2-ca95c4b3af253a39df3086017836073e753e6b1e68e5c737518dec64e6a3d6d4.payload.squashfs` |
| Payload sha256 / size | `ca95c4b3af253a39df3086017836073e753e6b1e68e5c737518dec64e6a3d6d4` / 9,547,776 |
| Manifest | `libreecho-lidar-base-airplay2-6cb55ffeb76b9910295717c0a9ddb2f9f912795bce0bc738e10293e61eb76e6e.manifest.json` |
| Manifest sha256 | `6cb55ffeb76b9910295717c0a9ddb2f9f912795bce0bc738e10293e61eb76e6e` |
| Engine in payload | `usr/local/sbin/libreecho-audio-engine`, sha256 `97867ec9fba12293d9c118aa7373610691d16bc607f3cd873483722e5d02d836` |
| Source | `repos/LibreEcho-Platform` HEAD `fc8e3c2a3eb8a3451b8d6f08be4d44913c2a128a` (contains `cdad1f619`) |
| Base payload | upstream `a6583300…` root, repacked; every other file is byte-identical |

The engine was built from the Platform tree with the phase-05 ARMHF toolchain
and sysroot (`artifacts/phase-05/toolchains/armhf-cc`, `armhf-root`) and the
pinned tinyalsa `e43025bb` archive. `strings` on the binary contains `lidar`
and `lo_driver_gain`; the stale deployed engine (`39b6f34e…`) contains neither.

The speaker profile stays at the Platform Lidar definition
(`tools/mt8167-arm64/libreecho_platform_targets.py`, `lo_driver_gain=0`,
`hp_driver_gain=0`, `speaker_chain=lidar`, `codec_profile=Flat`). This
procedure does not change the image profile and does not raise the level.

The payload is not a partition image. It lives on `userdata` under the
generation tree and is verified and mounted by the update/generation tooling:

- bundle: `/data/libreecho/incoming/local-install.ota.tar` (temporary)
- installed payload: `/data/libreecho/generations/<txn>/features/airplay2/payload.squashfs`
- installed manifest: `/data/libreecho/generations/<txn>/features/airplay2/manifest.json`
- runtime mount: `/run/libreecho/features/airplay2/root` (`ro,nosuid,nodev`, squashfs loop)

`system_a`, `system_b`, `boot_a/b` and the other boot-chain areas are not
written by this step. A payload-only change needs no boot flash; flash the new
boot image separately only for the audiod route fix.

The boot image rebuilt for the audiod fix (LibreEcho-UI
`50c744d6dfcc1bb4b62da2b22d9d774c6751ecde`) is in
`artifacts/phase-06/images-route/`:

| Image | sha256 |
|---|---|
| `boot-lidar-dev.img` | `ebb2191f75ec25128c7c0a6af05e976716a767be5f7dbc8074d9acf28dc3af06` |
| `boot-lidar-v1.img` | `45f1113c532db82cc7c3cdbc8e031ed724f2961e90212444e168c2bb1ff4123f` |
| `boot-lidar-v2.img` | `256cd6a7691ff4e92fa48dfae411852ecb10801467de2ca2d5cda04562f3b8db` |

Each passed `lidar_recovery_image_contract=PASS` and remains
`PREPARED_NOT_FLASHED`; the UI bundle manifest sha256 is
`562ae177fd78fbf95f6f34c528904e124f29b341be66794b8337cbd64cb947bb`.

## 1. Derived feature catalog

Do not edit the phase-05 catalog in place. Copy it and repoint only
`airplay2` (the other four keep their phase-05 assets and hashes):

```sh
cd /workspace/libreecho
A=artifacts/phase-06/features-airplay2-lidar
python3 - "$A" <<'PY'
import json, pathlib, sys
a = pathlib.Path(sys.argv[1]).resolve()
c = json.loads(pathlib.Path('artifacts/phase-05/ota/lab-run/feature-catalog.json').read_text())
c['features']['airplay2'] = {
    'payload': str(a / 'libreecho-lidar-base-airplay2-ca95c4b3af253a39df3086017836073e753e6b1e68e5c737518dec64e6a3d6d4.payload.squashfs'),
    'payload_sha256': 'ca95c4b3af253a39df3086017836073e753e6b1e68e5c737518dec64e6a3d6d4',
    'payload_size': 9547776,
    'manifest': str(a / 'libreecho-lidar-base-airplay2-6cb55ffeb76b9910295717c0a9ddb2f9f912795bce0bc738e10293e61eb76e6e.manifest.json'),
    'manifest_sha256': '6cb55ffeb76b9910295717c0a9ddb2f9f912795bce0bc738e10293e61eb76e6e',
    'manifest_size': 141734,
}
(a / 'feature-catalog.json').write_text(json.dumps(c, indent=2) + '\n')
PY
```

`make_lab_ota.py` re-hashes both files, requires the manifest's
`schema_version=1`, `feature_id=airplay2`, `format=squashfs-lz4`,
`payload.sha256/size` and `files["usr/local/sbin/libreecho-audio-engine"].sha256`,
and derives the asset names from those hashes.

## 2. Build a lab OTA bundle that carries it

Use the boot image the unit already runs when only the payload changes, or the
image built from the UI fix when audiod is also being updated. Release version
must be above the installed one (`0.2.14` on the unit at the time of writing).

```sh
cd /workspace/libreecho
A=artifacts/phase-06/features-airplay2-lidar
mkdir -p "$A/ota"
python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image artifacts/phase-06/images-route/boot-lidar-v2.img \
  --feature-catalog "$A/feature-catalog.json" \
  --release lidar-lab-v0.2.15 --version 0.2.15 \
  --update-channel dev --service-profile production \
  --signing-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output "$A/ota/lidar-lab-v0.2.15.ota.tar"
sha256sum "$A/ota/lidar-lab-v0.2.15.ota.tar"
```

The maker writes the generation tree next to the bundle. Note the
`generation=`/transaction id it prints; `<txn>` below is that id.

## 3. Install (requires separate hardware-write approval)

```sh
cd /workspace/libreecho
A=artifacts/phase-06/features-airplay2-lidar
txn=<transaction-id-from-step-2>
adb shell 'mkdir -p /data/libreecho/generations /data/libreecho/incoming'
adb push "$A/ota/generations/$txn" /data/libreecho/generations/
adb push "$A/ota/lidar-lab-v0.2.15.ota.tar" \
  /data/libreecho/incoming/local-install.ota.tar
adb shell "g=/data/libreecho/generations/$txn
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \
  \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync"
adb shell reboot
```

Install requires `verify_rc=0` and `install_rc=0`; do not reboot otherwise.

## 4. What the device verifies

`libreecho-generation verify` (`initramfs/libreecho-generation`, `verify_tree`):
checks the signed `target.manifest` and `.sig`, the `COMPLETE` hash, the exact
generation file set, no symlinks, and, for every feature, that
`features/<feature>/payload.squashfs` matches `feature_<feature>_sha256` and
`feature_<feature>_size` from the generation manifest and that
`manifest.json` matches `feature_<feature>_manifest_sha256/size`. For this
build those expected fields are the catalog values above.

`libreecho-update install` verifies the bundle signature and the same per-file
hashes while extracting, then writes `/data/libreecho/update/current`.

`libreecho-generation-transaction` binds each payload read-only:
`mount -t squashfs -o ro,loop,nosuid,nodev …/features/airplay2/payload.squashfs
/run/libreecho/features/airplay2/root` and refuses the generation if the mount
fails.

At runtime `libreecho-reconcile-features` requires exactly one `ro,nosuid,nodev`
squashfs mount at `/run/libreecho/features/airplay2/root`
(`feature_runtime_mounted`) before starting `airplayd`; a missing or replaced
payload logs `feature-reconcile-payload-missing:airplay2` and does not start.

## 5. Confirm on the unit

```sh
adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-update status' | \
  grep -E 'feature_airplay2_(payload_sha256|payload_size|manifest_sha256|running_daemon_sha256)'
adb shell 'grep libreecho-audio-engine /proc/mounts; findmnt -no OPTIONS /run/libreecho/features/airplay2/root; \
  strings /proc/$(pidof libreecho-audio-engine)/exe | grep -E "^(lidar|lo_driver_gain)$"; \
  tail -n 40 /var/log/libreecho-airplayd.log'
```

Expected after the first playback attempt:

- `feature_airplay2_payload_sha256=ca95c4b3…`, size `9547776`;
- `feature_airplay2_running_daemon_sha256=97867ec9…`;
- the engine strings contain `lidar` and `lo_driver_gain`;
- the log no longer has `audio profile rejected; using radar-puffin defaults`
  or `output arm failed`, and `Output Route` is not rewritten through amixer.

The profile's `lo_driver_gain=0` is −6 dB by design (TLV320AIC32x4 step
−0.5 dB); it is not raised here.
