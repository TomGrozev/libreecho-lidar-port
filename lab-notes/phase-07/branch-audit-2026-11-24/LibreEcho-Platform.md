# LibreEcho-Platform: topic-branch audit and rewrite (2026-11-24)

Repo: `private/forks/LibreEcho-Platform`. Worktrees: `private/forks/LibreEcho-Platform`
(primary), `private/forks/LibreEcho-Platform-wakeops`. Upstream `origin` =
aslater3/LibreEcho-Platform, `fork` = owner's fork. Nothing pushed.

Base: `origin/main` = `37fc39aa6092491bcb5f12b77a8151179ffd122b` (0.14.6).

Heads at the start of the work (after `git fetch --all --prune`):

| Branch | Old head |
| --- | --- |
| `feat/wake-layernorm-ops` | `9bae088ccd0bfdae5ba6bc4b6aeaa5028c7533bd` |
| `feature/lidar-support-0.14.6` | `40bf6f0b69fb05232bd72f16bceefd96c48e81c8` (was `7011650f9` when the brief was written; another session added `40bf6f0b6`) |
| `feature/lidar-wake-ops` | `2ce7c9d3b132e38d648586e3dcb67a33fc15299a` |
| `fix/general-fixes-from-lidar-port` | `ba81a7e6b708daa2c88d90e86f88114be79f6877` |
| `fix/lidar-efr32-nodes` | `32f3dbdc47b81c3d0827f73532a172e6ee8f026c` |
| `fix/reconcile-topology-nonfatal` | `07549ae3542fd9d08116c169b1180b4537d03548` |
| `fix/sendspin-media-status` | `0a4d7a6e024b3662cb864c75c09ed1af3f98a96d` |
| `main` | `e917f8f9502509fae26812b5e362c0a3eba1ec7a` (0.14.5) |

Resulting topics (all based on current `origin/main`):

| Branch | New head | Commits | Scope |
| --- | --- | --- | --- |
| `fix/general-fixes-from-lidar-port` | `08e4b9872f780454a06b6937b2c34a947c3dec3e` | 8 | general |
| `feat/wake-layernorm-ops` | `9bae088ccd0bfdae5ba6bc4b6aeaa5028c7533bd` (unchanged) | 1 | general |
| `feature/lidar-support` | `2ebe8111a23c603c392fe0eef7d48ddea12b865e` | 38 (8 general base + 30 lidar) | lidar |

`feature/lidar-support` is stacked on `fix/general-fixes-from-lidar-port`: the
Lidar history was rebased on the general branch and its commits depend on it
(`build_recovery_image.py` / `libreecho-init` state, the pinned reconciler
bytes). `git log origin/main..feature/lidar-support` therefore also lists the
eight general commits; no commit is duplicated as its own copy.

## Classification

| Old commit | Subject | Class | New home |
| --- | --- | --- | --- |
| `ad4e21f83` | fix(ota): read the BCB for the running slot on the last try | general fix | `0ce404fd3` |
| `85d72c179` | fix(init): keep the failure record the current boot wrote | general fix | `7796e7e34` |
| `0e1048a53` | fix(adb): keep the gadget enumerated across adbd restarts | general fix | `fb7d2a002` |
| `60f3cc4f5` | fix(ota): require the voice graph only when audio is declared | general fix | `db4feea1d` |
| `ffa448773` | build: refresh the recovery init pin | general fix | `9636d8516` |
| `ba81a7e6b` | fix(audio-engine): drain the PCM ring before muting the Lidar DAC | general fix (not target-gated) | `ebd12dfea` |
| `07549ae35` | fix(reconcile): keep starting features when the voice topology fails | general fix (was only on the Lidar branch / `fix/reconcile-topology-nonfatal`) | `ced303f88` |
| `0a4d7a6e0` | fix(audio-engine): report Sendspin as media playback | general fix (was only on the Lidar branch / `fix/sendspin-media-status`) | `08e4b9872` |
| `8e08af75f` | feat(mt8167): add the Lidar platform profile and A/B boot support | lidar | `cf329a2ba` |
| `fda949e51` | feat(vendor-import): add the Lidar MT7668 firmware layout | lidar | `feae6d0f9` |
| `1cdd80b5d` | feat(init): bring up the Lidar MT7668 radio | lidar | `469c71445` |
| `9d18ef0d8` | feat(audio): drive the Lidar AIC32x4 speaker chain | lidar (chain gated on `lidar_chain`) | `55541debd` |
| `e32cddeb7` | feat(targets): render the Lidar audio profile | lidar | `7eab4d5d4` |
| `a873cc628` | fix(image): pin the current vendor importer in the verifier | lidar (pin follows the MT7668 importer) | `783bf4483` |
| `6c7a28718` | lidar: stage a static wpa_supplicant in the boot image | lidar | `3a3537dfd` |
| `981e89040` | lidar: stage the static tinyalsa tools in the boot image | lidar | `8317f8ce4` |
| `2f830f9ec` | fix(lidar): create ttyS2 and gpiochip nodes at boot | lidar (`TARGET_ID=lidar`) | `56baa8657` |
| `d7ad2ac48` | perf(audio-engine): keep the Lidar output prepared between sessions | lidar (`lidar_chain`) | `0d85de0d0` |
| `94af033cf` | fix(lidar): map the Lidar target in the boot init | lidar | `574e7e3ce` |
| `064c1df2e` | test(multi-target): restore the Lidar acceptance contracts | lidar tests | `fb4cc3c47` |
| `2278dedde` | test(multi-target): pin the reconciler to the topology fix | lidar test pin (value re-pointed) | `937e76c7e` |
| `3fce9b077` | fix(lidar): require the Wi-Fi radio before confirming a slot | lidar | `b7206c455` |
| `af4bcba2b` | fix(lidar): refuse to confirm a slot with an unmapped target identity | lidar | `0674a6590` |
| `a09f6cd5b` | test(lidar): cover every builder target id in every identity parser | lidar tests | `c4bd3596f` |
| `bbc1eb929` | feat(lidar): run every in-image target parser during image verification | lidar | `2c6e45a8f` |
| `2d0ac7c8f` | fix(lidar): report every target-parser failure in one verification pass | lidar | `d82d5502a` |
| `57324285b` | fix(lidar): accept the HA assistant startup gate in the UI bundle | lidar (Lidar bundle contract) | `6a78fe1bb` |
| `463a6370e` | fix(lidar): run the target-identity guard in the MT8167 image verifier | lidar | `cbc7eddf1` |
| `326072055` | chore(mt8167-arm64): take dtc from LIDAR_DTC or PATH | lidar tooling | `00baa08d0` |
| `55941f9d0` | feat(mt8167-arm64): define the Lidar boot-chain backup set | lidar | `d0e875863` |
| `82958b732` | feat(lidar): verify the expdb chain generation before flash writes | lidar | `380435054` |
| `83e9caae7` | feat(lidar): add reviewed preparation command | lidar | `e2bf28e7f` |
| `e347165b7` | feat(lidar): package the Thread border router service | lidar | `f4031dd24` |
| `f9ac5cd9a` | feat(lidar): generate donor-derived chain artifacts from a verified backup | lidar | `cbbacaf9a` |
| `3617d6650` | feat(lidar): stage radio helpers and harden otbr build | lidar | `567dad349` |
| `02ef8ad6a` | fix(mt8167): validate Lidar radio helpers before staging | lidar | `d1f07f20e` |
| `671a2caf9` | fix(lidar): raise speaker output to the stock driver gain | lidar (`lidar_chain` / lidar target profile) | `5c9344d61` |
| `40bf6f0b6` | feat(lidar): ship the Thread border agent with D-Bus and Avahi | lidar | `2ebe8111a` |
| `7011650f9` | feat(wakeword): compile LayerNorm classifier kernels into the reduced runtime | duplicate of `9bae088cc` | dropped from Lidar; identical patch at `9bae088cc`; old commit retained by `backup/2026-11-24/feature/lidar-support-0.14.6` |

Duplicates: `git patch-id --stable` gives `a18ecd69abf7c6530b2c0d6ea5667a26e25cf476`
for all three of `9bae088cc`, `7011650f9`, `2ce7c9d3b`. `feature/lidar-wake-ops`
(`2ce7c9d3b`) additionally is just the Lidar branch plus that wake commit; it has
no commit of its own.

`fix/lidar-efr32-nodes` (0.14.5 line, 12 commits) was already ported into the
0.14.6 Lidar branch during the 2026-11-22 rebase; its mapping is recorded in
`private/lab/phase-07/platform-rebase.md` and its head is tagged
`archive/lidar-efr32-nodes-0.14.5` (`32f3dbdc4`). No debug-only commit exists.

## Commands and results

Fetch and classification:

```
git fetch --all --prune
git merge-base <branch> origin/main          # all topics were already on 37fc39aa6
git log --oneline origin/main..<branch>
git show --stat --name-only <commit>
git patch-id --stable < <(git show <commit>)
git cherry <other> <branch>
```

Rewrite (temporary worktree `/tmp/wt-audit-platform`, detached at `origin/main`).
This ran before the 2026-11-24 pause; after the pause the same commits were still
in the object store, so the branches were pointed at them instead of being
rebuilt, which is why the SHAs above are the ones this command sequence made:

```
git worktree add /tmp/wt-audit-platform --detach origin/main
git switch -c audit/general-new
git cherry-pick -x ad4e21f83 85d72c179 0e1048a53 60f3cc4f5 ffa448773 ba81a7e6b 07549ae35 0a4d7a6e0
git switch -c audit/lidar-new
git cherry-pick -x 8e08af75f fda949e51 1cdd80b5d 9d18ef0d8 e32cddeb7 a873cc628 \
  6c7a28718 981e89040 2f830f9ec d7ad2ac48 94af033cf 064c1df2e
git cherry-pick -n 2278dedde     # then re-point PINNED_COMMIT, commit -F (message updated)
git cherry-pick -x 3fce9b077 af4bcba2b a09f6cd5b bbc1eb929 2d0ac7c8f 57324285b \
  463a6370e 326072055 55941f9d0 82958b732 83e9caae7 e347165b7 f9ac5cd9a 3617d6650 \
  02ef8ad6a 671a2caf9 40bf6f0b6
```

Every cherry-pick applied without conflict; `9d18ef0d8` and `d7ad2ac48`
auto-merged in `tools/mt8163-arm32/airplay/audio_engine.c`. The only content
edit in the rewrite is the re-pinned reconciler SHA:

```
tools/mt8163-arm32/test_multi_target.py: PINNED_COMMIT
  07549ae3542fd9d08116c169b1180b4537d03548 -> ced303f8883d99a66db220d707882647f6fba65d
```

Pin evidence (the moved commit cannot keep its SHA because its parent is a Lidar
commit):

```
git show 07549ae35:tools/mt8163-arm32/initramfs/libreecho-reconcile-features | sha256sum
git show ced303f88:tools/mt8163-arm32/initramfs/libreecho-reconcile-features | sha256sum
  17257a236577e796e748a528759574837769c54c9e50fe2c2d36fd0f5fcf9741  (both)
git log --oneline ced303f88..HEAD -- tools/mt8163-arm32/initramfs/libreecho-reconcile-features
  (empty: no later commit changes the pinned file)
```

Branch moves:

```
git branch -m feature/lidar-support-0.14.6 feature/lidar-support   # in the primary worktree
git checkout -B feature/lidar-support 2ebe8111a                    # clean worktree
git branch -f fix/general-fixes-from-lidar-port 08e4b9872
```

Range-diff, old vs new (`git range-diff origin/main..<old> origin/main..<new>`):
all 38 common commits pair 1:1 with no content difference; the only additions are
`(cherry picked from …)` trailers plus the one re-pin above. `7011650f9` shows as
`<` (dropped) because it is the duplicate wake patch.

Trial integration (`rerere.enabled=true`, `rerere.autoupdate=true`, in
`/tmp/wt-trial-platform`; `private/integration/` untouched):

```
git switch -c trial-integration
git merge --no-ff --no-edit fix/general-fixes-from-lidar-port   # clean, 15 files
git merge --no-ff --no-edit feat/wake-layernorm-ops             # clean, 1 file
git merge --no-ff --no-edit feature/lidar-support               # clean
```

Tree diff of the trial merge against the old combined state `40bf6f0b6` (which
already contains the wake patch):

```
git diff --stat 40bf6f0b6 HEAD
 tools/mt8163-arm32/test_multi_target.py | 2 +-
```

The single hunk is the intended re-pin; there is no other difference (in
particular the wake patch and every Lidar byte are unchanged).

Host tests on the trial merge (`tools/mt8163-arm32`):

| Test | Result |
| --- | --- |
| `python3 -m unittest -v test_reconcile_topology_failure` (added by `07549ae35`) | 2 run, OK |
| `python3 airplay/test_audio_engine_sendspin.py` (changed by `0a4d7a6e0`) | PASS |
| `bash airplay/test_music_analysis_tap.sh` (changed by `0a4d7a6e0`) | ok |
| `python3 -m unittest test_multi_target` | 40 run, 16 failures, 15 errors |

`test_multi_target` failures are environmental and pre-existing: on `origin/main`
the same file is 37 run, 16 failures, 12 errors (measured in a detached worktree).
The only new failures are the three Lidar tests, and all 15 errors on the trial
are `FileNotFoundError: '/bin/busybox'` (the host has no busybox; earlier runs
supplied one in a bwrap namespace). No regression from the rewrite. The
`RadarTreeDiffTests` pin is therefore verified by the byte comparison above, not
by running that test.

## Manifest entry

```json
{
  "name": "LibreEcho-Platform",
  "path": "private/forks/LibreEcho-Platform",
  "integration_path": "private/integration/LibreEcho-Platform",
  "base": "origin/main",
  "in_ota": true,
  "topics": [
    {"branch": "fix/general-fixes-from-lidar-port", "scope": "general"},
    {"branch": "feat/wake-layernorm-ops", "scope": "general"},
    {"branch": "feature/lidar-support", "scope": "lidar"}
  ]
}
```

## Owner deletes

`git branch -d` refuses all of these (not fully merged by SHA even though every
patch is represented), and `git branch -D` is blocked by the safety net:

| Branch | Head | Where its commits live |
| --- | --- | --- |
| `feature/lidar-wake-ops` | `2ce7c9d3b` | all on `feature/lidar-support`; wake patch as `9bae088cc`; tag `archive/lidar-wake-ops` |
| `fix/reconcile-topology-nonfatal` | `07549ae35` | `ced303f88` on `fix/general-fixes-from-lidar-port` |
| `fix/sendspin-media-status` | `0a4d7a6e0` | `08e4b9872` on `fix/general-fixes-from-lidar-port` |
| `fix/lidar-efr32-nodes` | `32f3dbdc4` | ported per `platform-rebase.md`; tag `archive/lidar-efr32-nodes-0.14.5` |
| `trial-integration` | `d4cf88200` | throwaway merge of the three topics; delete freely |

## Notes

- `rerere.enabled` / `rerere.autoupdate` were set to `true` in this repo for the
  trial merge (and left set for the real integration rebuild).
- Backup tags `backup/2026-11-24/<branch>` hold every old head; they were created
  before the pause and were not extended.
- The primary worktree `private/forks/LibreEcho-Platform` checks out
  `feature/lidar-support` at `2ebe8111a`; `private/forks/LibreEcho-Platform-wakeops`
  keeps `feat/wake-layernorm-ops` at `9bae088cc`. Both trees are clean.
- Not run: the full Platform host suites and hardware checks (out of scope for
  this audit).
