# Step 33: latency OTA v0.2.25 installed

Host build plus install, 2026-11-22. The slices that produced the inputs are
`step33-latency-fix/{CpufreqWake,stream-playback,engine}.md`; this file records how they
were integrated into one OTA and what the unit reports after the reboot.

## Bundle

| Item | Value |
|---|---|
| Bundle | `artifacts/phase-06/ota-step33-latency/lidar-lab-v0.2.25.ota.tar` |
| sha256 / size | `1ea37bbddf52aa29665777fbc636e460fc0899dceb3afe0d3cb2f7feeb8f1a7c` / 16,793,600 |
| Transaction | `txn-92d3a65dbbc8ff12b9a722f5` |
| Boot image | `boot-lidar-v2.img` `2afa9fdf33f9746e65e8a1ee119cbf72ffca42399f90fe69bc0c4048769f0b01` |
| Channel / profile | dev / production, lab key, `lidar_recovery_image_contract=PASS` |

The three images were rebuilt into `artifacts/phase-06/images-step33-latency/`
(dev `2fb84ce7…`, v1 `873ebf40…`, v2 `2afa9fdf…`) with kernel `77931cc96944`
(`Image` `8acf87fe…`, `config` `0ade3894…`, DTB unchanged `e8727c88…`) and the UI bundle
rebuilt at `a9cea2ea5a0b` (manifest `1fb1a4d6…`, `source_commit=a9cea2ea5a0b`; its
`etc/init.d/libreecho-waked.init` asks for two wake threads on lidar). `build_images.sh`
now pins `UI_COMMIT=a9cea2ea5a0b605d574e1fb2ce9e407262c7fde3`; `UI_DIFF_SHA256` stays the
empty-diff hash because the tree is clean at that commit.

## airplay2 payload

`mksquashfs` is not packaged on this host, so squashfs-tools 4.6.1 was built from source
into `~/.local/opt/mksquashfs-4.6.1` (GZIP+LZ4+XZ+LZO+ZSTD) and
`repos/LibreEcho/build/package_feature_payload.sh` then packed the staged root
(`artifacts/phase-06/latency/engine/root`, every file byte-identical to the step-20 payload
root except the engine) with `-comp lz4 -all-root -no-xattrs -mkfs-time 0 -all-time 0`.

| Item | Value |
|---|---|
| Payload | `artifacts/phase-06/features-airplay2-latency/libreecho-lidar-base-airplay2-6361af00…payload.squashfs` |
| Payload sha256 / size | `6361af00bf939438a383f6aa20894c6ff70daf25f52e60c266a459e715989e0d` / 9,535,488 |
| Manifest sha256 / size | `eeffbba8565743c05eea70c05bd7b290bb392aa5e81fb3b262ba3e58b06765ee` / 141,734 |
| Engine in payload | `usr/local/sbin/libreecho-audio-engine` `84e5ae9b…` / 71,404 |
| Catalog | `feature-catalog.json` (phase-05 catalog with only `airplay2` repointed; the other four features keep absolute phase-05 asset paths) |

`unsquashfs -cat … usr/local/sbin/libreecho-audio-engine` returns exactly
`84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35`, and the host
`libreecho-update-verify` prints `ota_manifest_signature=PASS` for the generation.

## Install

`install.sh` (copy of the step-31 procedure, `adb -s <DEVICE_IP_A>:5555`), log in
`events.log` / `install.log` / `polls.log`:

```
08:15:28 start: bundle=v0.2.25 tx=txn-92d3a65dbbc8ff12b9a722f5 slot=a target=b
08:19:19 install: verify_rc=0 ready=b install_rc=0   (signature=PASS)
08:21:42 CONFIRMED: slot=b state=installed generation=txn-92d3a65dbbc8ff12b9a722f5 current=txn-92d3a65dbbc8ff12b9a722f5
```

The unit had been on slot a, v0.2.24. Install wrote the inactive slot b and the BCB, the
reboot landed on b, and the terminal confirmed state arrived about 2 minutes after the
reboot. No fallback was needed.

## After-checks (`after-checks.log`)

Read-only; no audio was played.

- Kernel `6.18.64+`; `scaling_driver=mtk-cpufreq`, `scaling_governor=schedutil`,
  `scaling_available_frequencies=598000 747500 1040000 1196000 1300000`,
  `scaling_min_freq=598000`, `scaling_max_freq=1300000`.
- `scaling_cur_freq=1300000` at idle and `1300000` in both samples under four `yes`
  processes, so the top OPP is reached. dmesg carries only cpufreq's benign "Running at
  unlisted initial frequency: 1001000 kHz, changing to: 1040000 kHz".
- waked argv: `--wake-threads 2`. Ten-second `/proc/<pid>/task/*/stat` deltas:
  two worker threads at 63.8 % and 48.1 % of a core, main thread 0.4 %, the other two
  4.5 % and 0.4 % (the ONNX work is now split over the two intra-op threads).
- `libreecho-esphomed` `a70f839d…` equals the bundle's staged binary (it is not staged at
  `/usr/local/sbin/libreecho-audio-engine`: the running engine is
  `/run/libreecho/features/airplay2/root/usr/local/sbin/libreecho-audio-engine`,
  sha256 `84e5ae9b…`, matching the artifact).
- `esphome-status.json`: `"ready":true,"connected":true`, port 6053.
- Idle ALSA: `/proc/asound/card0/pcm0p/sub0/status` = `closed`. The engine's five open
  `…/*.pcm` descriptors are its ring files, not ALSA devices. `pcm0c` does not exist on
  this card (capture goes through the codec device, as in step 31).

## Not verified here

Wake-to-sound latency after this bundle awaits my retest; no audio was played in this
run (per the assignment). The `floor` group frequency is not exercised separately.
