# Ticket 03 host replay: waked decode path on the lab clips

Acceptance from `03-decide.md`: "A host replay of the lab clips through the
`waked` decode path detects the same clips as the `pymicro-wakeword` rule."

`replay.c` is a throwaway driver: it links the topic branch's real
`src/adapter/wake_worker.c` (the decision rule) and the real
`src/adapter/wake_engine_mww.cpp` (TFLite Micro engine) and feeds raw
mono S16_LE 16 kHz PCM in 1280-sample blocks. `run.py` builds it, runs the
clean clip set of `../host-eval-20261127/OkNabuRobustness/out/mww_clean.json`
through both bundled words, and compares each (clip, model) detection with the
reference. Sensitivity is the default 50, so each model runs its manifest
cutoff.

## Run 2026-11-27

```
$ python3 run.py
...
10/10 clip/model pairs match the reference
```

Branch: `work/topic/03-LibreEcho-UI` at the ticket's tip before commit;
models `work/inputs/public-deps/micro-wake-word-models-source/models/v2`
(alexa, okay_nabu, vad); host TFLM from `work/inputs/tmp/mww-host`.

| clip | alexa | okay_nabu |
| --- | --- | --- |
| alexa-twice.wav | 2 detections (26880, 140800) | 0 |
| alexa-what-time.wav | 1 detection (26880) | 0 |
| okay_nabu_turn_on_the_lights.wav | 0 | 1 (21760) |
| genuine_brightness_fifty.wav | 0 | 1 (25600) |
| genuine_turn_on_the_lights_nab.wav | 0 | 1 (24320) |

No block was dropped (`dropped 0` in every run). The reference records only
"any window reached the cutoff", so the two `alexa-twice` detections are one
reference hit; the second alexa in the clip is 113 920 samples later, well
past the one-second refractory.

Not covered here: the retired openWakeWord engine, degraded/reverb conditions,
and the device build; those are the reference harness's own sets.
