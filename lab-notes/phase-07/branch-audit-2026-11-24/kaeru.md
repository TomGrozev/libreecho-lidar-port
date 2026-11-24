# kaeru branch audit and rebase

Date: 2026-11-24. Repo: `private/forks/kaeru`.
Remotes: `origin` = `R0rt1z2/kaeru` (upstream), `fork` = `TomGrozev/kaeru`.
All work local. No push.

## Result

`feature/lidar-support` was rebased onto current upstream `main`. The three
topic commits apply cleanly and keep their content. No commit was dropped,
split or duplicated. `private/integration/kaeru` was not touched.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| old base | `2909a08f76f7a71fed547800aea206ca380245c8` | local `main`, 3 behind current upstream |
| upstream target | `21d075824d7d36aa66ca6e664a7d59465a176044` | `origin/main` after `git fetch origin` |
| old topic tip | `0cbe64d8511d4692982c057e488ebee946064141` | `feature/lidar-support` before rebase |
| new topic tip | `1d9cfc218f4c2828a8be29653ba8a1a64f8967fd` | `feature/lidar-support` after rebase |
| `main` | `2909a08` | unchanged, still tracks `origin/main` (behind 3) |
| `integration` | `4709de155ed7aefe018d465b75af654fe0d00937` | unchanged; Main rebuilds it |

New upstream commits brought in by the rebase:

| Commit | Subject |
| --- | --- |
| `dcc317d` | soc: Add support for MediaTek MT8169 |
| `1ddfeed` | kaeru: Add support for Amazon MT8169 tablets |
| `21d0758` | maverick: Update to support latest LK |

## Commits of ours

All three are Lidar work. None is a general fix, a general feature, debug-only
or a duplicate.

| New sha | Old sha | Subject | Classification |
| --- | --- | --- | --- |
| `8696911` | `e7a9cd5` | amazon: add experimental Echo Plus 2nd Gen (Lidar, MT8167) support | Lidar |
| `93b9135` | `66704e6` | amazon: omit unverified fastboot info address for lidar | Lidar |
| `1d9cfc2` | `0cbe64d` | feat(lidar): add the fastboot fetch and peek diagnostics | Lidar |

`git rev-list --count origin/main..feature/lidar-support` gives 3.
Patch-id scan over `git rev-list --all` showed one hit per patch, plus the old
copy of the last two patches still reachable through the backup tag. No patch
exists on any other branch.

## Rebase

Working tree was clean before and after.

```
git config rerere.enabled true
git config rerere.autoupdate true
git rebase --onto origin/main 2909a08
```

Output: `Successfully rebased and updated refs/heads/feature/lidar-support.`
No conflict. `git status --porcelain` is empty.

Range-diff, old `2909a08..0cbe64d` against new `origin/main..feature/lidar-support`:

- commit 1 differs only in context lines: upstream added MT8169 defaults to
  `soc/Kconfig` next to the MT8167 lines this commit adds. The added MT8167
  lines are unchanged.
- commits 2 and 3 are identical (`=`).

## Backup and refs

Backup tags made by Main before this session were not changed:

| Tag | Commit |
| --- | --- |
| `backup/2026-11-24/feature/lidar-support` | `0cbe64d` |
| `backup/2026-11-24/integration` | `4709de1` |
| `backup/2026-11-24/main` | `2909a08` |

No new tag was created. `rerere.enabled` and `rerere.autoupdate` were set to
`true` in this repo.

## Checks

| Command | Result |
| --- | --- |
| `git rebase --onto origin/main 2909a08` | clean, 3 of 3 applied |
| `git range-diff 2909a08..0cbe64d origin/main..feature/lidar-support` | 1 with context-only change, 2 and 3 identical |
| `git status --porcelain` | empty |

Not run: any build or test of kaeru itself (the brief named none), and the
integration rebuild.

## Open questions

None. `main` remains at the old upstream commit and was not moved; that does
not affect the topic.
