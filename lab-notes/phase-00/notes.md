# Phase 0 notes: experimental workspace

Date: 2026-11-10. Workspace root: `/workspace/libreecho`.
Purpose: close the workspace gate so later phases start from known repositories and tools.

## Layout check against README.md

| README path | Present | Notes |
| --- | --- | --- |
| `PLAN.md` | yes | Phase 1 is complete; this phase closes the workspace gate. |
| `reference/` | yes | `dump.tar.gz` and `echo-plus-2-bootchain.zip` unchanged; the extracted reference package sits beside them. |
| `dumps/` | yes | `dumps/stock/` from the original dump plus `dumps/20261110-lidar-readback/` from the Phase 1 reads. |
| `experiments/` | yes | `experiments/phase-01/` from Phase 1; this directory added. |
| `artifacts/` | yes | empty; nothing built yet. |
| `repos/` | yes | see below. |

One deviation: my `mtkclient/` checkout sits at the workspace root, not under
`experiments/`. README lists "mtkclient work" as an `experiments/` purpose, but moving the
checkout now would break the relative paths recorded in the Phase 1 notes and would leave the
tool's own git state behind. It stays where it is and is treated as a host tool checkout, not as
workspace content. Its commit is recorded below.

## Host dependencies

Collected on 2026-11-10T07:40:12Z.

| Tool | Value |
| --- | --- |
| Host | Linux 7.2.11-arch1-1, x86_64, Arch Linux |
| `python3` | 3.14.9 at `/usr/sbin/python3` |
| `git` | 2.56.0 |
| `openssl` | 3.6.5 |
| `gcc` | 16.2.1 20260810 |
| `dtc` | not installed |
| `aarch64-linux-gnu-gcc` | not installed |
| `arm-linux-gnueabi-gcc` | not installed |
| `docker` | not installed |
| `node` / `npm` | v26.13.0 / 12.2.1 |
| `unzip` | 6.00 |
| `sha256sum` | coreutils 0.8.0 |

mtkclient: commit `118a000a83ea31c4f427fe5225abfe964546e05e` on `main`, with four local changes
(the DA log forwarding patch in `mtkclient/Library/DA/xflash/xflash_lib.py` plus the untracked
`hwparam.json`, `.state`, and `logs/` from the Phase 1 sessions). Its virtualenv runs Python
3.13.18. The patch was saved on 2026-11-17 as
`experiments/phase-01/mtkclient-da-logframes.patch`, so a checkout reset does not lose it.

Gaps that later phases will hit: no `dtc` (Phase 4 needs it to compile the Lidar DTS and to
decompile the stock DTB for comparison), no ARM64 or ARM cross toolchain (Phase 4 kernel and
Phase 2 stage-image work), and no Docker (whatever the owning repositories' CI uses). Nothing here
blocks Phase 0, which is a workspace gate.

## Source repositories

Upstream is the GitHub org `aslater3`. The commits below are the `main` heads read with
`git ls-remote` before cloning, so they are the bases the local branches start from.

| Repository | `main` head | Local state |
| --- | --- | --- |
| LibreEcho | `4f5445934679d68863fc0c723b990326fc9ff3d1` | pre-existing clone, clean |
| LibreEcho-Linux | `2922465d65dc709f90ae4fbdf0f3d819eb47b197` | cloned for this phase, clean |
| LibreEcho-Platform | `e917f8f9502509fae26812b5e362c0a3eba1ec7a` | cloned for this phase, clean |
| LibreEcho-Installer-Web | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | cloned for this phase, clean |
| LibreEcho-UI | `b39af308f0d32e5ae56986d4c603195ab524dbc4` | not cloned; not required before Phase 6 |

`LibreEcho-UI` is left uncloned on purpose: the plan only adds UI work if the existing
device-independent code cannot handle Lidar hardware, which Phase 6 decides. Its head is recorded
so that a later clone starts from a known commit.

## Branches

`feature/lidar-support` was created locally in each required repository from the recorded head:

| Repository | Branch | Base commit | Worktree |
| --- | --- | --- | --- |
| LibreEcho | `feature/lidar-support` | `4f5445934679d68863fc0c723b990326fc9ff3d1` | clean |
| LibreEcho-Linux | `feature/lidar-support` | `2922465d65dc709f90ae4fbdf0f3d819eb47b197` | clean |
| LibreEcho-Platform | `feature/lidar-support` | `e917f8f9502509fae26812b5e362c0a3eba1ec7a` | clean |
| LibreEcho-Installer-Web | `feature/lidar-support` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | clean |

`git status --porcelain` is empty in all four after the branch switch. No branch is pushed and no
fork exists. Disk use: LibreEcho-Linux 6.7 GB (a Linux-fork history), LibreEcho-Platform 1.1 GB,
LibreEcho 128 MB, LibreEcho-Installer-Web 2.2 MB, with 17 GB free on `/home` afterwards.

The first LibreEcho-Linux clone attempt was killed by the shell's 300-second job deadline part way
through, so it was deleted and cloned again from scratch with no deadline. The recorded head and
the clean worktree above come from the completed clone.

## Deferred

External repositories (Kaeru, Koboreru) are cloned only with explicit user authorization, and the
plan assigns that to Phase 2. Nothing was cloned from outside the LibreEcho org in this phase.
