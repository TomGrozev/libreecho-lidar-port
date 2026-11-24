# LibreEcho-Installer-Web branch audit

Date: 2026-11-24. Repo: `private/forks/LibreEcho-Installer-Web`.
Remotes: `origin` = `aslater3/LibreEcho-Installer-Web` (upstream), `fork` =
`TomGrozev/LibreEcho-Installer-Web`. `git fetch origin` on 2026-11-24 was a
no-op. No push, no rewrite.

## Result

`feature/lidar-support` is a clean topic: 3 commits on current upstream `main`,
nothing of ours outside it, no duplicate and no debug commit. No rebase was
needed and none was done. Working tree clean before and after.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| upstream `main` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | `origin/main`, unchanged by the latest fetch |
| `main` | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | same commit |
| base of topic | `c7cac7ca433015b3e839debc5ac1b99f260bf2a4` | `git merge-base` is the upstream tip |
| `feature/lidar-support` | `5b6477ec2c188f2a9456b903f355df3597ec1932` | unchanged, 3 ahead |
| `integration` | `24674e192d9ca70c20f86e20197e7b50079b9830` | Main rebuilds it; not touched |

## Commits of ours

`git rev-list --count origin/main..feature/lidar-support` gives 3.

| Sha | Subject | Classification |
| --- | --- | --- |
| `3e189f5` | feat(install): add Lidar identity and pin gates | Lidar |
| `fef736c` | test(install): assert the Lidar stage plan takes no backup | Lidar |
| `5b6477e` | fix(install): hide boards that lack hardware acceptance | Lidar, with a general gate |

`5b6477e` adds a `hardwareAccepted` flag to each profile and hides or refuses a
board whose flag is false. Only the Lidar profile sets it false, so the commit
changes no existing Radar or Biscuit behavior. It exists to keep Lidar out of
the normal web installer until hardware acceptance (PLAN.md Phase 7). It stays
on the Lidar topic.

Patch-id scan over `git rev-list --all` gave one hit per patch, so no duplicate
exists on another branch, and no commit here duplicates product wake-word work.

## Checks

| Command | Result |
| --- | --- |
| `git fetch origin` | no-op, `origin/main` still `c7cac7c` |
| `git merge-base --is-ancestor origin/main feature/lidar-support` | exit 0 |
| `git rev-list --count origin/main..feature/lidar-support` | 3 |
| patch-id scan for the 3 commits | 1 hit each |
| `git status --porcelain` | empty |

Not run: the node suites (the brief named no tests for this repo).

## Refs and tags

Backup tags made by Main were left as is:

| Tag | Commit |
| --- | --- |
| `backup/2026-11-24/feature/lidar-support` | `5b6477e` |
| `backup/2026-11-24/integration` | `24674e1` |
| `backup/2026-11-24/main` | `c7cac7c` |

`fork/feature/lidar-support` does not exist; this branch has never been pushed.
The only pre-existing tag is upstream's `archive/feat-auto-fetch-release`,
unrelated to us and left alone.

## Open questions

None.
