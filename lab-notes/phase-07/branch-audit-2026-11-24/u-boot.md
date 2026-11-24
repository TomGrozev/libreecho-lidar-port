# u-boot branch audit

Date: 2026-11-24. Repo: `private/forks/u-boot`.
Remotes: `origin` = `https://source.denx.de/u-boot/u-boot.git` (partial clone,
`blob:none`), `fork` = `TomGrozev/u-boot`. `git fetch origin` printed only a
redirect warning to `https://git.u-boot-project.org/u-boot/u-boot.git`; the full
`origin/master` fetch had timed out before this session, so no `origin/*`
tracking ref exists locally. No push, no rewrite.

## Result

`lidar-fastboot-stage2` is a clean Lidar topic: exactly 1 commit on the
`v2026.10` release tag. There is no local `main`, no other local branch and no
commit of ours outside that topic. No rebase was needed and none was done.
Working tree clean.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| upstream base | `5508406582f6f7120dce0c4b3059819a41788db2` | commit of tag `v2026.10`, "Prepare v2026.10", 2026-10-05 |
| tag object | `a58e2b7af42c179ace2c6210de0a219fa3f3cf3c` | annotated tag `v2026.10`, peels to `55084065` |
| topic | `dffcf3d8cb2f781aa9ab611772d8ef51709a32f8` | `lidar-fastboot-stage2` |
| topic parent | `5508406582f6f7120dce0c4b3059819a41788db2` | equals the tag commit |
| fork copy | `dffcf3d8cb2f781aa9ab611772d8ef51709a32f8` | `fork/lidar-fastboot-stage2` |

Manifest base for this repo: `refs/tags/v2026.10`, since `refs/remotes/origin/...`
is unavailable because the full fetch timed out. `git rev-list --count
v2026.10..lidar-fastboot-stage2` gives 1.

## Commits of ours

| Sha | Subject | Classification |
| --- | --- | --- |
| `dffcf3d8` | feat(lidar): add the stage-2 fastboot candidate | Lidar |

The commit touches only the Lidar DTS, MT8516 machine hooks, the
`board/libreecho/lidar` board files, the `mt8516_lidar_defconfig`, and the USB
gadget and console paths that board needs. No general fix, no debug commit.

## Checks

| Command | Result |
| --- | --- |
| `git rev-parse v2026.10^{commit}` | `55084065` |
| `git rev-parse dffcf3d8^` | `55084065` |
| `git rev-list --count v2026.10..lidar-fastboot-stage2` | 1 |
| `git rev-parse fork/lidar-fastboot-stage2` | `dffcf3d8`, same as local |
| `git status --porcelain` | empty |
| `git rev-list --count --all --no-merges` | 2 (tag commit plus the topic) |

Not run: any build or test (the brief named none).

## Refs and tags

No backup tag was made for this repo by Main (only one branch existed and the
head is also on the fork). No tag was created or moved in this session.

## Open questions

None. If a future integration wants to merge against a branch instead of a tag,
`origin/master` has to be fetched first; the tag is the correct base today.
