# Platform rebase onto 0.14.6: work in progress

Status: **incomplete**. The generic branch is done; the Lidar branch is built and
committed but its full unit suites and the per-file delta review are outstanding.

Later (2026-11-22): most of that outstanding work is done. The Lidar branch exists
at `d7ad2ac48`, the branch-only test failures are fixed and re-verified (see
"Post-fix results"), and the host CI suites ran on all three trees (see "Test
baseline"). Still outstanding: the per-file enumeration of the 36 modified files
and the plan-level Phase 7 checklist items outside this rebase.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| old base (merge-base of our work) | `e917f8f9502509fae26812b5e362c0a3eba1ec7a` | 0.14.5, local `main` |
| upstream target | `37fc39aa6...` (`origin/main`, 0.14.6) | new base |
| old tip | `32f3dbdc4...` (`fix/lidar-efr32-nodes`) | 12 commits `e917f8f..32f3dbd` |
| `fix/general-fixes-from-lidar-port` | `0e1048a53` + uncommitted G4 work | from `origin/main` |
| `feature/lidar-support-0.14.6` | not created | planned from the generic head |

Later (2026-11-22): both branches exist and the work advanced past the rows above.
The current facts are in "Status at handoff" (generic head `ba81a7e6b`) and
"Lidar branch `feature/lidar-support-0.14.6`" (head `d7ad2ac48`) below; the
post-fix results and the archive tags at the end of this file are the newest
record. The Bases table and the two tables above it are kept as written when the
work started.

Worktree used: `/tmp/wt-gen` (`git worktree add`); the main checkout, all existing
branches and tags are untouched. No push, fetch, gc or clean was run.

## Generic commits so far

| New hash | Subject | Class | Source old hash |
| --- | --- | --- | --- |
| `ad4e21f83` | fix(ota): read the BCB for the running slot on the last try | GENERIC | `620935f41` |
| `85d72c179` | fix(init): keep the failure record the current boot wrote | GENERIC | `620935f41` |
| `0e1048a53` | fix(adb): keep the gadget enumerated across adbd restarts | GENERIC | `620935f41` |

G4 (`fix(ota): require the voice graph only when audio is declared`) is applied to
`libreecho-generation-transaction` and `libreecho-init` in the worktree and
**not committed**; `libreecho-reconcile-features`, `build_recovery_image.py`, its
tests and the pin refresh are not yet done.

## Classification of the 12 source commits

| Old hash | Subject | Class |
| --- | --- | --- |
| `620935f41` | feat(mt8167): Lidar platform profile and A/B boot support | MIXED: split by hunk |
| `76608be06` | test(multi-target): pin the reviewed reconciler and startup contract | GENERIC (pins adapt to the new hashes) |
| `17a453bf1` | feat(vendor-import): Lidar MT7668 firmware layout | LIDAR |
| `dcb69a971` | feat(init): Lidar MT7668 radio | LIDAR |
| `cdad1f619` | feat(audio): Lidar AIC32x4 chain | LIDAR |
| `0b6edb501` | feat(targets): render the Lidar audio profile | LIDAR (its `libreecho-init` comment tweak and pin churn fold into the generic audio-gate and pin commits) |
| `f4268e0be` | fix(image): pin the vendor importer in the verifier | LIDAR (pin depends on the MT7668 importer) |
| `c07b4fab0` | lidar: stage static wpa_supplicant | LIDAR |
| `fc8e3c2a3` | lidar: stage static tinyalsa tools | LIDAR |
| `0be90ed7e` | fix(audio-engine): drain the PCM ring before muting | GENERIC (not target-gated) |
| `bf073fb39` | fix(lidar): create ttyS2/gpiochip nodes | LIDAR (gated on `TARGET_ID=lidar`) |
| `32f3dbdc4` | perf(audio-engine): keep the Lidar output prepared | LIDAR (`lidar_chain` gated) |

GENERIC hunks taken from `620935f41`: failure-log prune order and its test; the
`/dev/kmsg` node, `no_disconnect=1` mount and UDC rebind supervisor and their test;
the `read_bcb` running-slot rework, `bootctl status "$v3_running"` at activation,
`feature_target_not_ready` token and the last-try activation test; the
audio-profile presence gate across the transaction, init, reconciler, UI startup
contract and its tests; the recovery-image hash pins.
LIDAR hunks left in `620935f41`: the whole `tools/mt8167-arm64/` tree; `lidar`
target slugs in init/manifest/update/update-fetch; vendor-import not-applicable
path; `partitions_lidar[]`/layout-policy/reboot-mode in `libreecho_bootctl.c` and
its tests; Lidar OTA/target tests.

## Dropped items

- `PINNED_SHA256` working-tree-bytes hack in `620935f41`, superseded by
  `76608be06`, which pins the reviewed commit instead.
- No debug-only commit exists in `e917f8f..32f3dbd`; nothing else dropped.

## Conflict resolutions so far

- `libreecho-reconcile-features`: upstream 0.14.6 keeps `ttsd` in Home Assistant
  mode (`d71439068`) while ours adds the audio-profile skip. Resolution: keep
  upstream's persisted `ttsd`/`ttsd-stays-wanted` behaviour and add the
  `assistant|wakeword` audio gate around it (not yet applied).
- `libreecho-init`: upstream added a second `voice_stack_absent` fallback; resolved
  by keeping the first fallback and removing the redundant second one, as our
  hunk does (applied).
- `test_multi_target.py`: upstream pins `PINNED_COMMIT=d71439068144...`; adopt
  upstream's structure and re-point to the new commit holding the reconciler.

## Test plan (NOT RUN)

Baseline: `origin/main`. Branches: both new heads.
```
cd tools/mt8163-arm32 && python3 -m unittest discover -v
cd tools/mt8167-arm64  && python3 -m unittest discover -v   # lidar branch only
```
CI workflow commands in `.github/workflows/` are the authority; record pass/fail
counts per branch against the baseline in this file.

## Proposed archive tags (not created)

- `archive/experiment-lidar-adb-stability` → `experiment/lidar-adb-stability`
- `archive/lidar-support-0.14.5` → `feature/lidar-support`
- `archive/lidar-efr32-nodes-0.14.5` → `fix/lidar-efr32-nodes`
- `archive/engine-drain-0.14.5` → `fix/engine-drain-before-mute`

## Status at handoff (worktree work only, no pushes)

Generic branch `fix/general-fixes-from-lidar-port` at `ba81a7e6b`, based on
`origin/main` `37fc39aa6`:

- `ad4e21f83` BCB running-slot read on the last try (from `620935f41`).
- `85d72c179` init keeps the current boot's failure record (from `620935f41`).
- `0e1048a53` adb gadget stays enumerated across adbd restarts (from `620935f41`).
- `60f3cc4f5` audio-profile gate for the voice graph (reconciler, init,
  generation transaction, UI startup contract, builder OTA health, tests).
  Upstream's Home Assistant `ttsd` behaviour is kept.
- `ffa448773` recovery init pin refreshed to the new `libreecho-init` bytes;
  the vendor-import pin keeps upstream's value.
- `ba81a7e6b` PCM ring drain before the DAC mute, ported onto upstream's
  refactored renderer: `play_partial_tail()` rebuilds the sub-period tail from
  `source->received`, renders through `sendspin_stage()`/`render_period()`, and
  `drain_output_pcm()` waits on `pcm_get_htimestamp()` for ring duration plus
  one period.

Verified on this branch: `airplay/test_audio_engine_contract.py` PASS and
`airplay/test_audio_engine_sendspin.py` PASS (real engine, fake PCM).

Not done at handoff: the Lidar branch `feature/lidar-support-0.14.6`
(`620935f41..32f3dbd` plus the target/tooling copies), the full unit suites on
baseline and both branches, the diff check against `fix/lidar-efr32-nodes`, and
test-result counting in this file.

## Lidar branch `feature/lidar-support-0.14.6`

Heads before the test-regression rewrite: generic `06bf811b0`, lidar `32884c432`.
The generic `test_recovery_image_tools.py` startup fixture and the lidar
`audio_engine.c` dangling-else were fixed by autosquash into `7661bc23f` and
`eed0943ef`; the lidar branch was then rebased onto the new generic head.

Worktree `/tmp/wt-lidar`, rebased onto `fix/general-fixes-from-lidar-port`
(`ba81a7e6b`). Head `d7ad2ac48`. Main checkout, old branches and tags untouched;
no push/fetch/gc. The autosquash rewrote the lidar commits, so every hash in the
table below is the post-rebase one.

| New hash | Subject | Source old hash |
| --- | --- | --- |
| `8e08af75f` | feat(mt8167): add the Lidar platform profile and A/B boot support (LIDAR hunks only) | `620935f41` |
| `fda949e51` | feat(vendor-import): add the Lidar MT7668 firmware layout | `17a453bf1` |
| `1cdd80b5d` | feat(init): bring up the Lidar MT7668 radio | `dcb69a971` |
| `9d18ef0d8` | feat(audio): drive the Lidar AIC32x4 speaker chain from the target profile | `cdad1f619` |
| `e32cddeb7` | feat(targets): render the Lidar audio profile | `0b6edb501` |
| `a873cc628` | fix(image): pin the current vendor importer in the verifier | `f4268e0be` |
| `6c7a28718` | lidar: stage a static wpa_supplicant in the boot image | `c07b4fab0` |
| `981e89040` | lidar: stage the static tinyalsa tools in the boot image | `fc8e3c2a3` |
| `2f830f9ec` | fix(lidar): create ttyS2 and gpiochip nodes at boot | `bf073fb39` |
| `d7ad2ac48` | perf(audio-engine): keep the Lidar output prepared between sessions | `32f3dbdc4` |

### Diff against `fix/lidar-efr32-nodes`

- `git diff fix/lidar-efr32-nodes feature/lidar-support-0.14.6 -- tools/mt8167-arm64`
  is **empty**: the whole MT8167 tool tree ports byte-identically.
- Whole tree: 50 files, 14 added / 36 modified, +9258/-229, no file deleted. The
  14 additions and the bulk of the insertions are upstream 0.14.6 files absent
  from the 0.14.5 tip (`airplay_delay.h`, the delay/pipe-delay/owner-settings
  tests, `test_ota_stale_install_lock.py`, the refactored `airplay_audio.c` and
  `audio_engine.c`). Deleted lines come from upstream refactors and from
  replaced port code.
- The remaining deltas are the generic branch commits (BCB, init failure
  record, adb gadget, audio-profile voice gate, pin refresh) and the recorded
  resolutions below. No unexplained delta in the mt8167 tree; per-file
  enumeration of the 36 modified files is still outstanding.

### Conflict resolutions (Lidar branch)

- `build_recovery_image.py` / `verify_recovery_image.py` pins: `620935f41` and
  `0b6edb501` carried old-branch init pins. Ours was kept until the ported
  `libreecho-init` bytes settled, then recomputed: `729d9a37...` after the radio
  commit, `cc61a51b...` after the device-node commit.
  `CONNECTIVITY_IMPORTER_SHA256` = `09eb59c5...`, checked against the shipped
  importer bytes.
- `test_multi_target.py`: kept the generic branch pins (`PINNED_COMMIT =
  7661bc23f`, `v3_reviewed` `d093e3b7...`); the `PINNED_SHA256` working-tree
  hack stays dropped.
- `libreecho-init`: kept the generic audio gate and upstream 0.14.6 structure;
  took the commit's vendor-import tool gate (`load_image_target` +
  `vendor_tools_present`) and the radio bring-up; the device-node worker is
  `TARGET_ID=lidar` gated.
- `build_recovery_image.py` audio startup contract: kept ours (upstream's
  bounded-delay contract already carries the audio gate).
- `audio_engine.c` (both commits): combined `reply_separate` accumulation with
  the `lidar_chain` bypass in `render_period()`; ported the hold window into
  upstream's per-iteration loop with `pcm`/`hold_until_us` hoisted to
  `run_engine`, the start-path delay snapshots kept, arm/open wrapped in
  `if (!pcm)`, and hold teardown/`session_failed`/`out:` close-up merged.

### Tests

- `tools/mt8163-arm32/airplay/test_audio_engine_contract.py`: **PASS** (all five
  checks, including both Lidar checks) on this branch.
- Full `tools/mt8163-arm32` and `tools/mt8167-arm64` suites: **NOT RUN**.

## Test baseline (host CI suites)

Bases: `/tmp/wt-base` = `37fc39aa6` (origin/main, detached);
`/tmp/wt-gen` = `06bf811b0` (fix/general-fixes-from-lidar-port);
`/tmp/wt-lidar` = `32884c432` (feature/lidar-support-0.14.6). Read-only from the
worktrees; no branch or main-checkout changes. These are the pre-rewrite heads.

Commands (from `.github/workflows/ota-release.yml`, `button-backport.yml`),
python 3.11.18 + PyNaCl 1.5.0:

    cd tools/mt8163-arm32
    python -m unittest -v test_recovery_image_tools test_build_wifi_dtb \
        test_verify_radar_puffin_dtb test_recovery_ap
    cd ../..
    # 16 airplay/music scripts (test_audio_engine_contract, test_airplay_volume_contract,
    # test_audio_period_buffer, test_audio_sink, test_audio_engine_sendspin,
    # test_speaker_dsp.sh, test_speaker_mbcl.sh, test_biscuit_speaker_dsp.sh,
    # test_radar_speaker_equivalence, test_music_features.sh, test_music_session_id.sh,
    # test_music_feature_trace.sh, test_music_transport_wrap.sh,
    # test_music_analysis_tap.sh, test_music_feature_packet, test_music_trace)
    python sendspin/test_packaging.py
    python emulation/hwsim/test_hwsim.py
    python -m unittest -q feature_runtime/test_runtime_package.py
    cd tools/mt8163-arm32
    python -m unittest -q test_multi_target.py test_build_wifi_dtb.py \
        test_verify_radar_puffin_dtb.py test_recovery_image_tools.py \
        test_recovery_ap.py test_local_install_adoption.py \
        test_issue_169_ota_health.py test_early_control_plane.py \
        test_issue_157_ota_rollback_finalization.py \
        test_operator_stale_lock_recovery.py mdns/test_runtime.py \
        test_qualification.py test_ssh_runtime.py test_local_services.py \
        test_vm_profile.py test_vendor_import_compat.py \
        test_source_offer_tools.py \
        recovery-install/tests/test_build_install_bundle.py \
        recovery-install/tests/test_installer_boot_write.py \
        recovery-install/tests/test_direct_userdata_install.py \
        recovery-install/tests/test_direct_nonce.py \
        ota/test_ota_v2_implementation.py test_ota_v3_activation.py \
        test_issue_231_fixed_boot_store.py test_reboot_bootloader.py \
        test_issue_195_no_expdb_marker.py test_ota_v3_config.py \
        test_ota_v3_convergence.py test_ota_v3_failure_policy.py \
        test_ota_v3_integration.py test_ota_v3_manifest.py \
        test_ota_v3_packaging.py test_ota_v3_recovery.py \
        test_ota_v3_transport.py test_ota_log.py test_ota_v3_web_status.py \
        ota/test_feature_provenance.py ota/test_service_identity.py \
        ota/test_dev_discovery.py ota/test_release_source.py \
        test_active_device_ping.py
    # py_compile lists, bash -n over tracked tools/mt8163-arm32/**/*.sh,
    # git diff --check
    cd tools/mt8167-arm64 && python -m unittest discover -v   # lidar only

| Step | base 37fc39aa6 | gen 06bf811b0 | lidar 32884c432 |
| --- | --- | --- | --- |
| button unittest group | 334 ran, 283 pass, 16F 5E 30S | 336 ran, 284 pass, 16F 6E 30S | 336 ran, 284 pass, 16F 6E 30S |
| 41-module unittest group | 986 ran, 892 pass, 38F 20E 36S | 991 ran, 896 pass, 38F 21E 36S | 1002 ran, 905 pass, 38F 21E 38S |
| 16 airplay/music scripts | 16 pass | 16 pass | 12 pass, 4 fail |
| sendspin packaging | 3 OK | 3 OK | 3 OK |
| hwsim | 6 ran, 5 pass, 1 skip | same | same |
| runtime package | 28 OK | 28 OK | 28 OK |
| py_compile, shell syntax, diff check | pass | pass | pass |
| mt8167 discover | n/a | n/a | 0 ran, 2 class skips (no dtc) |

All remaining failures/errors are identical on base and branch and are
environmental: host lacks `dtc`, `squashfs-tools`, `mksh`, `espeak-ng-data`; the
UI bundle fixture needs the external UI checkout; `/bin/busybox` was provided as
static busybox 1.35 in a bwrap namespace (C steps were rerun outside it).

Branch-only failures:

- `test_recovery_image_tools.PolicyTests.test_ui_bundle_startup_contract_is_fail_closed`
  errors on both branches and passes on base: `test_recovery_image_tools.py:2316`
  -> `build_recovery_image.py:1278` `SystemExit: ERROR: UI startup contract
  missing 'esphome_integration_state()'`. The builder's required marker list
  (`build_recovery_image.py:1197-1198`) gained the ESPHome gate, but the test's
  `valid_web` fixture did not.
- Lidar only: `test_airplay_volume_contract.py`, `test_audio_period_buffer.py`,
  `test_audio_engine_sendspin.py`, `test_music_analysis_tap.sh` fail because
  `audio_engine.c:2719-2720` has an unbraced
  `if (biscuit_chain) if (speaker_profile.lidar_chain)`, rejected by
  `-Wall -Wextra -Werror` (`-Wdangling-else`).

Skipped (need network/cross toolchains): "Verify sleep media arbitration"
(companion UI sparse checkout + `SLEEP_GENERATOR_DIR`); "Build the verified
ARM32 Opus prefix" and the pinned Opus provenance suites (archive downloads +
arm-linux-gnueabihf cross build); `button-backport` `recovery-ap-build` job
(archive downloads + ARM cross toolchain). `tts/test_package_feature_contract.sh`
ran but its unauthenticated GitHub fetches returned 401 (CI supplies
`GITHUB_TOKEN`); identical on base, so not a regression.

Logs: `/tmp/logs/base2`, `/tmp/logs/gen2`, `/tmp/logs/lidar2`,
`/tmp/logs/lidar-extra/mt8167-unittest.log`, `/tmp/logs/*-airplay.txt`.

## Post-fix results (heads `ba81a7e6b` and `d7ad2ac48`)

- Fix 1: `valid_web` in `test_recovery_image_tools.py` now carries
  `esphome_integration_state()`, `esphome_service_ready()` and its
  `disabled) return 0 ;;` arm; fixup squashed into `60f3cc4f5`.
- Fix 2: the stray `if (biscuit_chain)` in the wide render path of
  `audio_engine.c` is removed, so the lidar/bypass chain is
  `if (lidar_chain) ... else if (biscuit_chain) ... else ...`; fixup squashed
  into `9d18ef0d8`.
- `test_recovery_image_tools.PolicyTests.test_ui_bundle_startup_contract_is_fail_closed`:
  PASS on `ba81a7e6b` and on `d7ad2ac48`.
- 16 airplay/music scripts on `d7ad2ac48`, outside any bwrap namespace: 16 pass,
  0 fail (`bash /tmp/run-airplay-16.sh /tmp/wt-lidar`). A first batch run had
  `test_audio_engine_sendspin.py` fail once with a single `rtstart` underrun
  after the preceding compile-heavy steps; it passes standalone and on every
  rerun, and the same batch on `ba81a7e6b` passes 16/16, so it is load timing,
  not a branch delta.

## Archive tags (created 2026-11-22, owner approved; local only, not pushed)

- `archive/experiment-lidar-adb-stability` → `e917f8f95025`
- `archive/lidar-support-0.14.5` → `fc8e3c2a3eb8`
- `archive/lidar-efr32-nodes-0.14.5` → `32f3dbdc47b8`
- `archive/engine-drain-0.14.5` → `0be90ed7e6e3`

Annotated tags at the tips of the same-named branches; the branches are kept.
