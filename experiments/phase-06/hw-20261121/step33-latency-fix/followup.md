# Step 33 follow-up: v0.2.26 lab OTA built

Host build record, 2026-11-22. Nothing here was installed or booted; the only
device-facing script, `install-0226.sh`, was written and not run.

## Bundle and images

The UI bundle was rebuilt at LibreEcho-UI `e564bf56977527b5378f1b4f0e60bc16535428a5`
(`fix(esphomed): keep a full period queued and clear the wake ring`) from a clean
detached worktree, so `source_diff_sha256` is the empty-diff hash. Manifest
`a00ffe844902f1b0a8a8ba7f131901f77bd444b843c8093bce8f54050fa67a83` lists
`sbin/libreecho-esphomed` `a906bb91c9ca6d4f3296b09c05042904db378e0fa31f5f2e5c1c0012cd475201`
(previous `a70f839d…`); the binary carries the new `{"name":"stop","owner":"wakeword"}`
handover. The only other changed file is `sbin/libreecho-web` (`3a1cecf…`), whose
embedded `LE_SOURCE_COMMIT` string moved from the old pin to `e564bf5`.

`experiments/phase-06/build_images.sh` now pins `UI_COMMIT=e564bf5…`. The three
images are in `artifacts/phase-06/images-step33-followup/`, built with the
cpufreq kernel (`artifacts/phase-06/latency/cpufreq/Image`
`8acf87fe028b1372b921a9522d3c4a9d3e6f578541e0dc59113e98860032d9fd`, config
`0ade3894…`, DTB unchanged `e8727c88…`), and each printed
`lidar_recovery_image_contract=PASS`:

| Image | sha256 |
|---|---|
| `boot-lidar-dev.img` | `240b3e7ec8dff2a32e49bf10b3e4c4c87fbe1c8a3ec2d4382256c1652f45dccb` |
| `boot-lidar-v1.img` | `3ca48b4506b3f459f73286ed18e2cb9a8fe38c340c16060c6b4a6f1ff932a79b` |
| `boot-lidar-v2.img` | `c3844effddd9ad9f6de81850c78ab58ca5b91c7bfccb7ecfc39cc2cb0b362cf1` |

## OTA

`make_lab_ota.py` (dev channel, production, lab key, `--config-schema 1`) signed
the v2 image with the unchanged derived catalog
`artifacts/phase-06/features-airplay2-latency/feature-catalog.json`, so the
`airplay2` payload is the v0.2.25 one (`6361af00…`, manifest `eeffbba8…`, engine
`84e5ae9b…`) and the other four features keep their phase-05 assets.

| Item | Value |
|---|---|
| Bundle | `artifacts/phase-06/ota-step33-followup/lidar-lab-v0.2.26.ota.tar` |
| sha256 / size | `7d28f40b9141b5a2c4955977a81262a65ad9b4dfe7e216e72549e5c9b6bc26c3` / 16,793,600 |
| Transaction | `txn-bad7b618061367f54b2daf6d` |
| Boot image | `boot.img` `c3844eff…` (16 MiB) |

The host `libreecho-update-verify` against the generation tree prints
`ota_manifest_signature=PASS`.

## Install

`install-0226.sh` is `install.sh` with `dir=artifacts/phase-06/ota-step33-followup`
and `ver=0.2.26`; it passes `bash -n`. It was not run, so there are no
install/after-check logs for this version and the unit still runs v0.2.25.

## Not verified

No reboot, OTA install, service restart or audio playback. The esphomed pacing
and LED handover behaviour is therefore only covered by the host tests recorded
in the slice, not on hardware.
