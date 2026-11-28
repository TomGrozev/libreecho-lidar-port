# Step 32: Home Assistant voice turn latency, 2026-11-22

Read-only investigation on v0.2.24 (slot a). No image, config or service was changed. I did three wake turns and pasted HA's pipeline debug for each. HA: Soniox STT and TTS,
local intents first and an LLM agent as fallback, VAD "default", HA on a k8s host at
<LAN_HOST_A_2>:8123.

## Method

- `probe.sh` runs on the device and stamps, with `/proc/uptime` at roughly 20 to 40 ms
  resolution, the following: esphome-status `in_progress`, live TCP sockets (the TTS fetch to
  :8123), esphomed's open fds (the speaker FIFO opening), the speaker PCM state with
  `trigger_time`, and waked log lines. Logs: `probe-run1.log` (turns A and B) and
  `probe-run2.log` (turn C).
- Clock alignment: device `in_progress=true` against HA `run-start`. Turn A fixes the
  offset, and turn B then predicts its own `run-start` to within 1 ms.
- `tinyplay-check.sh` plays 1 s of silence straight to PCM 0,0, bypassing the audio engine.
  The input was a 48 kHz stereo S16 WAV of zeros generated on the host.
- Code paths traced read-only: `repos/LibreEcho-UI` (esphomed, waked, micd) and
  `repos/LibreEcho-Platform/tools/mt8163-arm32/airplay/audio_engine.c`.

## Timeline, end of speech to first sound

Turn A is "what time is it" with a local intent and an uncached reply. Times are seconds.

| Stage | A | B (cached reply) | C (LLM fallback) | Tom |
|---|---|---|---|---|
| HA waits for silence after speech (VAD "default") | ~0.7 | ~0.7 | ~0.7 | HA setting |
| STT final text after VAD end (Soniox) | 1.37 | 1.38 | 1.30 | HA / Soniox |
| Intent | 0.02 | 0.00 | 3.01 (LLM) | HA |
| TTS fetch: connect to body complete (device waits for whole file) | 1.13 | 0.10 | 1.19 | Soniox synth + esphomed |
| esphomed body complete to FIFO open | 0.08 | 0.09 | 0.04 | device |
| Audio engine: PCM open (SETUP) to RUNNING | ~0.6 (inferred) | ~0.6 (inferred) | 0.64 | device, audio engine |
| **Total** | **~3.9** | **~2.9** | **~6.9** | |

`tts-end` comes 2 ms after `tts-start` in every run, because HA streams TTS lazily. Soniox
synthesis therefore runs inside the device's fetch, and esphomed plays nothing until the
whole body has arrived (`esphome_playback.c:86-87`). For A and B the engine-start row is
inferred from the waked playback-start second (`t=2596s`, `t=2603s`), which matches FIFO
open + 0.6 s.

`tinyplay` reaches RUNNING within 10 to 20 ms of starting, so the kernel and codec are fast.
The 0.6 s is spent inside the audio engine, between its `pcm_open` and the PCM start
(`audio_engine.c:2780-2843`). Whether this is Lidar-only or affects every target is not yet
known.

## Wake path

- The waked inference thread uses 99.4 % of one core (994 ticks in 10 s, `/proc/<pid>/task`).
  The CPU is fixed at about 1.0 GHz (`armpll` 1001 MHz): the 6.18 kernel has
  `CONFIG_ARM_MEDIATEK_CPUFREQ` off, so the DT OPP table up to 1.3 GHz is never used.
  This is Lidar-specific.
- HA receives audio faster than real time. In turn A it had 2.59 s of audio 1.33 s after
  `run-start`, and turn B shows the same pattern. The wake event therefore fires at least
  about 1.0 s after the audio it detects. I see the ring light about 1 s after
  "Alexa". With the 8-block queue full, the worker drops blocks silently
  (`wake_worker.c:15`), which is the likely cause of the missed wakes on the third attempt.
- Network is not a factor: LAN RTT to HA is 1 to 7 ms, and a cached reply downloads in
  0.10 s.

## Other observation (cause not verified)

Turn C's transcript was "Time is it." because the first word was lost. The local intent
missed, and the LLM fallback added 3 s.
