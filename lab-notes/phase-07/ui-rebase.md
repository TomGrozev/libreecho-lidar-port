# LibreEcho-UI rebase onto 0.14.6

Status: **rebased and suite-verified**. The generic branch head is `eedbc47`
(8 commits from `b14f9eb`); `feature/lidar-support-0.14.6` is `0b1bb52`, the
same generic head plus the 12 ported Lidar commits. `make all` and the host
`make test` suite pass on all three trees apart from the environment failures
listed below. Old heads, before this pass rewrote them: generic `d8fd0fe`,
Lidar `99e1929`.

The final pass fixed four branch-only failures inside their causing commits:
the missing `bt_adv_proxy.c` and `timer_schedule.c` link sources, the
`le_service_command_timeout` call site in `api.c`, the mock-only guard that had
been restored to `import_configuration` during conflict resolution, and the
extra wakeword-owner LED call that shifted the ended-turn index in
`test_voice_listening_callers.py`.

Head drift, read order (2026-11-22): this file was written in passes, so the
hashes in it are not one consistent snapshot. The Bases table's `eedbc47` and
`0b1bb52` are the heads at the start of the test pass. The Lidar port section's
`d8fd0fe` is the generic head that pass rebased onto. "UI test results" records
two later fixups (in `ff98ffa` and the `test-config-import-linux` Makefile
target), so the final generic head is past `eedbc47` and the final Lidar branch
is a rebase of it past `0b1bb52`; the archive tags at the end name the branches,
which are the durable reference. In each section the newest statement wins.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| old base | `b39af308f0d32e5ae56986d4c603195ab524dbc4` | 0.14.5, our work starts here |
| upstream target | `b14f9eb4dc8343769eca86240bc258c9130fcc6b` | `upstream/main`, 0.14.6 |
| old tip | `f43dadef8d6616812c53b38b1e3690491a1cacce` | 21 commits `b39af30..fix/lidar-port-identity` |
| `fix/general-fixes-from-lidar-port` | `eedbc47` | 8 commits from `b14f9eb` |
| `feature/lidar-support-0.14.6` | `0b1bb52` | generic head plus the 12 Lidar commits |

Containment: `fix/lidar-speaker-path`, `feature/lidar-audio` and
`experiment/lidar-startup-readiness` are all ancestors of the old tip, so the
21 commits cover every branch.

Worktrees: `/tmp/wt-gen2` (generic branch) and `/tmp/wt-lidar2` (Lidar branch).
The main checkout, old branches, tags and remotes are untouched. No push,
fetch, gc, clean or device access was run.

## Generic branch commits

| New hash | Subject | Class | Source |
| --- | --- | --- | --- |
| `fa4d1e4` | init: gate local voice services on the audio profile and back off readiness | GENERIC | `fce530a` |
| `7553fd0` | buttond: drive KEY_MICMUTE through the privacy latch, not a toggle | GENERIC | `d91fdff` |
| `dac8772` | fix(audiod): raise generated cue peak to half scale | GENERIC | `abe8d91` |
| `ff98ffa` | fix(esphomed): release the wakeword LED owner when a turn starts | GENERIC (split from `e564bf5`) | `e564bf5` |
| `bd6a806` | fix(btd): enable connectable before discoverable | GENERIC | `6945303` |
| `0b8edfa` | feat(timed): persist the last valid epoch on boards without an RTC | GENERIC | `d60fd17` |
| `9eff986` | fix(api): bound voice restarts, enable config import and align baby-monitor sources | GENERIC | `27a4363` |
| `eedbc47` | fix(micd): stop logging a phantom stream stop | GENERIC | `f43dade` |

The readiness commit supplies `esphome_integration_state()` and
`esphome_service_ready()` in `init/libreecho-web.init`, which is the UI-side
startup contract the Platform builder requires
(`build_recovery_image.py:1197-1198` on the Platform tree).

## Classification of all 21 commits

| Old hash | Subject | Class |
| --- | --- | --- |
| `4f478a3` | audio: describe PCM layout per target profile | LIDAR |
| `e4de634` | audio: anti-alias the Lidar AEC reference and profile the web source | LIDAR |
| `41c1782` | audio: map Lidar capture lanes by role and keep MT8163 relay raw | LIDAR |
| `4489e39` | audio: drop the Lidar AEC reference queue and cover it with tests | LIDAR |
| `fce530a` | init: gate local voice services on the audio profile and back off readiness | GENERIC |
| `c09551f` | btd: use the mainline btmtksdio controller on Lidar | LIDAR |
| `292e313` | audio: enable the Lidar line-out mixers and cap codec volume | LIDAR |
| `b283907` | ledd: probe the IS31 ring before the averaged sysfs backend | LIDAR |
| `d91fdff` | buttond: drive KEY_MICMUTE through the privacy latch, not a toggle | GENERIC |
| `68264d2` | audiod: apply capture mute and gain to every codec PGA | LIDAR |
| `50c744d` | fix(audiod): write the Lidar Speaker route with the control ioctl | LIDAR |
| `abe8d91` | fix(audiod): raise generated cue peak to half scale | GENERIC |
| `a7edb1d` | fix(esphomed): fall back to wlan0's factory MAC on Lidar | LIDAR |
| `371950a` | fix(micd): write the Lidar PGA as a percentage | LIDAR |
| `4b3c17d` | fix(waked): run two ONNX intra-op threads on Lidar | LIDAR |
| `a9cea2e` | perf(esphomed): stream TTS playback and prime the amp on wake | MIXED, superseded |
| `e564bf5` | fix(esphomed): keep a full period queued and clear the wake ring | MIXED: generic wake-ring hunk kept, pacing hunk superseded |
| `6945303` | fix(btd): enable connectable before discoverable | GENERIC |
| `d60fd17` | feat(timed): persist the last valid epoch on boards without an RTC | GENERIC |
| `27a4363` | fix(api): bound voice restarts, enable config import and align baby-monitor sources | GENERIC |
| `f43dade` | fix(micd): stop logging a phantom stream stop | GENERIC |

No debug-only commit exists in `b39af30..f43dade`; nothing was dropped for being
debug. Rationale for the border cases: the privacy latch path
(`src/adapter/buttond.c:53`) exists on every target, and the timed epoch file
changes a missing RTC from a failure to the expected state on any RTC-less
board.

## Conflict resolutions so far

- `src/adapter/buttond.c`: upstream moved `KEY_HELP` to an early branch, so the
  old case body is deleted; `KEY_MICMUTE` is folded into the `KEY_MUTE` arm and
  its comment kept.
- `Makefile:1542`, `tests/run_tests.sh:122`, `src/http_server.c:475`: kept both
  sides (new upstream test targets plus our added ones; `api_tick` plus
  `api_discovery_tick`).
- `src/api.c:690`: kept both `const int ha` and the bounded `deadline`.
- `src/api.c:703`: kept our ttsd-restarts-in-every-mode comment and `!ha`
  exception with the bounded command timeout.
- `src/api.c:1096`: merged `noise_suppression` and `restart.phase` into the
  voice status JSON and its argument list.
- `src/api.c:2166`, `3251`, `4027`: kept upstream HEAD wholesale. Upstream
  0.14.6 already carries the evolved `import_configuration`, equaliser import,
  settings copy, broadcast and voice-clip code, so our side of those blocks was
  redundant. The config-import error mapping keeps upstream's
  `rc==LE_INVALID?400:501` rather than our `501:503` split.

## Dropped items

- `a9cea2e` (streaming TTS and primer) is superseded by upstream `e26ed7d`,
  `63d1f4a` and `8adf5cf`: 0.14.6 streams the reply with
  `ESP_PLAY_WIRE`/`ESP_PLAY_PAYLOAD`, paces silence and calls
  `esp_playback_warm()` while the turn waits, which is the priming our
  `prime_bus()` provided.
- `e564bf5` pacing hunk (`ESP_PLAY_LEAD_MS`) is superseded by upstream
  `AUDIO_LEAD_MS`/`SILENCE_LEAD_MS`; only the wake-ring ownership fix survives.
- `27a4363`'s config-import error mapping and its old `import_configuration`
  body are dropped as above.

## Lidar branch (ported)

`feature/lidar-support-0.14.6` is rebased onto the fixed generic head
`d8fd0fe`. All 12 Lidar commits are ported, one commit each:

| New hash | Subject | Source |
| --- | --- | --- |
| `c050204` | audio: describe PCM layout per target profile | `4f478a3` |
| `aa16ac0` | audio: anti-alias the Lidar AEC reference and profile the web source | `e4de634` |
| `33639b3` | audio: map Lidar capture lanes by role and keep MT8163 relay raw | `41c1782` |
| `fb63a7d` | audio: drop the Lidar AEC reference queue and cover it with tests | `4489e39` |
| `a21c43c` | btd: use the mainline btmtksdio controller on Lidar | `c09551f` |
| `70a4460` | audio: enable the Lidar line-out mixers and cap codec volume | `292e313` |
| `dfaa023` | ledd: probe the IS31 ring before the averaged sysfs backend | `b283907` |
| `accc40a` | audiod: apply capture mute and gain to every codec PGA | `68264d2` |
| `9a383a5` | fix(audiod): write the Lidar Speaker route with the control ioctl | `50c744d` |
| `87dbe8a` | fix(esphomed): fall back to wlan0's factory MAC on Lidar | `a7edb1d` |
| `f6f89d8` | fix(micd): write the Lidar PGA as a percentage | `371950a` |
| `0b1bb52` | fix(waked): run two ONNX intra-op threads on Lidar | `4b3c17d` |

Port notes:

- `4f478a3` needed hand merges in `audiod.c` and `micd.c`. `audiod.c` keeps
  the upstream `event_sound.h` include alongside `audio_profile.h`; the
  profile-driven card/device, control capture, startup route and CLI handling
  apply as written. In `micd.c` the new layout/normalization/AEC helpers and
  `relay_capture` are taken whole, while `relay_capture_mono` keeps upstream's
  header-first OK write, mix mode and digital gain; `normalize_capture_frame`
  runs before `le_voice_decode_calibrated`, `frame_bytes` replaces the fixed
  wire frame size in the loop, and both reads are bounded by the 256-entry
  output buffer.
- `e4de634` applied cleanly apart from its `api.c` helper: the generic branch
  already defines `baby_audio_profile()`, so the duplicate definition from the
  port is dropped and the profile-aware local baby-monitor listing is kept.
- `a7edb1d` and `4b3c17d` conflicted only in tests and the waked init script.
  The two `test_esphomed.py` additions are independent, so both are kept. In
  `libreecho-waked.init` the second-wake-word argument block and the new
  `--wake-threads $WAKE_THREADS` default are combined. The ported
  `test_waked_init_model.sh` gained `wait_args` in `expect_second`, matching
  the wait it already uses for the model cases, because the fake daemon writes
  its argv asynchronously.

Every commit touching `audiod.c`, `micd.c`, `btd.c` or `ledd.c` was compiled
before the next cherry-pick. `make all` passes on the final tree with the CI
mbedTLS prefix (`CPPFLAGS=-I/tmp/mbed-host/prefix/include`,
`LDFLAGS=-L/tmp/mbed-host/prefix/lib`); the host has no system mbedTLS
headers. `make test` is the remaining check.

### What `git diff fix/lidar-port-identity feature/lidar-support-0.14.6` shows

Compared tips: `f43dade` (0.14.5 port) against `0b1bb52` (0.14.6 port).

**Upstream.** The new branch starts from `b14f9eb` (`upstream/main`, 0.14.6),
not from 0.14.5, so the diff carries all of 0.14.5 to 0.14.6: the large
`audiod.c` and `micd.c` refactors, the ESPHome streaming TTS work (`e26ed7d`,
`63d1f4a`, `8adf5cf`), the evolved `api.c`, the new service-command boundary
and the additional test targets. No upstream change was reverted.

**Resolution.** On that base the diff adds the eight generic commits and the 12
Lidar commits above. Read against the old branch, the Lidar behaviour is
unchanged: audio profile and its readers, AEC reference FIR, packed-lane
mapping, MT8163 passthrough, BT SDIO controller, line-out mixers and volume
cap, IS31 probe order, per-PGA capture gain, control-ioctl Speaker route, web
baby-monitor alignment, wlan0 MAC fallback, percentage PGA and two wake
threads. Conflict resolutions are those listed above; the only semantic ones
are the upstream config-import body and error mapping replacing our older
split, and the generic `baby_audio_profile()` helper replacing the duplicate
definition from the port.

**Dropped.** Two old commits leave no counterpart. `a9cea2e` (streaming TTS
and primer) is superseded by upstream's streaming/pacing/warm path, and the
pacing half of `e564bf5` (`ESP_PLAY_LEAD_MS`) is superseded by
`AUDIO_LEAD_MS`/`SILENCE_LEAD_MS`. The wake-ring ownership half of `e564bf5`
survives as the generic `ff98ffa`, whose extra wakeword-owner release is
reflected in `test_voice_listening_callers.py`. `27a4363`'s old config-import
mapping and body are dropped as described above; its Linux-backend intent is
kept by removing upstream's mock-only guard in `9eff986`.

## Test baseline

Worktrees: `/tmp/wt-ui-base` (detached `b14f9eb`) and `/tmp/wt-gen2` (generic
branch). Host steps follow `.github/workflows/checks.yml`; the workflow's
preflight subset (button settings, config/mock server) runs inside `make test`,
so it is covered by the suite rather than repeated here.

Environment used for both trees:
`ESPHOMED_NOISE=1`, `ESPHOMED_CRYPTO_PYTHON=/usr/bin/python3`,
`ESPHOMED_TLS_PREFIX`/`ESPHOMED_TEST_TLS_PREFIX=/tmp/mbed-host/prefix`,
`ESPHOMED_TLS_LIBS` = the static mbedTLS 3.6.7 archives in that prefix,
`CPPFLAGS=-I/tmp/mbed-host/prefix/include`,
`ESPHOMED_AIO_PYTHON=/tmp/esphome-client/bin/python` (aioesphomeapi 46.2.0,
PyNaCl 1.5.0) and `SPEEX_PREFIX=/tmp/speexdsp`. Ubuntu 24.04 ships the pinned
static SpeexDSP package; Arch only ships the shared library, so the host lane
built speexdsp 1.2.1 `--disable-shared --enable-static` into that prefix. The
pinned real-HA runtime for `make test-ha-esphome` was installed (Home Assistant
2026.9.4 and the exact `tests/test_ha_esphome_requirements.txt` pins).

| Tree | `make all` | `make test` | `make test-ha-esphome` |
| --- | --- | --- | --- |
| `/tmp/wt-ui-base` (`b14f9eb`) | pass | started; reached `tests/test_watchdog_stop_recovery_contract.sh` with no failure and then hung in that script (its `fake-watchdog` child idles; the same script hung a parallel suite in another worktree, so this is the host environment, not the tree) | not reached |
| `/tmp/wt-gen2` at `c01d0cc` | **fail** (see below) | not run | not run |
| `/tmp/wt-gen2` at `d8fd0fe` | pass | not run (ports were held by the hung base run) | not run |

Branch-only build failures and their fixes, all folded into `784ec3d`
("fix(api): bound voice restarts, enable config import and align
baby-monitor sources") into which the bad hunks were cherry-picked, by a
`--fixup` commit and `git rebase --autosquash` on the generic branch only:

1. `src/api.c:4216` called `voice_pipeline_restart_reap()`, which upstream
   0.14.6 removed. Replaced with `voice_pipeline_restart_advance(0)`.
2. `src/api.c` called `baby_audio_profile()` and `api_handle` lost `api_tick`,
   both of which only existed in the old tree and were dropped in the split.
   The generic commit now ships the header-only `src/adapter/audio_profile.h`
   (from `4f478a3`, defaults to the MT8163 layout), includes it from `api.c`,
   defines the small `baby_audio_profile()` cache helper and restores
   `void api_tick(...)`. The generic tree therefore builds without any Lidar
   commit. The Lidar port only needs `4f478a3`'s `audiod.c`/`micd.c` changes and
   must not re-add the header.

Generic head moved `c01d0cc` -> `d8fd0fe`; `UiLidarPort` was told to rebase
onto `d8fd0fe`. The suite was not run to completion on either tree; see
"UI test results" below for the branch-only failures that were established.

Cross builds skipped: the workflow has no cross lane, and the ARM32 targets
(`build/libreecho-waked-arm32`, `build/libreecho-sttd-sherpa-arm32`,
`build/test-wake-engine-arm32`, `build/wake-adapter-client-arm32`,
`build/stt-stream-file-client-arm32`, `build/libreecho-waked-onnx-arm32`) were
not built because they need `ARM_CROSS_COMPILE`/an ARM toolchain and SDKs that
the host lane does not provision. `make test-ha-esphome` was not run because
the base suite hung before it and the pinned HA run needs the same host while
the hung daemons hold the fixture ports.

## UI test results

Run on 2026-11-22, host only, worktrees read-only apart from `build/`. The suite
must run under a real shell (the agent's synthetic shell returns fake `$!`
PIDs, which makes the watchdog tests fail); all runs below used Python
`subprocess` with `/bin/sh`.

Environment for every tree:

```
CPPFLAGS=-I/tmp/mbed-host/prefix/include
ESPHOMED_TLS_PREFIX=/tmp/mbed-host/prefix
ESPHOMED_TEST_TLS_PREFIX=/tmp/mbed-host/prefix
SPEEX_PREFIX=/tmp/speexdsp
TMPDIR=/tmp/suite-<tree>
```

`/tmp/speexdsp` is a host static SpeexDSP 1.2.1 prefix (headers plus
`lib/libspeexdsp.a`) built without root; with it `make -j4 all` passes on
`/tmp/wt-ui-base` (rc 0), which removes the earlier
`cannot find /lib/libspeexdsp.a` failure. `make test-ha-esphome` still needs
`ESPHOME_HA_PYTHON` and was not run.

`tests/run_tests.sh` was not edited. A copy under `/tmp` wrapped each test-script
invocation with `timeout` and a TSV result line, leaving every other line and all
runner state intact. `TMPDIR` was set outside `build/` because of the suite bug
below.

### Per-tree state

Full `make test` equivalent, three trees run concurrently with staggered starts,
each in its own `TMPDIR` and with `LIBREECHO_TEST_PORT` 18082/18092/18102. Every
test invocation was wrapped in `timeout` and a `PASS`/`FAIL` record; no
assertion or build failure aborted a run.

| Tree | Result |
| --- | --- |
| `/tmp/wt-ui-base` (b14f9eb) | 316 steps: **309 pass, 7 fail**. |
| `/tmp/wt-gen2` (generic) | 319 steps: **311 pass, 8 fail**. |
| `/tmp/wt-lidar2` (Lidar) | 321 steps: **312 pass, 9 fail**. |

The failures, all environment-caused and reproduced on base unless noted:

- `tests/test_watchdog_stop_recovery_contract.sh` (base, gen, lidar): rc 124
  (60 s timeout) because its fake-watchdog child idles; the doc's earlier run
  hung on the same script with no timeout.
- `tools/test_virtual_echo.py` (rc 1, `test_persisted_auth_root`).
- `tests/test_issue_34.py` (rc 1, `URLError: Connection refused`).
- `tests/test_issue_94.py` (rc 1, virtual target not ready).
- `tests/test_ci_nested_make_provenance.py` (rc 1 on all three; the host is
  not the CI snapshot).
- `make test-esphome` (rc 2 on all three; the optional ESPHome lane is not
  provisioned on this host).
- `./build/test-timer-persistence` (rc 134 on all three; aborts on base too).

Two branch-only failures remained in that run and were then fixed and
re-verified on the final heads:

- `tests/test_voice_listening_callers.py` on gen and Lidar: the ported
  wakeword-owner release adds a fourth `led pattern` call before the ended-turn
  indicator, so the upstream test's fixed index 3 saw `owner == wakeword`.
  Commit `ff98ffa` updates the index to the next call and says why.
- `./build/test-config-import-linux` on Lidar: the Makefile target did not list
  `src/api.c` as a prerequisite even though the test includes it, so the Lidar
  tree reused a stale binary after the guard fix. The target now depends on
  `src/api.c`.

After the last rebase both tests pass on `/tmp/wt-gen2` and `/tmp/wt-lidar2`
(`config import: ... ok`, `Ran 1 test ... OK`). The generic head advanced by
these fixes; the rest of the suite is unchanged apart from the link sources and
the `le_service_command(` call site that the wrappers exercised.

### Branch-only failures fixed in their commits

1. `tests/run_tests.sh` link line for `test_bluetooth_discoverable_order.c`
   now links `src/adapter/bt_adv_proxy.c` (fixup folded into the commit that
   added the runner line).
2. `Makefile` `build/test-config-import-linux` now links
   `src/adapter/timer_schedule.c` and depends on `src/api.c`.
3. `src/api.c`'s default `run_init_command` now calls `le_service_command(`
   directly, meeting the upstream contract check; the bounded restart path
   keeps `le_service_command_timeout` through `run_init_command_timeout`.
4. The `import_configuration` mock-only guard, reintroduced by keeping
   upstream's block during conflict resolution, is removed again so import
   works on the Linux backend as the ported commit intends.
5. The wakeword owner release is accounted for in the listening-callers test.

### Suite harness bug (same on base and gen)

`Makefile:1461` (`:1449` on base) has
`-include $(shell find $(BUILD) -name '*.d')`, which matches directories.
`tests/run_tests.sh:5` puts the suite temp dir under `build/` when `TMPDIR` is
unset, and `tests/test_backup_roundtrip.sh:16` creates `etc/init.d` there. The
next `make` then dies with
`make: *** build/le-*/libreecho-backup-test.*/etc/init.d: Is a directory. Stop.`
at `tests/run_tests.sh:68`; reproduced directly. Setting `TMPDIR` outside
`build/` avoids it.

## Archive tags (created 2026-11-22, owner approved; local only, not pushed)

- `archive/lidar-port-identity-0.14.5` → `fix/lidar-port-identity`
- `archive/lidar-speaker-path-0.14.5` → `fix/lidar-speaker-path`
- `archive/lidar-audio-0.14.5` → `feature/lidar-audio`
- `archive/lidar-startup-readiness-0.14.5` → `experiment/lidar-startup-readiness`
