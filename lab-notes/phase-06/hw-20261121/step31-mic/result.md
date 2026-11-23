# Step 31: Lidar microphone level

## Device

v0.2.23, slot b, Wi-Fi adb <DEVICE_IP_A>:5555. Silent room, no playback.

## Measurements (bounded), 2026-11-22

`mic-levels.sh` (this dir) replaces step 24's unbounded `stream_mono` drain with
a total `timeout -s KILL` deadline; `tinycap` is bounded with `timeout -s INT 8`
(the image's toybox tinycap has no `-T`).

* Mixer: `ADC1..ADC4 PGA Capture Volume = 52, 52 (range 0->80)`, all four.
* Raw codec lanes (8 ch S32_LE 16 kHz, card 0 device 1, 8 s), lane RMS / peak:
  0 −56.6/−44.2, 1 −61.0/−42.4, 2 −65.4/−45.0, 3 −60.5/−42.7,
  4 −62.4/−42.8, 5 −59.1/−42.7, 6 −65.0/−42.5, 7 −76.3/−58.1 dBFS.
  A quiet room; the codec itself is not over-driven.
* Calibrated mono (`stream_mono`, 9.76 s, JSON header stripped): idle 0.5 s
  frames −79 … −64 dBFS, peak −42 … −58 dBFS; a short louder tail at
  8.0–9.5 s (−57 … −42 dBFS RMS) while the room was disturbed. **No sample
  reaches the rails** in this capture.
* Step-24 real speech capture (`alexa-what-time.pcm`, mono): loudest 100 ms
  frames RMS ≈ 3600–4500 (≈ −17 dBFS), peak ≈ −4 dBFS. Relative to micd's own
  contract (70–105 RMS before the 4× digital gain, i.e. 280–420 after), that
  is ~10× hot and only ~4 dB below clipping.

## Root cause

The readback range is **0..80**, not 0..127. micd asked for
`65 * 127 / 100 = 82` at every capture start; the write is out of range,
tinymix clamps it to 80, and the log still prints 82. audiod independently
writes the owner's 65 % of the discovered range = 52. So the two daemons set
the same PGA 14 dB apart, and whichever wrote last won: micd's 80 saturates
the beamformed stream (the clipped first 67 s of step 24's 102 s capture),
then audiod's 52 restores the quieter level. The mono over-level is this
analogue race, not the beamformer or the 4× digital gain (raw lanes are
−56 … −65 dBFS RMS at 52).

Probe on device: `tinymix set "ADC1 PGA Capture Volume" 65% 65%` reads back
`52, 52`. percentage writes land on 52 exactly as audiod computes it.

## Change

`repos/LibreEcho-UI/src/adapter/micd.c` `configure_lidar_capture_path()`:
the Lidar PGA is now written as `"<percent>%"` instead of a hardcoded
`* 127 / 100`, so tinymix resolves it against the control's real 0..80 range
and cannot disagree with audiod. The Radar path and the 4× digital gain are
untouched.

Open: speech level at the fixed 52 should now be ~14 dB below the step-24 hot
capture (≈ 720 RMS, ≈ −18 dBFS peak, ≈ 18 dB headroom). That is still ~1.7×
the contract's upper bound; whether to lower the Lidar digital-gain default
would need a wake-score measurement, which this unit has no onnxruntime
fixture for. Owner retest decides.

## Pending (not done in this run)

* Build UI bundle / images / OTA `lidar-lab-v0.2.24`, verifier, manifest diff.
* `install.sh` with after-checks.
* Runtime trial (binary swap + micd/waked restart). not performed; the async
  `alexa-what-time.pcm` numbers above are the before/after baseline.
* Original binary preserved at `/data/local/tmp/step31-micd.orig`
  (sha256 99ed0451…b695ba4d); device mixer restored to 52.
