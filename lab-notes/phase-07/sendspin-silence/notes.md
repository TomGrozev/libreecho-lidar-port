# Sendspin music is silent on the Lidar (2026-11-22)

Status: investigation only, cause open. No source change, no device write, no reboot.

## Report

Music Assistant (MA) streams to the Lidar's Sendspin player and nothing is audible. MA's
AirPlay player for the same Echo plays. Seen after the device restart at about 02:26:46 UTC.
Unit and software as in `../announce-bug/notes.md`; engine LibreEcho-Platform 32f3dbd.

## Device evidence (read-only)

Raw output: `dumps/20261122-lidar-announce/sendspin-*.txt` (private).

- MA (<LAN_HOST_A_52>) holds an established connection to `sendspind` on port 8928.
  `libreecho-airplayd.log` shows two FLAC 48 kHz stereo stream starts (lines 12 and 415),
  more than 400 `W sendspin.player: Failed to send audio chunk`, and at line 443
  `sendspind: engine dropped stream generation 4 (progress, err=11); re-arming`.
- During the silent stream the engine holds PCM 0,0 `RUNNING` (`hw_params`: S16_LE, period
  2048, buffer 4096) on an accepted `sendspin.sock` connection (`sendspin-pcm-live.txt`,
  `sendspin-fds-live.txt`, `sendspin-unix-live.txt`).
- Mixer, read with `tinymix` get only (`sendspin-mixer-live.txt`, 03:07:15 UTC):
  `LO DAC Playback Switch On, On`, `Output Route Speaker`, `LO Driver Gain Volume 0, 0`,
  `PCM Playback Volume 127, 127`. The gain matches the audible AirPlay path.
- `status.json` stays `idle` with every bus false during Sendspin, because
  `ready_activity_mask` reads only the FIFO buses (`audio_engine.c:1725-1740`). This is a
  reporting gap, not the silence.

## Ruled out

| Hypothesis | Evidence against |
| --- | --- |
| DAC left muted by the Lidar output hold (32f3dbd) | DAC unmuted during the silent stream; the Sendspin start path still reaches `unmute_output_controls` (`audio_engine.c:2871-2905`) |
| 20 ms SDK write budget against a 42.7 ms engine period | The same timing plays on Radar and Dot (commit 4c30c03 in LibreEcho-UI); `sendspin_service_until_writable` services the sink while the period drains |
| Lidar S16 2048 x 2 ring starves the sink | Host run of the real engine (`lidar_ring.py`, `run.log`): the Lidar ring credits 49,664 frames/s with 0 underruns, like the Radar and Dot S32 1024 x 3 ring; `avail` is 8-10 frames at the helper, so it polls every period |

The Lidar host run reports one failure, `completed generation never closed the PCM`. That is
the Lidar output hold keeping the PCM open on purpose; the harness clears only the older
Sendspin hold. It is not starvation.

## Open

The host engine admits Sendspin audio at real time with the Lidar ring, and the device does
not. The difference is outside what the host run models. Candidates not yet checked:

- The binaries on the device differ from the sources read (engine, `sendspind`, or the
  Sendspin SDK patch level that 4c30c03 needs).
- Something only on the device between `sendspind` and the engine sink, for example a
  second generation that starts inside the Lidar output hold.

Settling it needs an engine built with `LE_ENGINE_SENDSPIN_TRACE` or a verbose `sendspind` on
the unit, which is a device write and a service restart (needs approval), or a read-only hash
comparison of the device binaries against a local build.

## Live state sampled during the silent stream (2026-11-22 03:15-03:18 UTC)

Raw: `sendspin-engine-live-state.txt`, `sendspin-master-volume.txt`, `sendspin-waked-status.txt`,
`sendspin-socket-queues.txt`.

- Engine `8002` is in `do_sys_poll`, `voluntary_ctxt_switches` 694 900 -> 696 424 in 3.09 s
  (~490/s). That rate is the `sendspin_service_until_writable` bridge waking on each companion
  datagram, so the engine *is* inside the Sendspin inner loop and is servicing the sink, not
  parked in the outer 20 ms loop.
- PCM 0,0 `state RUNNING`, `owner_pid 8002`; `hw_ptr` advanced 144 828 frames in 3.0 s
  (48.2 kfr/s), so periods are being written at real time. `appl_ptr - hw_ptr` was 4 012 of
  4 096; `avail` 84 then 1 552. The sink queue is kept almost full, which is what refuses most
  offers with CAPACITY and produces the `Failed to send audio chunk` flood (normal backpressure,
  not a fault).
- `master.volume` = 66 (mode 0640, root, 3 bytes) and readable by the root engine:
  `logical_master_gain(66)` ~ -24 dB, so a zero software master is *not* the cause.
- `mix_sources_frame` gives Sendspin a flat gain of 32768 (`audio_engine.c:1861-1873`), so a
  media gain of 0 cannot mute it.
- Engine holds the `sendspin.sock` listener (inode 11682, LISTEN) and a connected peer
  (inode 14438) plus the PCM fd; `sendspind` has 7 sockets. The connection is live.
- `/run/libreecho-audio/waked-aec.status`: `ref_packets=25616 ref_overruns=16800216
  ref_edge_clears=18 ref_active=0`. The engine has published ~350 s of reference audio, i.e.
  it has written Sendspin periods for minutes; waked cleared the reference ring only at the
  five announcement starts (t=2717..2740 s in the tail).

## Trace cycle result (2026-11-22, engine built with -DLE_ENGINE_SENDSPIN_TRACE)

Raw: `dumps/20261122-trace-cycle/` (`sendspin-trace-full.log`, `restore2.txt`,
`sendspin-state.txt`). Build provenance: `artifacts/phase-06/features-airplay2-trace/README.md`.

One MA play, trace engine bound over the payload path. 454 lines, one generation, 442 periods:

```
open  gen=1 have=1 stage=0    nz=0 active=1 acc=0      queued=0
period gen=1 have=1 stage=2048 nz=0 active=1 acc=8192   queued=2048 tvalid=1 played=2072
...
period gen=1 have=1 stage=2048 nz=0 active=1 acc=907264 queued=2048 tvalid=1 played=901152
```

`nz` is the count of nonzero int16 samples in the staged period (`audio_engine.c:217-219`).
Every one of the 442 periods staged 2048 frames with `nz=0`. The engine therefore received,
queued, rendered and played 18.9 s of pure digital silence: accepted and played advance at
real time (~47.7 kfr/s), timing is valid, no starve, no generation churn, no XRUN.

So the engine is not the fault on the Lidar: the companion hands it zero PCM. In
`sendspind` the only component that zeroes samples before the sink is `PcmMute`
(`src/adapter/sendspin/pcm_mute.h`, applied in `write_locked`,
`sdk_player_listener.h:263-284`). `muted_` changes only via `on_mute_changed(bool)` and is
deliberately preserved across streams by `reset_stream()` ("a new stream starts at frame 0
already at the current target level"). `on_volume_changed` never scales PCM (it goes to
audiod as the device master). The persisted state file holds keypair/pairing/last-played
only, no mute, so a latched mute comes from the server on each connection.

Conclusion: the stream is silent because the Sendspin player is muted server-side (MA mute
for that player entity) and the client applies it to the PCM. That is the whole symptom;
the observable is indistinguishable from a decode fault only if the SDK also zeroes, which
the code rules out.

Next (cheap, no deploy): in MA, check the Sendspin player entity's mute state; or run
`sendspind` without `--quiet` and grep `mute` for the `on_mute_changed` transition. If MA
shows the entity unmuted, the SDK is dispatching a wrong mute and the fix is in the
companion: log/ignore a mute that arrives with no server state, or re-query the player state
on stream start.

Not a code fix yet: no test can distinguish "server muted" from "SDK dispatched a bogus
mute" without that datum.


The engine paces real-time Sendspin periods and keeps the sink queue full, yet no Sendspin
reference stream ever starts in waked. That leaves exactly two states for every period, and
they cannot be told apart from outside the process:

1. `g_sendspin.stage_frames == 0`, so the period is written by `write_period()` as silence
   while the sink still owns queued frames (means `have_generation == 0` in the inner loop,
   despite `sendspin_sync_identity` at `audio_engine.c:1556-1557`); or
2. `stage_frames > 0` but every staged sample is zero.

The in-tree trace prints exactly this: `sendspin_trace()` (`audio_engine.c:207-235`) logs
`gen= have= stage= nz= ... acc= queued=` per period to
`/run/libreecho-audio/sendspin-trace.log` in a build with `-DLE_ENGINE_SENDSPIN_TRACE`.
One play with that engine settles case 1 vs 2 in a single line. Not deployed: needs approval.

Proposed (needs owner/Main approval; write + restart):

```
# on the build host
make -C repos/LibreEcho-Platform/tools/mt8163-arm32/airplay CFLAGS+=-DLE_ENGINE_SENDSPIN_TRACE
adb -s <DEVICE_IP_A>:5555 push libreecho-audio-engine \
  /run/libreecho/features/airplay2/root/usr/local/sbin/libreecho-audio-engine.new
adb -s <DEVICE_IP_A>:5555 shell 'mv .../libreecho-audio-engine.new .../libreecho-audio-engine && \
  /etc/init.d/libreecho-airplayd restart'   # exact service name to confirm on unit
# then play one MA Sendspin stream, and read
adb shell cat /run/libreecho-audio/sendspin-trace.log
```

`nz=0` with `have=1 stage>0` would point at the render/mix path; `have=0` or `stage=0` with
`acc` growing points at the identity/stage gate during the hold.

## Mute refuted, instrumented-sendspind cycle (2026-11-22, approved by owner)

Owner muted then unmuted the Sendspin player in MA mid-play: no sound. So the `PcmMute`
latch (`src/adapter/sendspin/pcm_mute.h`, fed only by `PlayerRoleListener::on_mute_changed`,
`sendspin-cpp src/player_role.cpp:514-516`) is not the cause. Remaining zero-PCM producers:
the SDK's own `silence_scratch` writes (`sendspin-cpp src/sync_task.cpp:379-413`, aligning /
underflow / time filter never converging) or a decoder that emits zeros.

Prepared (logging only, branch `diag/sendspin-silence-trace` off deployed UI `f43dade`,
everything under `#ifdef LE_SENDSPIND_SILENCE_TRACE`):

- `src/adapter/sendspin/sdk_player_listener.h`: once per second and on every state change,
  `T sendspind.trace: t= muted= vol= stream= tsync= acc= writes= frames= zero_in=
  zero_out= full= tot_... starts= ends= reports=`; `zero_in` = all-zero frames as the SDK
  hands them, `zero_out` = all-zero after `PcmMute`; `MUTE_CHANGED`, `STREAM_START/END/
  CLEAR/BOUNDARY` lines. `tsync` is `SendspinClient::is_time_synced()`.
- `src/adapter/sendspind.cpp:380`: `listener.set_client(&client)`.
- Built with `LE_SENDSPIND_SILENCE_TRACE` + `LE_SENDSPIND_CLOCK_TRACE` (SDK VERBOSE prints
  `Hard sync: adding N frames of silence`, `Lost sync`, `Buffered frames underflow`) via
  `tools/mt8163-arm32/sendspin/hotstage/build_sendspind.py`:
  `/tmp/le-ss-out/sendspind`, static ARM EABI5, sha256
  `0a069d1d18ffb734cf1393a89c654177a18443f7403047209534bd1bcd81faa7`.
  Pinned archives in `/tmp/le-ss-archives` (all sha256 match `SOURCE.lock`).
  Toolchain: `artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-`, and binutils need
  `LD_LIBRARY_PATH=artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu`.

Interpreting one play: `zero_in` counting all frames with `tsync=0` (or VERBOSE hard-sync
silence lines) = SDK silence path; `zero_in` near 0 but `zero_out` all-zero = post-decode
zeroing/decoder. Then fix, host test (fails before, passes after), propose deploy.

Remaining device steps (approved): hash `/run/.../sbin/libreecho-sendspind` (expect
`a427bd68`), copy to `/data/libreecho/trace-cycle/libreecho-sendspind.orig`, push the trace
binary, bind-mount it over the payload path, stop→start `libreecho-airplayd` (discipline from
`dumps/20261122-trace-cycle/`), play one MA stream, capture, then stop→umount→start and assert
`a427bd68`, no bind in `/proc/mounts`, service running.

Result of that cycle (2026-11-22, owner played about 80 s; raw:
`dumps/20261122-lidar-announce/sendspin-trace-play.log`, `sendspin-trace-state.txt`):

- `stream=1 tsync=1 muted=0 vol=78 acc=1730560 tot_frames=3887232 tot_zero_in=3887232
  reports=0 starts=2 ends=1`. Every frame the SDK hands the companion is all-zero
  (`zero_in == frames`); `zero_out == zero_in`, so `PcmMute` is not involved.
- Writes are mini-blocks of about 233 frames at 319/s, the SDK's priming-silence blocks
  (`sync_task.cpp:379-388`), and no `sync_task` decode line ever appears in the log.
- `reports=0` is the key: the companion never calls `notify_audio_played`, so the SDK's
  `initial_decode` is never cleared (`sync_task.cpp:801-811`) and `handle_initial_sync`
  refills 25 ms of priming silence forever (`sync_task.cpp:198-216`). No chunk is decoded,
  the encoded ring fills, and MA's chunks are refused ("Failed to send audio chunk").
- The companion's pump (`sdk_player_listener.h:264-292`) bails before reporting; the guard
  that fires is not yet identified. Candidate: `session_.poll()` returning Timeout against the
  20 ms `control_timeout_ms` (`engine_sink_session.h:65`) while the engine services the sink
  once per 42.7 ms period.
- Restore verified: payload hash `a427bd68`, `/proc/<pid>/exe` `a427bd68`, no bind in
  `/proc/1/mounts`, airplayd and engine running.

Next: the branch now also counts each pump bail reason (`trace_bail_poll/timing/cursor/
delta/derive/regress`, `trace_last_poll`); one more short cycle with that build names the
guard, then the fix and its host test.

## Bail-counter cycle (2026-11-22, approved by owner)

Host harness check first: `tests/sendspin_engine_fixture.h` runs the real `audio_sink.c`
servicer in a 200 us loop and no test uses `EngineServer::pause()`, so the harness never
stalls the servicer; its P3 tests report on the first `pump_feedback()`. It cannot reproduce
the device's `reports=0`, so it cannot name the guard. Device cycle it is.

Diag branch committed: `c888e0d` (parent `f43dadef8d`), logging only, still under
`#ifdef LE_SENDSPIND_SILENCE_TRACE`. New counters: `pumps=` entries, `b_poll`, `b_timing`,
`b_cursor`, `b_delta`, `b_derive`, `b_regress`, `b_start`, `b_finish`, and
`lastpoll= played= accepted= finish_us=`.

Build (`/tmp/le-ss-out2/sendspind`, static ARM, sha256
`ea2e5311bb83b02d06c8af0bbb793da663068176f2521327b509cfa629472a6d`), recorded in
`artifacts/phase-07/sendspin-silence-trace.txt`:

```
export LD_LIBRARY_PATH=artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu
export CROSS_PREFIX=artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-
python3 repos/LibreEcho-Platform/tools/mt8163-arm32/sendspin/hotstage/build_sendspind.py \
  --ui repos/LibreEcho-UI --archives /tmp/le-ss-archives --out /tmp/le-ss-out2 \
  --define LE_SENDSPIND_SILENCE_TRACE --define LE_SENDSPIND_CLOCK_TRACE
```

Deploy script `/tmp/le-ss-archives/step2b.sh` (backup already on device from the previous
cycle, hash-checked, bind, stop/start, identity check); restore stays `/tmp/le-ss-archives/
step5.sh`.

State: deployed 2026-11-22 07:09 UTC, path hash `ea2e5311…`, bind active, airplayd and
engine running, no stream yet (`stream=0`, `lastpoll=2` NotOpen, `b_poll` grows with
`pumps`). Owner play announced as ready; capture is `/tmp/le-ss-archives/watch2.sh` plus
`cap2.sh` (writes `dumps/20261122-lidar-announce/sendspin-bail-play.log`). MUST run
`step5.sh` after the play to restore stock `a427bd68`.

Result (owner played about 30 s; `sendspin-bail-play.log`; restored at 07:10 UTC, path
hash `a427bd68`, binds 0, service running): the rejecting guard is the timing one.
During the stream `lastpoll=0` (poll Ok), `b_timing` climbed every second, `played`
advanced ~7000 frames behind `accepted`, and `finish_us=0` throughout. `b_poll` stayed
flat. So `session_.poll` succeeds and the engine publishes played frames with **no
finish horizon**.

## Root cause and fix (2026-11-22)

`audio_engine.c:773-781` `chain_output_latency_us()` returns -1 for `lidar_chain`
(introduced 2026-11-21 by `9d18ef0d8`), so `latency_calibrated` is false
(`audio_engine.c:3397`), so `le_audio_timing_source_finish_us()` refuses
(`audio_timing.c:386-395`) and `sendspin_publish_progress()` publishes TIMING_INVALID
(`audio_engine.c:411-422`): `finish_us` is always 0. The engine trace confirms it, 441 of
444 periods with `tvalid=1 tsrc=1 tfin=0`. The companion then bailed at
`sdk_player_listener.h:225` (`finish_us == 0`), so the SDK never cleared
`initial_decode` (`sync_task.cpp:801-811`) and only ever sent priming silence.

Fix: branch `fix/sendspin-uncalibrated-horizon` off `f43dadef8d`, commit `d63a58a`.
`pump_feedback()` reports the played prefix stamped with the local CLOCK_MONOTONIC
sample time when there is no horizon (a true upper bound), instead of refusing. Engine
ledger untouched; pacing runs late by the unmeasured chain delay until the Lidar chain is
measured (`hotstage/latency-measure.sh`).

Test: `test_uncalibrated_engine_still_reports_progress` in
`tests/test_sendspin_bridge_sdk.cpp`, 5 FAIL checks before the fix, exit 0 after; full
`tests/test_sendspin_sdk_host.py` lane passes. Build, deploy proposal and evidence:
`artifacts/phase-07/sendspin-silence-fix.txt`.

Trial on the Lidar, 2026-11-22 07:28 UTC: build `4198d62a…` (d63a58a, no diagnostic
defines) pushed to `/data/libreecho/trace-cycle/libreecho-sendspind`, bind-mounted over
the payload path, service restarted (sendspind 14847, `/proc/14847/exe` `4198d62a…`).
**Owner confirms music plays.** Fix left mounted; stock `a427bd68` stays at
`/data/libreecho/trace-cycle/libreecho-sendspind.orig`. Evidence:
`dumps/20261122-lidar-announce/sendspin-fix-trial-{deploy,play,state}.txt`; waked logged
`reference ring cleared at playback start` in the same window, the engine output start the
trace cycles never had.

Two operational notes: the bind does not appear in `/proc/mounts` as seen from the adb
shell namespace (hashes at the payload path and `/proc/<pid>/exe` both show the trial
binary, so the bind is real; `step5.sh`'s umount still works), and a reboot drops the bind
and returns the device to stock `a427bd68` until the fix is baked into a payload.

Integration, 2026-11-22: `repos/LibreEcho-UI` `fix/lidar-port-identity` fast-forwarded
`f43dade` → `d63a58a` (local, not pushed). That branch is the UI source the phase-06 build
scripts package, so the next airplay2 payload build carries the fix. No payload built yet.
