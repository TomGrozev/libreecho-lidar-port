# LibreEcho (product) branch audit and trial integration

Date: 2026-11-24. Repo: `private/forks/LibreEcho`.
Remotes: `origin` = `aslater3/LibreEcho` (upstream), `fork` =
`TomGrozev/LibreEcho`. `git fetch origin` added three upstream branches
(`ci/discord-dev-pointer-announce`, `fix/325-reboot-guard-0.14.7`,
`release/0.14.7`); `origin/main` stayed at `bc16752`. No push, no rewrite.

## Result

Both topics already sit on current upstream `main` `bc167529`, so no rebase was
needed and none was done. `feature/lidar-support` carries 11 commits and
`feat/wakeword-convert` carries 1. The wake-word work is not duplicated on the
Lidar topic: the file sets are disjoint and every patch-id is unique.

A trial integration in `/tmp` merged `origin/main`, then `feat/wakeword-convert`,
then `feature/lidar-support`, with `rerere` on. Both merges were clean. The
Lidar target validates and `tools.test_release_tools` passes on the trial head.
The trial worktree was removed afterwards; no trial branch was created.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| upstream `main` | `bc1675298c259dac703986fa4ba01d534ee67953` | `origin/main` |
| `main` | `bc1675298c259dac703986fa4ba01d534ee67953` | unchanged |
| base of `feature/lidar-support` | `bc1675298c259dac703986fa4ba01d534ee67953` | merge-base equals upstream tip, 0 behind |
| `feature/lidar-support` | `8e0d52f43c972e8306e6dd9e47037bac0459ee64` | unchanged, 11 ahead |
| base of `feat/wakeword-convert` | `bc1675298c259dac703986fa4ba01d534ee67953` | merge-base equals upstream tip |
| `feat/wakeword-convert` | `ced4fb80bded780f8dce2872068f87e31d9dbd09` | unchanged, 1 ahead, checked out in `LibreEcho-wakeops` |

`git rev-list --left-right --count origin/main...feature/lidar-support` gives
`0 11`; the same for `feat/wakeword-convert` gives `0 1`. Both are current.

## Commits of ours

`feature/lidar-support`, oldest first:

| Sha | Subject | Classification |
| --- | --- | --- |
| `eefd5989` | feat(release): generalize target contracts beyond MT8163 | general feature, no Lidar data |
| `2574049` | feat(release): register the Lidar target | Lidar |
| `7f0d5c6` | feat(release): support Lidar in the one-shot installer | Lidar |
| `17ed788` | test(release): drop generalized TWRP planner from incidental biscuit list | general test fix, follows `eefd5989` |
| `737cb90` | feat(build): pin an aarch64 kernel cross for Lidar CI | general build/CI feature with an MT8167 branch |
| `b74cfd9` | test(release): assert the Lidar installer takes no backup | Lidar |
| `9631fee` | feat(lidar): check the expdb chain generation before every flash | Lidar |
| `ca80410` | fix(release): refresh installer digest and mock the expdb gate in the backup test | Lidar follow-up |
| `73508b6` | feat(release): refuse images and bundles carrying EFR32 firmware | general release check |
| `f449b3f` | feat(release): refuse donor-derived boot-chain assets | general release check, MTK header rule breaks MT8163 targets until `8e0d52f` |
| `8e0d52f` | fix(release): scope MTK boot-chain checks to the Lidar target | Lidar scoping plus general generator-manifest check |

`feat/wakeword-convert`:

| Sha | Subject | Classification |
| --- | --- | --- |
| `ced4fb8` | feat(wakeword): convert LayerNorm classifiers against the runtime operator set | general feature, separate topic |

Duplicate check. Patch-id for all 12 commits, compared against
`git rev-list --all` (597 non-merge commits at audit time): each patch-id has
exactly one hit. No commit from `ced4fb8` appears on `feature/lidar-support`,
and no commit appears on an upstream branch.

No debug-only commit and no experiment branch exists. The only stash is Main's
`wake-word converter draft` (also tagged `archive/stash-wake-word-draft`,
`5fad7fa`); it is not a branch and was left alone.

## Rewrite decision

No rewrite. Main's instruction was to rewrite only for a clearly
target-independent bug fix. The release-check commits that look general are
features, not fixes for existing targets: `f449b3f` deliberately changes
behavior for every target and `8e0d52f` repairs the MT8163 breakage that
`f449b3f` introduced on this same branch. `8e0d52f` also depends on the Lidar
target being registered (`--target lidar` resolves through the registry added by
`2574049`), so it cannot be lifted onto a general branch ahead of the Lidar
data without splitting a commit. Both topics are therefore unchanged.

This leaves general work on the Lidar topic, which the one-topic-per-change
workflow would normally split. See "Open questions".

## Trial integration

Commands, run in `/tmp/wt-libreecho-trial` (a `git worktree` at `origin/main`);
`rerere.enabled` and `rerere.autoupdate` were set to true in the repo first.

```
git worktree add /tmp/wt-libreecho-trial --detach origin/main
git merge --no-ff feat/wakeword-convert -m "trial: merge feat/wakeword-convert"
git merge --no-ff feature/lidar-support -m "trial: merge feature/lidar-support"
```

| Step | Result |
| --- | --- |
| base | `bc16752` |
| merge `ced4fb8` | clean, `ort` strategy, merge commit `29e7c27` |
| merge `8e0d52f` | clean, `ort` strategy, merge commit `94f7126` |
| trial head | `94f71262b1b5cbfc6580d16fe9e2a95ddf5681f1` |

No conflict occurred, so rerere recorded nothing.

Checks on the trial head, each run once:

| Command | Result |
| --- | --- |
| `python3 build/ci/validate-targets.py --targets lidar` | `{"board": "lidar", "target_descriptor_sha256": "b57f3cecc965a9d39fd54f50c420ba0acc3a1bb37e508187dc5caeb67a23cf28"}` |
| `python3 -m unittest tools.test_release_tools` | `Ran 127 tests in 133.370s`, `OK` |

Cleanup:

```
git worktree remove /tmp/wt-libreecho-trial
git worktree remove --force /tmp/wt-libreecho-trial
```

Both commands were refused by the tool approval layer ("requires approval but
no interactive UI available"), so the trial worktree is still registered at
`/tmp/wt-libreecho-trial` on detached `94f7126`. It is on the owner-deletes
list. No trial branch was created, so none was deleted.
`private/integration/` was not touched.

## Refs and tags

| Ref | Commit |
| --- | --- |
| `backup/2026-11-24/feature/lidar-support` | `8e0d52f` |
| `backup/2026-11-24/feat/wakeword-convert` | `ced4fb8` |
| `backup/2026-11-24/main` | `bc16752` |
| `archive/stash-wake-word-draft` | `5fad7fa` (Main's stash tag) |

No tag was created or moved in this session. `rerere.enabled` and
`rerere.autoupdate` were set to `true`.

## Mapping table

| Old sha | New sha | Where |
| --- | --- | --- |
| `eefd5989` | `eefd5989` | `feature/lidar-support` (unchanged) |
| `2574049` | `2574049` | `feature/lidar-support` |
| `7f0d5c6` | `7f0d5c6` | `feature/lidar-support` |
| `17ed788` | `17ed788` | `feature/lidar-support` |
| `737cb90` | `737cb90` | `feature/lidar-support` |
| `b74cfd9` | `b74cfd9` | `feature/lidar-support` |
| `9631fee` | `9631fee` | `feature/lidar-support` |
| `ca80410` | `ca80410` | `feature/lidar-support` |
| `73508b6` | `73508b6` | `feature/lidar-support` |
| `f449b3f` | `f449b3f` | `feature/lidar-support` |
| `8e0d52f` | `8e0d52f` | `feature/lidar-support` |
| `ced4fb8` | `ced4fb8` | `feat/wakeword-convert` |

No commit was dropped or archived in this repo.

## Open questions

1. General features sit on the Lidar topic (`eefd5989`, `17ed788`, `737cb90`,
   `73508b6`, `f449b3f`). The new workflow wants them on general topics with
   `feature/lidar-support` stacked on top. A split is possible but needs
   reordering and a decision on `8e0d52f`, which depends on the Lidar
   registration. Options: keep as is (one mixed Lidar PR), or split into
   `feat/target-generalization` (`eefd5989`, `17ed788`, `737cb90`) plus
   `fix/general-fixes-from-lidar-port` (`73508b6`, `f449b3f`, with the MTK
   scoping either kept on Lidar or folded into `f449b3f`). No rewrite was done
   pending that decision.
2. The OTA build script calls the product repo at
   `private/forks/LibreEcho/tools/check-release-components.py`, not the
   integration worktree (`private/lab/phase-07/ota-v0.2.37-build.sh:272`).
   `in_ota` is true, but a rebuilt integration is not what that script reads
   today.
