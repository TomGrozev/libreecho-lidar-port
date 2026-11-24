# amonet-koboreru branch audit

Date: 2026-11-24. Repo: `private/forks/amonet-koboreru`.
Remotes: `origin` = `R0rt1z2/amonet-koboreru` (upstream), `fork` =
`TomGrozev/amonet-koboreru`. `git fetch origin` on 2026-11-24 was a no-op. No
push, no rewrite.

## Result

`feature/lidar-support` is a clean topic: 3 commits on current upstream `main`,
nothing of ours outside it, no duplicate and no debug commit. No rebase was
needed and none was done. Working tree clean before and after.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| upstream `main` | `d51af735e5b95fa2c03c0b311d5c05f0f73461d4` | `origin/main`, unchanged by the latest fetch |
| `main` | `d51af735e5b95fa2c03c0b311d5c05f0f73461d4` | same commit |
| base of topic | `d51af735e5b95fa2c03c0b311d5c05f0f73461d4` | `git merge-base` is the upstream tip |
| `feature/lidar-support` | `564251319e6fe8823b5f8ba7b13fa07f869bb3b1` | unchanged, 3 ahead |

There is no local `integration` branch in this clone.

## Commits of ours

`git rev-list --count origin/main..feature/lidar-support` gives 3.

| Sha | Subject | Classification |
| --- | --- | --- |
| `285e1b2` | add experimental Lidar (MT8167) device port | Lidar |
| `9a617f1` | fix Lidar port review findings | Lidar |
| `5642513` | fix(lidar): apply the hardware-proven preloader patch sites | Lidar |

`9a617f1` is review fallout inside the Lidar port, not a general fix: it
touches only `devices/lidar.c`, `include/devices/lidar.h`, the MT8167 platform
files, `include/preloader.h` and `tee.c` for the Lidar path.

Patch-id scan over `git rev-list --all` gave one hit per patch, so no duplicate
exists on another branch.

## Checks

| Command | Result |
| --- | --- |
| `git fetch origin` | no-op, `origin/main` still `d51af73` |
| `git merge-base --is-ancestor origin/main feature/lidar-support` | exit 0 |
| `git rev-list --count origin/main..feature/lidar-support` | 3 |
| patch-id scan for the 3 commits | 1 hit each |
| `git status --porcelain` | empty |

`fork/feature/lidar-support` is `5642513`, the same commit as local, so the
topic is already published on the fork at its current head. Nothing was pushed.

Not run: any build (the brief named none).

## Refs and tags

| Tag | Commit |
| --- | --- |
| `backup/2026-11-24/feature/lidar-support` | `5642513` |
| `backup/2026-11-24/main` | `d51af73` |

No tag was created or moved in this session.

## Open questions

None.
