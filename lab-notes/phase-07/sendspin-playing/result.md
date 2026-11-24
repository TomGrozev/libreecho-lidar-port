# Sendspin playback is not reported as playing / LEDs never start

Status: fixed in source, host-tested. Not built into an OTA and not verified on
hardware.

## Root cause

Sendspin audio is a media-class source that bypasses the producer FIFOs: the
engine stages it from the framed sink and `render_period()` mixes it directly
(`audio_engine.c:2101-2147`). Every media observer, however, only looked at the
FIFO buses:

- `source_activity_mask()` (`audio_engine.c:1236-1248`) built the published
  `/run/libreecho-audio/status.json` mask from `SOURCE_MEDIA`/`SOURCE_AIRPLAY`
  `idle_periods`, so a Sendspin-only stream published `state":"idle"` with every
  bus false. The web portal reads that file in
  `LibreEcho-UI/src/backend_linux.c:2992` (`playback()`), hence "not playing".
- `process_music_visualizer()`/`music_analysis_period()`
  (`audio_engine.c:1124-1183`) analysed only the media/AirPlay FIFOs and stopped
  the visualiser when both had no bytes, so the LED tap emitted no music frames.

Both paths therefore missed Sendspin. This is a pre-existing engine gap, not a
rebase conflict: the 0.14.5 branch (`fork/feature/lidar-support`) has the same
code (`git diff fork/feature/lidar-support HEAD -- audio_engine.c` is empty).
It became visible now that a working Sendspin stream actually plays.

## Fix

Platform branch `fix/sendspin-media-status` at `0a4d7a6e0`, based on
`feature/lidar-support-0.14.6` at `326072055` (whose parent is the v0.2.34
build head `57324285b`). One commit holds the fix and its tests.
`tools/mt8163-arm32/airplay/audio_engine.c`:

- `sendspin_media_active()` asks the sink (`sendspin_live`) whether a generation
  is playing.
- `source_activity_mask()` and `ready_activity_mask()` set `PLAYBACK_BUS_MEDIA`
  for it (portal status, and the AEC reference activity mask).
- `music_analysis_period()` sums the staged Sendspin frames at unity;
  `process_music_visualizer()` keeps running while the sink is live and passes
  the stage in at both call sites.

No UI change: the portal already maps `source":"media"` to "Media"
(`web/js/app.js:46`), and `sendspind` still writes nothing to the FIFOs.

## Tests run

```
cd private/forks/LibreEcho-Platform/tools/mt8163-arm32/airplay
sh test_music_analysis_tap.sh            # PASS
python3 test_audio_engine_sendspin.py    # PASS (exit 0)
```
`engine-test.log` holds the full engine suite output. New coverage:

- `test_music_analysis_tap.c` case 4: Sendspin stage analysed at unity and
  saturating with the media bus.
- `test_audio_engine_sendspin.py` scenario `sendspinmedia`: a socket-only
  Sendspin stream must publish `"state":"playing","active":"media",
  "media":true` and reach the LED frame path.
- The loop harness now records LED-socket connects in `audit_led` and the
  "unexpected external path" checks compare `audit_denied == audit_led`, so the
  intended LED output no longer fails scenarios that only feed Sendspin.

## v0.2.35 rebuild

Platform only: rebuild the airplay2 payload / `libreecho-audio-engine` from
the v0.2.34 build's Platform step. No `sendspind`, UI or audio-sink change.

## Unverified

- Behaviour on the device (portal and LED ring) needs the rebuilt engine.
- No hash comparison of the shipped `sendspind` against UI `0d2285b` was made;
  it is not needed for this fix.
