# Step 24: voice turn (Tom "Alexa" + "set a timer for ten seconds")

## Timeline (device clock; boot at 10:03:11, v0.2.21 slot A)

| boot s | wall | evidence | event |
|---|---|---|---|
| 40 | 10:03:51 | system.log | timerd listening; micd "Lidar OCM capture path configured (PGA 82)"; micd "calibrated mono stream started" |
| 76 | 10:04:27 | system.log | agentd ready (first instance) |
| ~344 | 10:09:33 | waked.log | `wake_event sample=4860160 score=0.999093 vad_score=0.078`; capture began ~40 s, so wall 40+304 |
| 346 | 10:09:35 | waked.log | `reference ring cleared at playback start` = agentd's wake chirp (`voice_listening_led.c:31`, played from `voice_pipeline.c` start_recognition) |
| n/a | 10:09:35→10:12 | **no agentd line at all** (system.log) | no transcript, no `voice turn … before transcript`, no `timed_out` before the 30 s deadline (`voice_pipeline.c:30`) |
| 533 | 10:12:04 | watchdogd.log | voice ownership flips to Home Assistant (config change), agentd/ttsd/sttd stop being supervised |
| 545 | 10:12:16 | system.log | ttsd shutting down (rebuild of the stack) |
| 581 | 10:12:52 | system.log | `libreecho-web: Home Assistant address updated` |
| 590 | 10:13:01 | watchdogd.log | voice ownership back to local; agentd/ttsd/sttd restarted |
| 615 | 10:13:26 | system.log | agentd ready (second instance); **not a crash** |

The boot-615 "agentd ready" is the voice-mode flip restart, not a watchdog recovery: watchdogd log has no failure/restart lines, dmesg has no oops, and ttsd/sttd restarted in the same window (`/tmp/libreecho-*.reconcile.log`). The flip was caused by a web config update (another session's setup work), so the failed attempt ran on the local pipeline.

## Probes (silent)

Artifacts in `probe-results/`, `mono-raw-10-20.pcm`, `raw8-10-20.wav`, `rendered-step24-*.pcm`.

* `stt-run.sh`: sttd accepts `recognize_stream` and reports `pcm_s16_le/16000/mono`. But every TTS-`render` clip transcribes as `"S"`, `"UL"`, `""` even when resampled (slow15/slow137 also `"S"`). The microphone recording `alexa-what-time.pcm` transcribes perfectly (`ALEXA WHAT TIME IS IT`). Conclusion: sttd works on real mic audio; the TTS render output is not usable as an ASR fixture, so that part of the probe is inconclusive and must not be read as an STT failure.
* `mic-levels.sh`: the `voiceprobe recv` drain has a per-read timeout, not a total one, so `stream_mono` never returns (job killed after 100 s). Captured mono (`mono-raw-10-20.pcm`, 102 s): 1 s RMS −21…−6 dB with 0 dB clipping bursts in the first 67 s, then −33…−20 dB. `micd`'s own contract is idle RMS 12–17 and 1 m speech 70–105 *before* the 4× digital gain (`micd.c:418-472`, `voice_dsp.c:214-229`), i.e. ~50–420 after gain; the captured stream is 10–40× hotter and clips.
* Raw ALSA (`tinycap -D 0 -d 1 -c 8 -r 16000 -b 32`): S32_LE 8 ch, per-lane RMS 49/31/19/31/25/35/20/4 after `>>16`, peak ≈ −33 dBFS; a quiet room. So the over-level is created inside micd's beamform/gain stage, not at the codec.
* Mixer readback: `ADC1/2/3 PGA Capture Volume = 52 (range 0..63)`; micd maps my 65 % gain with `capture_gain_percent() * 127 / 100` (`micd.c:606-610`), asking for 82 on a 0..63 control, while audiod writes its own percent of the discovered max. The two daemons disagree about the same PGA and micd's value is out of range (the sibling comment at `micd.c:500-515` warns that an out-of-range write is actively harmful).

## Root cause status

* Proven: waked detected the wake; agentd's pipeline opened a turn and played the chirp; **no terminal outcome was ever logged** although the 30 s backstop (`voice_pipeline.c:30`, `:642-651`) must have fired. The capture thread therefore stalled between `start_recognition` and the poll loop, or the outcome log never reached logd. That is a LibreEcho-UI voice-pipeline defect, not a Lidar driver issue.
* Not proven: the mic level/format defect as the STT trigger. The live mono stream is demonstrably over-gained and clipping, and micd's PGA mapping is out of range, but my actual utterance was never captured through the pipeline for STT, so causality is unconfirmed.

## Retest (Tom)

1. After the next OTA, say "Alexa" then "set a timer for ten seconds".
2. Immediately afterwards (`< 30 s`), pull `agentd` status, `waked` status and `system.log`; if `waked: detected_count` increments but `agentd: wake_events` does not, the wake handoff is the fault; if `agentd: wake_events` increments and `voice turn … before transcript` appears, STT failed on the clipped mic stream.
3. Collect `mono-raw` via `stream_mono` with a fixed total deadline (probe bug above) during the same utterance.
