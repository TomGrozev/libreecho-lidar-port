# Ticket 07 and 08: remove openWakeWord and retire its branches

Both tickets ran together. 07 removed the ONNX wake engine; 08 retired the
branches that only existed to build it.

## Ticket 07 commits

| Repo | Branch | Commit |
|---|---|---|
| LibreEcho-UI | `feat/wake-word-selection` | `e8b4d5c` feat(waked): make microWakeWord the only wake engine |
| LibreEcho-Platform | `feat/micro-wake-word` | `f5c0cf7c9` feat(wakeword): package microWakeWord models instead of the ONNX runtime |
| LibreEcho | `feat/micro-wake-word` | `c7714bd` feat(wakeword): build microWakeWord and package its TFLite models |

The packager contract is now
`package_feature.sh <waked> <models-root> <payload> <manifest>`, with a models
root of `<name>/<name>.tflite` + `<name>/<name>.json`. `alexa` and `vad` are
hash-pinned to the pinned micro-wake-word-models source; the payload installs
models under `usr/local/share/libreecho/wakeword/` and licences under
`usr/local/share/licenses/libreecho-microwakeword/`, which is what
`verify_recovery_image.py` requires.

## Integration repair

The Platform integration merge hit a modify/delete conflict on
`wakeword/build_runtime.sh`: `fix/general-fixes-from-lidar-port` still carried
the reduced-ORT reproducibility fixes, `feat/micro-wake-word` deletes the file.
Fixed at the source with `33f69d107` on the general branch, which removes the
script, its operator list and the four tests that pinned their internals. The
remaining `test_recovery_image_tools.py` conflict is recorded in rerere, so
`integrate.py rebuild` resolves it on its own.

## Ticket 08

- Tagged and deleted `feat/wake-layernorm-ops` (`09e0ca345`) and
  `feat/wakeword-convert` (`80f53ed`); neither had been pushed.
- Removed both topics from `integration.json` and deleted their draft PR bodies.
- UI `feature/lidar-support`: dropped `f00a7d2` (two ONNX intra-op threads) and
  kept its non-ONNX hunk as `b662149` (the init test waited for a racing fake
  daemon). Old head at `archive/feature-lidar-support-2026-11-27`.
- `check-lock` passes for all eight repos after `integrate.py rebuild`.

Not done: the on-device wake-word comparison in ticket 06. The rest is complete: the
rewritten UI `feature/lidar-support` is pushed and equals the fork head, and the lab OTA
is built and pushed to the unit. v0.2.68 contains the microWakeWord stack
(`run/wake-tflm-build.log`, `run/wakeword-daemon-build.log`) and was installed on the
development unit on 2026-11-28 (owner report). Rewritten commits are unsigned because this
environment holds no GPG secret key.

## Commands

```
python3 tools/integrate.py rebuild --no-fetch
python3 tools/integrate.py check-lock
sh tests/test_waked_init_model.sh            # UI, passes on the rewritten head
python3 tools/mt8163-arm32/test_recovery_image_tools.py   # Platform, 1 known failure: no busybox
```
