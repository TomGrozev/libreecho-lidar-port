# LibreEcho (product) rebase onto 0.14.6

Status: **done**. The fork carried no commits of its own: `main` and
`feature/lidar-support` were both `4f54459`, an ancestor of `origin/main`, so
the rebase is a fast-forward of both branches to `origin/main` (`bc167529`).
There was nothing to port, split or drop, and no general-fix branch was needed.
Both focused checks pass on the new head.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| old base / old tip | `4f5445934679d68863fc0c723b990326fc9ff3d1` | 0.14.5 era, `main` == `feature/lidar-support` |
| upstream target | `bc1675298c259dac703986fa4ba01d534ee67953` | `origin/main`, 0.14.6 plus post-release fixes |
| `feature/lidar-support` | `bc1675298c259dac703986fa4ba01d534ee67953` | set to the upstream target |
| `main` | `bc1675298c259dac703986fa4ba01d534ee67953` | fast-forwarded to the upstream target |
| `fix/general-fixes-from-lidar-port` | not created | no general fixes exist in this fork |

### Base choice evidence

The contract says to match Platform's choice between `origin/main` and
`release/0.14.6`. On the Platform fork,
`git merge-base origin/main feature/lidar-support-0.14.6` is
`37fc39aa6092491bcb5f12b77a8151179ffd122b`, and that commit is itself
`Merge pull request #326 from aslater3/release/0.14.6`, i.e. Platform based on
`origin/main` after the 0.14.6 line was merged into it, not on the release
branch tip (`private/lab/phase-07/platform-rebase.md`, Bases table). The UI
record likewise names `upstream/main` (`private/lab/phase-07/ui-rebase.md`).

In this repository `origin/release/0.14.6` (`8c6c2590620378ea1ae3fbd4a85a7526bd3ab7bb`)
is an ancestor of `origin/main`: `git log --oneline origin/release/0.14.6..origin/main`
lists 0 commits in the reverse direction and `git merge-base` confirms it is
contained. So `origin/main` is the same 0.14.6 base at its current tip,
consistent with Platform and UI. Chosen: `origin/main` = `bc167529`.

## Commits of ours

Verified with `git log --all` against the fetched `origin` refs:

- `git merge-base main origin/main` is `4f54459`, so `main` and
  `feature/lidar-support` are ancestors of the upstream target.
- `git log --oneline origin/main..HEAD` is empty for both old branches.
- `git rev-list --all --not --remotes=origin` returns 41 commits, all reachable
  only through local `archive/*` and `radar-puffin-v0.13.*` tags, and all
  authored by the upstream maintainer (`Andy Slater` / `aslater3`); they are
  upstream history, not ours.

Result: no general fix, no Lidar commit, no debug commit, nothing to port or
drop. `feature/lidar-support` is exactly the upstream base, which is where the
Phase 8 `lidar.json` / schema / validator work starts.

## Backup and ref moves

Before any move, the checked-out heads were:

| Ref | Commit |
| --- | --- |
| `main` | `4f5445934679d68863fc0c723b990326fc9ff3d1` |
| `feature/lidar-support` | `4f5445934679d68863fc0c723b990326fc9ff3d1` |
| working tree | clean (`git status --porcelain` empty) |

Backup: annotated tag `archive/product-0.14.5` (tag object
`b71219816ae82fb124f2c6375ad01cc5c1aa83e1`) → `4f54459`. The commit is also an
ancestor of `origin/main`, so it is preserved upstream as well; no bundle was
needed.

Moves, all local, no push and no fetch beyond the already-present refs:

```
git checkout --detach origin/main
git branch -f feature/lidar-support origin/main
git branch -f main origin/main
git checkout feature/lidar-support
```

`git reset --hard` was not used. Both branches now track `origin/main`.

## Tests (new head `bc167529`)

Run once from the fork root on 2026-11-23:

| Command | Result |
| --- | --- |
| `python -m unittest tools.test_release_tools` | **OK**, 108 tests in 131.560s |
| `python3 build/ci/validate-targets.py` | **exit 0**; `radar_puffin` `b9e8c5a7…`, `biscuit` `7c58bec0…` descriptor hashes printed |

`validate-targets.py` still validates only the two existing targets; Lidar is
absent by design until the Phase 8 schema work.

## Archive tags

- `archive/product-0.14.5` → `4f54459` (annotated, created 2026-11-23, local only).

No other tags were created or moved. Nothing was pushed.
