# Step 17: microphone array, per-mic rub test

Hardware evidence, 2026-11-21, Tom present.

## Commands
- Stopped `libreecho-waked.init` and `libreecho-micd.init` so the capture PCM was free.
- `tinycap /tmp/mic-0.wav -D 0 -d 1 -c 8 -r 16000 -b 32 -t 3`: room baseline (`mic-0.wav`, `baseline.log`).
- `tinycap ... -t 150` round 1: ran out before the last holes; partial only (not kept on device).
- `tinycap ... -t 300` round 2, stopped with SIGINT after I finished: `mic-round2.wav` (1,088,511 frames).
- Analysis: 0.5 s RMS windows per lane, relative to each lane's median (eval, pure Python).

## Round 2 result (Tom rubbed holes in clockwise order, centre last)

| Window | Lane far above others | Peak over own floor |
|---|---|---|
| 14.5-19.5 s | 4 | +50 dB |
| 24.0-29.5 s | 5 | +18 dB |
| 32.5-37.5 s | 0 | +44 dB |
| 39.0-42.5 s | 1 | +26 dB |
| 45.0-48.5 s | 2 | +12 dB |
| 51.5-55.0 s | 3 | +14 dB |
| 58.0-61.5 s | 6 (centre) | +43 dB |

- Each of lanes 0-6 responds on its own to one hole: 7 distinct mics, centre = lane 6.
- Clockwise physical order from my start hole: 4, 5, 0, 1, 2, 3, then centre 6.
- Lane 7 stays flat (±0.2 dB) throughout: no acoustic input (reference or unused slot).
- Lanes 0 and 1 have a ~26 dB higher idle floor than lanes 2-6 (median 129-131 vs 103-106 dB re 1 LSB). Noted; not investigated.

Verdict: all 7 microphones capture: PASS. Mic gain matching is not measured here.

# Privacy latch (mute button)

## Commands
- One `tinycap ... -t 120` capture (`mic-priv.wav`) with a 0.5 s poll of
  `/sys/devices/platform/amz-privacy/privacy_state` (`priv.log`); I talked, pressed mute,
  talked, pressed mute again, talked. State summary and `buttond-status`: `privacy-state.log`.
- Afterwards a fresh 2 s capture with `privacy_state=0`: `mic-after.wav`.

## Result
- `privacy_state`: 0 for 51.5 s, 1 for 17.5 s, then 0 again. Kernel sees both presses.
- While latched (52-68 s), all 8 lanes are exactly 0 despite speech: muted capture is silent. PASS.
- After release, lanes 2-6 carry audio again, but **lanes 0 and 1 stay exactly 0**, in the
  same capture and in a fresh stream (`mic-after.wav`). Two of seven mics do not recover after
  unmute: FAIL.
- Lanes 0 and 1 are also the two lanes with a ~26 dB hotter signal before mute, which suggests
  they come from a different ADC or path than lanes 2-6 [INFERENCE].
- `buttond-status` keeps `privacy_state=0` and `lamp_control=0` after the run.
- Tom: "some LEDs flash, no red ring". No steady muted indication: FAIL (visual).
