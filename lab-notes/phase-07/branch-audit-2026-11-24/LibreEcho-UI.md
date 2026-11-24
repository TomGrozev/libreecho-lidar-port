# LibreEcho-UI branch audit and retopic (2026-11-24)

Repo: `private/forks/LibreEcho-UI`. Upstream remote is `upstream`
(`https://github.com/aslater3/LibreEcho-UI.git`); `upstream/main` = `b14f9eb`
(0.14.6), unchanged by `git fetch upstream --prune`.

Topic layout after this pass:

| Branch | Head | Commits vs upstream/main | Base |
| --- | --- | --- | --- |
| `fix/general-fixes-from-lidar-port` | `02a950d` | 15 | `upstream/main` |
| `feat/wake-word-selection` | `46a950a` | 1 | `upstream/main` |
| `feature/lidar-support` | `96db763` | 30 (15 general + 15 Lidar) | `fix/general-fixes-from-lidar-port` |

`feature/lidar-support` is stacked on the general topic because the Lidar
commits need `src/adapter/audio_profile.h`, which only exists from general
commit `9eff986`; the Lidar tree does not build on `upstream/main` alone.

Old heads (also in `refs/tags/backup/2026-11-24/<branch>`):
`fix/general-fixes-from-lidar-port` `eedbc47`, `feat/wake-word-selection`
`46a950a`, `feature/lidar-support-0.14.6` `947841e`,
`fix/lidar-port-identity` `d63a58a`.

## General topic (15 commits)

The first eight are unchanged (`eedbc47` chain). The six after `eedbc47` were
made on the Lidar branch after the 0.14.6 port; none touches Lidar-only code
(esphomed/sendspin shared adapters, web init gate, Makefile link fix). The last
one is new.

| Commit | Subject | Source |
| --- | --- | --- |
| `fa4d1e4` | init: gate local voice services on the audio profile and back off readiness | `fce530a` |
| `7553fd0` | buttond: drive KEY_MICMUTE through the privacy latch, not a toggle | `d91fdff` |
| `dac8772` | fix(audiod): raise generated cue peak to half scale | `abe8d91` |
| `ff98ffa` | fix(esphomed): release the wakeword LED owner when a turn starts | `e564bf5` (wake-ring half) |
| `bd6a806` | fix(btd): enable connectable before discoverable | `6945303` |
| `0b8edfa` | feat(timed): persist the last valid epoch on boards without an RTC | `d60fd17` |
| `9eff986` | fix(api): bound voice restarts, enable config import and align baby-monitor sources | `27a4363` |
| `eedbc47` | fix(micd): stop logging a phantom stream stop | `f43dade` |
| `490efbe` | fix(sendspind): report played frames when the engine has no horizon | `715dd4f` |
| `2101753` | fix(init): keep the startup gate open in Home Assistant voice mode | `7a2639c` |
| `5e07cd7` | perf(esphomed): parse the CA chain once and treat a zero data size as EOF | `0d2285b` |
| `952a1fb` | test(esphomed): give the borrowed-setUp suites the daemon hooks | `470eb36` |
| `dc8a7d9` | fix(esphomed): ignore chunk extensions in chunked replies | `0cc5507` |
| `9eebb64` | fix(build): link service_env into esphomed | `29a7a0a` |
| `02a950d` | fix(api): declare api_tick before api_init | new |

`02a950d` moves the general branch's `api_tick` declaration above `api_init`.
Both this topic and `feat/wake-word-selection` re-add `api_tick` (upstream
0.14.6 removed it); with the declaration after `api_init` the two additions
landed in separate hunks, so a merge silently kept two declarations. At one
anchor the merge reports a single conflict that rerere can record.

`9eebb64` needed one resolution: the old `29a7a0a` Makefile line also carried
`wake_model.c wake_model_store.c` from the wake copy; on this topic only
`src/service_env.c` is added (`src/adapter/voice_ns.c src/config_store.c
src/json.c src/service_env.c`).

## Wake topic

`feat/wake-word-selection` `46a950a` was already exactly one commit on
`upstream/main`; no rebase, no content change.

About `7f5c29a`, the copy on the Lidar branch: its changed lines differ from
`46a950a` only where the base differs.
- `src/api.c` `api_tick`: the copy calls `voice_pipeline_restart_advance(1)`
  because the Lidar base already has `api_tick`; `46a950a` calls
  `voice_pipeline_restart_reap()`, which exists on `upstream/main`.
- `src/api.c` / `src/api.h`: comment wording, and `46a950a` also adds the
  `api_tick` declaration and the `http_server.c` call because upstream has
  neither.
- Nothing else: `git show` line-set diff of the two patches (
  `awk '/^[+-]/'`) is limited to those lines.

So `7f5c29a` contains no fix the wake feature lacks; it is a base adaptation.
It is tagged `archive/lidar-wake-word-selection-copy` and left off the Lidar
topic.

## Lidar topic (15 commits on the general topic)

| Commit | Subject | Source |
| --- | --- | --- |
| `5ab901a` | audio: describe PCM layout per target profile | `c050204` |
| `72aba38` | audio: anti-alias the Lidar AEC reference and profile the web source | `aa16ac0` |
| `97917ae` | audio: map Lidar capture lanes by role and keep MT8163 relay raw | `33639b3` |
| `135099a` | audio: drop the Lidar AEC reference queue and cover it with tests | `fb63a7d` |
| `3bca047` | btd: use the mainline btmtksdio controller on Lidar | `a21c43c` |
| `888bd05` | audio: enable the Lidar line-out mixers and cap codec volume | `70a4460` |
| `ca381c7` | ledd: probe the IS31 ring before the averaged sysfs backend | `dfaa023` |
| `b60b24f` | audiod: apply capture mute and gain to every codec PGA | `accc40a` |
| `a7f43a3` | fix(audiod): write the Lidar Speaker route with the control ioctl | `9a383a5` |
| `21dcacd` | fix(esphomed): fall back to wlan0's factory MAC on Lidar | `87dbe8a` |
| `66a8850` | fix(micd): write the Lidar PGA as a percentage | `f6f89d8` |
| `92fa94a` | fix(waked): run two ONNX intra-op threads on Lidar | `0b1bb52` |
| `e3d465e` | feat(ui): expose and persist the Lidar radio setting | `81aaae3` |
| `f871cdb` | fix(ui): keep the Lidar radio panel from being shadowed | `f584cf7` |
| `96db763` | fix(ui): describe the Lidar Thread option as what ships | `947841e` |

`81aaae3` and `f584cf7` touch `src/api.c`/`api.h`/`web/js/app.js` near wake
code but cherry-pick cleanly without the wake copy; no dependency on it.

## fix/lidar-port-identity (0.14.5, 22 commits), folded and archived

Every commit is superseded by a 0.14.6 counterpart, so nothing is dropped
silently; the old branch head is tagged `archive/lidar-port-identity-ui`
(`d63a58a`).

| Old | New / note |
| --- | --- |
| `d63a58a` | `490efbe`, `git show` patch is identical to `715dd4f` |
| `f43dade` | `eedbc47` |
| `27a4363` | `9eff986` |
| `d60fd17` | `0b8edfa` |
| `6945303` | `bd6a806` |
| `e564bf5` | `ff98ffa` (wake-ring half; `ESP_PLAY_LEAD_MS` pacing superseded by upstream `AUDIO_LEAD_MS`) |
| `a9cea2e` | superseded by upstream `e26ed7d`, `63d1f4a`, `8adf5cf`; reachable via `archive/lidar-port-identity-ui` |
| `4b3c17d` | `92fa94a` |
| `371950a` | `66a8850` |
| `a7edb1d` | `21dcacd` |
| `abe8d91` | `dac8772` |
| `50c744d` | `a7f43a3` |
| `68264d2` | `b60b24f` |
| `d91fdff` | `7553fd0` |
| `b283907` | `ca381c7` |
| `292e313` | `888bd05` |
| `c09551f` | `3bca047` |
| `fce530a` | `fa4d1e4` |
| `4489e39` | `135099a` |
| `41c1782` | `97917ae` |
| `e4de634` | `72aba38` |
| `4f478a3` | `5ab901a` |

## Trial integration

Worktree `/tmp/ui-audit`. `git config rerere.enabled true`,
`rerere.autoupdate true` in the repo.

```
git switch --detach b14f9eb
git merge --no-ff fix/general-fixes-from-lidar-port
git merge --no-ff feat/wake-word-selection
git merge --no-ff feature/lidar-support
```

Conflicts, resolved once and recorded in `.git/rr-cache` (4 entries: Makefile,
`src/adapter/esphomed.c`, `src/api.c`, `src/api.h`, `init/libreecho-waked.init`
= 5 keys):

- `Makefile`, keep the wake sources and `src/service_env.c`:
  `src/adapter/voice_ns.c src/config_store.c src/json.c src/wake_model.c src/wake_model_store.c \` + `src/service_env.c`.
- `src/adapter/esphomed.c`, `ep_string(&w,5,S.wake_phrase)` (wake) with
  `profile("listening");wake_stop();` (general's wakeword-owner release).
- `src/api.c`, `api_tick`: keep `(void)voice_pipeline_restart_advance(1)` and
  add `wake_restart_advance(c)`; `api_persist_configuration` keeps
  `voice_pipeline_restart_advance(0)`.
- `src/api.h`, one `api_tick` declaration, wake wording.
- `init/libreecho-waked.init`, `MICD_INIT` block then the Lidar
  `TARGET_FILE`/`WAKE_THREADS` block.

A replay from `b14f9eb` reuses the recorded resolutions (no manual edit) and
produces the same tree.

Trial head `455a5be` (tree `add1d82`). `git diff 947841e 455a5be` shows only:

- `src/api.c`: the wake-copy comment wording (5 lines, from `46a950a`) and
  `(void)c;` in `api_tick` (from general `9eff986`).
- `src/api.h`: `api_tick` declaration moved above `api_init` (6 lines, from
  `02a950d`) and the wake wording of its comment.

No other hunk: no Lidar behaviour changed, no upstream change reverted.

Build (host, no device): `make clean` then
`make -j$(nproc) all` with
`ESPHOMED_TLS_PREFIX=private/artifacts/phase-07/host-mbedtls` and
`SPEEX_PREFIX=private/artifacts/wakeword-build-inputs/speex-prefix`.
Result: `make clean` then `make -j8 all` completed with rc 0 on trial tree
`455a5be` (74 s). `make test` was not run: full suite, environment dependent,
and the prior record documents host-only failures.

## Cleanup state

- Temp worktree `/tmp/ui-audit` (branchless, detached). `git worktree remove`
  is approval-blocked here; cleanup is `mv` away plus `git worktree prune`.
- Temp branch `trial/integration` (`258c51e`) from the first trial remains
  because `git branch -d` refuses unmerged branches and `update-ref -d` is not
  allowed; owner-deletes.
- `fix/lidar-port-identity` (`d63a58a`) and `feature/lidar-support-0.14.6`
  (`947841e`) also need owner deletion; both are archived/tagged.
