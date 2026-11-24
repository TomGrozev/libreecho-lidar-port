# LibreEcho-Installer-Web rebase onto upstream main

Status: **verified, no-op rebase**. Both local branches already sit on current
upstream `main` (`c7cac7ca433015b3e839debc5ac1b99f260bf2a4`), and neither carries
a commit of ours. Nothing was ported, dropped or rewritten. The focused node
suites from `.github/workflows/pages.yml` pass on that base.

Repo: `private/forks/LibreEcho-Installer-Web`. Remotes: `origin` =
`aslater3/LibreEcho-Installer-Web` (upstream), `fork` =
`TomGrozev/LibreEcho-Installer-Web`. `git fetch origin` and `git fetch fork`
were run on 2026-11-23; both return `main` at `c7cac7c`. No push, no branch
rewrite, no other fork and no device command was touched.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| old base | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | local `main`, 2026-10-30, "Merge pull request #29 from aslater3/fix/28-resume-direct-install" |
| upstream target | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | `origin/main`; `fork/main` is the same commit |
| old tip | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | both `main` and `feature/lidar-support` |
| `feature/lidar-support` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | unchanged, equals `main` |
| `fix/general-fixes-from-lidar-port` | not created | no general fix exists in this repository |

### Which upstream ref, and why

Current upstream `main`. This repository versions independently of the product
`LibreEcho` release line: upstream publishes no `release/0.14.6` branch and no
version tags: its only tags are `archive/feat-auto-fetch-release` and its only
branches are `main` plus unmerged feature branches (checked with
`git ls-remote`). `PLAN.md` names `c7cac7c` as the installer-web baseline for the
Phase 7 rebase item, and Platform's generic branch was likewise built from
`origin/main` (`platform-rebase.md`: `37fc39aa6`). There is therefore no
`origin/main` vs release-ref ambiguity to resolve here.

## Heads recorded before work

| Branch | Hash |
| --- | --- |
| `main` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` |
| `feature/lidar-support` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` |

Backup method: **no backup tag or bundle was created, deliberately**. Both
branch tips are published upstream commits (`origin/main` and `fork/main` point
at `c7cac7c`), so nothing exists locally that upstream does not already
preserve. A `archive/...` tag at the old tips would duplicate an upstream commit
and imply discarded work that does not exist. Working tree was clean; no stash
exists.

The pre-existing tag `archive/feat-auto-fetch-release` →
`10215033edecc8ac1efd4eadf22e51844ce27c9a` is upstream's own archive of an
abandoned 2026-09-30 development line (`feat: fetch and verify release bundles
from static or development mirrors`, author Andy Slater). It is not an ancestor
of `main` and no branch contains it, but it is not our work and is left as is.

## Commits of ours

None. Verified against the upstream refs:

```
git rev-list --count origin/main..main                      # 0
git rev-list --count origin/main..feature/lidar-support     # 0
```

`git log --all --not origin/main` returns only upstream-owned work: the nine
unmerged commits on `origin/*` feature branches (`fix/0.13.21-bridge-delivery`,
`feat/initial-setup-config`, etc.) and the archived tag line above. Every author
is `aslater3`. Nothing to classify as general fix / Lidar / debug, so nothing was
ported and nothing was dropped.

## Rebase action

None required: rebasing either branch onto `origin/main` would be a no-op, and
`feature/lidar-support` already points at the base. The branches were left in
place and re-read after the fetches to confirm this. No push was run, so
`feature/lidar-support` still exists only locally; it will be pushed only as the
Phase 8 `feature/lidar-support` → `main` PR.

## Tests (run once, at `c7cac7c`, 2026-11-23)

There is no `package.json`; the runner is the one in
`.github/workflows/pages.yml` ("Unit-test the protocol layers"). Node v26.13.1 on
this host.

```
cd lib/fastboot && node --test test_fastboot.mjs
cd lib/adb     && node --test test_adb.mjs
node --test js/test_amonet.mjs js/test_amonet_visibility.mjs \
  js/test_app.mjs js/test_auto_fetch.mjs js/test_device_choice_copy.mjs \
  js/test_direct_install.mjs js/test_direct_review_fixes.mjs \
  js/test_empty_identity_query.mjs js/test_fastboot_mode_refusal.mjs \
  js/test_post_install.mjs js/test_post_install_app.mjs \
  js/test_publication_trust.mjs js/test_recovery.mjs js/test_recovery_entry.mjs \
  js/test_recovery_guided.mjs js/test_recovery_identity_322.mjs \
  js/test_recovery_metadata.mjs js/test_recovery_races.mjs js/test_release.mjs \
  js/test_report.mjs js/test_resume_28.mjs js/test_safety.mjs \
  js/test_stage_hardening.mjs js/test_targets.mjs js/test_transports_release.mjs \
  js/test_unpinned_lk.mjs js/test_usb_single_owner.mjs
```

(The third command spells out the `js/test_*.mjs` set that the workflow's glob
expands to, because this shell refuses an unverifiable glob.)

| Step | Result |
| --- | --- |
| `lib/fastboot` | 62 tests, **62 pass, 0 fail**, 0 skipped |
| `lib/adb` | 23 tests, **22 pass, 0 fail**, 1 skipped (`ADB_BIG_MB` opt-in big push) |
| `js/test_*.mjs` | 375 tests, **373 pass, 0 fail**, 2 skipped |

Both skips are opt-in lanes (hundreds-of-MB push and the second `js` skip are
documented in their files), not environment failures. The workflow's Python
"site contract" step was not re-run; this record covers the node suites the
contract named.

## Archive tags

None created (see "Backup method"). No experiment branch exists in this clone
that needs archiving: the only local branches are `main` and the Phase 8
`feature/lidar-support`, both at the upstream base.
