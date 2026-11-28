# Step 33: Lidar voice-turn start latency, audio engine

Host work plus read-only device measurement, 2026-11-22. No image was flashed, no OTA
was installed, no service was restarted.

## Base and commits

| Item | Value |
|---|---|
| Repository | `repos/LibreEcho-Platform`, branch `fix/lidar-efr32-nodes` |
| Base commit | `bf073fb39e8362bc307777738d76c719fe5354b0` |
| Commit | `32f3dbdc47b81c3d0827f73532a172e6ee8f026c` (`perf(audio-engine): keep the Lidar output prepared between sessions`) |
| File | `tools/mt8163-arm32/airplay/audio_engine.c` only |

## Cause, with evidence

The 0.56 to 0.64 s between the engine's PCM open and the PCM reaching RUNNING is the
kernel machine driver's amplifier settle, not engine work:

- `repos/LibreEcho-Linux-618-audio/sound/soc/mediatek/mt8516/mt8516-amazon-lidar.c:30`
  sets `LIDAR_AMP_SETTLE_MS 500`, and `lidar_amp_event()` (same file, line 73) sleeps it
  before it unmutes MFP5, on the `Speaker` widget's power-on event.
- That event runs from `snd_soc_dapm_stream_event(STREAM_START)` inside
  `__soc_pcm_prepare()`, `repos/LibreEcho-Linux-618-audio/sound/soc/soc-pcm.c:948`, so it
  blocks the engine's `pcm_prepare()` (`audio_engine.c:2806` before this change).
- `SND_SOC_DAPM_STREAM_STOP` happens only at DAI shutdown (`soc-pcm.c:2001`), so a stream
  that is prepared but not running keeps the DAC and the amplifier powered.

Device measurement, read-only over Wi-Fi adb (`<DEVICE_IP_A>:5555`), 1 s of silence through
`tinyplay`, polling `/proc/asound/card0/pcm0p/sub0/status` every 10 ms:

| Output Route | start to RUNNING | log |
|---|---|---|
| `Line Out` (engine idle state) | 10 ms | `/tmp/tp-lineout.marks`, `.poll` on the unit |
| `Speaker` (engine armed state) | 0.56 s | `SETUP 3299.25` then `RUNNING 3299.81` |

That matches step32's engine measurement (`step32-ha-latency/probe-run2.log`: SETUP at
2847.88, RUNNING at 2848.46). step32's `tinyplay-check.sh` measured the jack path, which is
why it saw the kernel as fast.

The settle cannot be shortened: it covers the amplifier's own power-on transient (the driver
records 250 ms as the first silent unmute). It can only leave the reply path.

## Change

- `LIDAR_OUTPUT_HOLD_US` (30 s) at `audio_engine.c:72`.
- `lidar_hold_output_pcm()` at `audio_engine.c:2622`: mute `LO DAC Playback Switch`, keep
  `Output Route` on `Speaker` (routing to Line Out is what powers the amplifier down), then
  `pcm_prepare()` to clear a drained stream's XRUN.
- `pcm` and `hold_until_us` are now hoisted out of the session loop
  (`audio_engine.c:2672`); the loop head closes an expired hold through the normal teardown
  (`audio_engine.c:2771`); arm and open are skipped while a PCM is held
  (`audio_engine.c:2807`).
- A session that failed a PCM write is marked (`session_failed`, `audio_engine.c:2870` and
  `:2970`) and is never held: the failed PCM closes and the next session reopens it, so an
  XRUN recovery cannot replay predecessor frames (`audio_engine.c:3025`).
- The engine exit path closes a held PCM (`audio_engine.c:3049`).

Expected on the unit: open-to-RUNNING about 10 to 20 ms for any session that starts inside
the 30 s window; a cold first session still pays 0.56 s (the esphomed wake-time silence is
that cold session, so the reply arrives inside the window). Not device-verified.

## Build

```sh
cd /workspace/libreecho
CC=artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-gcc
A=repos/LibreEcho-Platform/tools/mt8163-arm32/airplay
T=artifacts/phase-06/features-airplay2-lidar/work/tinyalsa-e43025bbf702eb7dd8edd48c1eb50530c60f1de8
$CC -O2 -Wall -I$T/include -o artifacts/phase-06/latency/engine/libreecho-audio-engine \
  $A/audio_engine.c $A/aec_reference.c $A/audio_sink.c $A/audio_timing.c \
  $A/audio_visualizer.c $A/playback_status.c -L$T/src -ltinyalsa -lm
LD_LIBRARY_PATH=artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
  artifacts/phase-05/toolchains/armhf-root/usr/bin/arm-linux-gnueabihf-strip \
  --strip-unneeded artifacts/phase-06/latency/engine/libreecho-audio-engine
```

| Artifact | sha256 | size |
|---|---|---|
| `artifacts/phase-06/latency/engine/libreecho-audio-engine` (stripped) | `84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35` | 71,404 |
| `artifacts/phase-06/latency/engine/root/` | staging tree, every file byte-identical to the step20 payload except the engine | |

The engine that ships today is `97867ec9fba12293d9c118aa7373610691d16bc607f3cd873483722e5d02d836`.

## Not done: payload repack

`mksquashfs` is not installed on this host and `LIBREECHO_PIPELINE_ROOT` is not present, so
`package_feature.sh` and the step20 squashfs step could not be run here. The integrator has
to finish it:

```sh
cd /workspace/libreecho
A=artifacts/phase-06/latency/engine
# 1. payload squashfs from the staged root (same construction as step20)
mksquashfs "$A/root" "$A/airplay2.payload.squashfs" -comp lz4 -noappend -all-root
# 2. regenerate the manifest, which pins files["usr/local/sbin/libreecho-audio-engine"]
#    (package_feature.sh or the pipeline packager), then feature-catalog.json and the
#    lab OTA per step20-engine/deploy.md sections 1 and 2
```

Target of the update: the `airplay2` feature payload only, engine path
`usr/local/sbin/libreecho-audio-engine`, no boot image change and no combined OTA from this
slice.

## Verification

- `python3 tools/mt8163-arm32/airplay/test_audio_engine_contract.py`: PASS (5 checks).
- `python3 tools/mt8163-arm32/airplay/test_audio_engine_sendspin.py`: passes, but the
  `rtstart` scenario ("a fed Sendspin session let the S32 ring run dry after start") is
  intermittently failing on this host: it failed on the first run of both the changed and
  the pristine source, and passed on reruns of each. It is a pre-existing flake, not a
  regression from this change. Every other scenario, including `estripe`, passes.
- Not verified: anything on the device. The expected 10 to 20 ms start is a prediction from
  the kernel's prepare path, to be confirmed after I install the payload.

## Residual risk to check on the unit

- PCM 0,0 stays open and prepared for up to 30 s after each session, so another opener
  (`tinyplay`, a second engine) gets EBUSY inside that window.
- Inside the window the amplifier and DAC stay powered with the DAC muted. Watch for idle
  hiss in a quiet room; the window is the knob if it shows.
- `arm_output_controls()` is not re-run while a PCM is held, so a mixer change made by
  another process in that window is not restored until the hold expires.
