# Hosted CI readiness for the Lidar branches

Evidence gathered 2026-11-26. Host evidence only; no hosted run has executed.

## Prerequisite: branch cleanup

Done locally, not on the forks. Every branch that `delete-old-branches.sh` names
(`fix/lidar-efr32-nodes`, `fix/lidar-port-identity`, `fix/lidar-6.18*`,
`experiment/lidar-*`, `feature/lidar-support-6.1`) is gone from the local clones
and still reachable through the `archive/*` tags. The fork remotes were not
touched (`delete-old-branches.sh:3`, "Nothing is pushed"); for example
`TomGrozev/LibreEcho-Linux` still has `fix/lidar-port-identity` at `47feddd6`.
Old remote branches do not affect CI, which builds only the ref that is
dispatched.

## Topic branch heads: local vs fork

`fork` remote for every manifest repository, `git ls-remote fork`:

| Repository | Branch | Local | Remote | State |
| --- | --- | --- | --- | --- |
| LibreEcho | `feature/lidar-support` | `1c844cd` | `7bdab28` | local has `be15ef0` (mixed-kernel guard) + this session's `ci(release)` commit |
| LibreEcho | `feat/wakeword-convert` | `80f53ed` | `80f53ed` | same |
| LibreEcho-UI | `feat/wake-word-selection` | `b65ed2c` | `f662af6` | local has one bot commit on top |
| LibreEcho-UI | `feature/lidar-support` | `520f90c` | `520f90c` | same |
| LibreEcho-Linux | `feature/lidar-support` | `cfb5ab1` | `cfb5ab1` | same |
| LibreEcho-Platform | `feature/lidar-support` | `b7a1557` | `b7a1557` | same |
| amonet | `mt8167-lidar` | `1e03d51` | absent | never pushed |
| all others in `integration.json` | topic heads | n/a | equal | pushed |

The pushed commits carry Tom Grozev's PGP signature (for example
`git cat-file commit 7bdab28` shows a `gpgsig` and author/committer
`<GIT_AUTHOR_A>`). The three local
extras (`be15ef0`, `b65ed2c`, `1e03d51`) are authored and signed by
`<BOT_ACCOUNT_A>`; `1c844cd` (this session, `LibreEcho feature/lidar-support`) is
the same.

The old `push-to-forks.sh` was stale (it pushed branches that no longer exist and
omitted four repos). It was replaced on 2026-11-26 by `tools/push-forks.py`, which
reads the branch list from `integration.json`.

## What each fork's CI needs

### LibreEcho-Linux `checks.yml` (the arm64 kernel build)

- Triggers: `push` to `main`, any `pull_request`, `workflow_dispatch`
  (`.github/workflows/checks.yml:3-9`).
- `target_table` runs `libreecho/validate_targets.py`; on this branch
  `libreecho/targets.json` has the `lidar` row (`arch` `arm64`, defconfig
  `mt8167_arm64_defconfig`, DTB `mediatek/libreecho-lidar.dtb`, image `Image`).
- `kernel_build` installs `gcc-aarch64-linux-gnu` and builds `Image` + DTB, then
  uploads CI artifacts (`checks.yml:106-200`). Nothing is released.
- No branch-name restriction, so a dispatch on `feature/lidar-support` runs the
  arm64 lane. `target_artifacts` only uploads workflow artifacts.

### LibreEcho `release-gate.yml` (the generalized validators)

- `workflow_dispatch` exists (`.github/workflows/release-gate.yml:85`), so any
  branch can be dispatched; the job has no source-resolution gate.
- Its existing steps run `tools.test_release_tools` (which covers the Lidar
  installer identity, pin, geometry and signing paths; `tools/test_release_tools.py:622-672`).
- It did not run the target-schema validators. This session adds a
  `target-contracts` job on `LibreEcho feature/lidar-support` (`1c844cd`):
  `validate-targets.py --targets {radar_puffin,biscuit,lidar}` plus
  `build.tests.test_multi_target` and `build.tests.test_target_manifest`, with a
  Platform checkout (`platform_ref` dispatch input, default `main`) because
  `sign_ota_candidate` needs the Platform OTA tools. Locally:
  `LIBREECHO_PLATFORM_SRC=private/integration/LibreEcho-Platform python3 -B -m
  unittest build.tests.test_multi_target build.tests.test_target_manifest` →
  38 tests OK (host run, 2026-11-26).
- Trigger paths for the validator, registry and test files were added to both
  the `pull_request` and `push` lists.

### LibreEcho `build-release.yml` (full product build)

Cannot build the Lidar work from a fork branch as written:

- Dispatch is accepted only from `refs/heads/main|release/*`
  (`build-release.yml:112-113`); a dispatch on `feature/lidar-support` fails in
  `resolve-and-preflight`.
- Even on a `release/*` branch, component sources are hard-coded to
  `https://github.com/aslater3/<component>.git` at the same branch name
  (`build-release.yml:222-241`, `:277`, `:380`, `:683`). The Lidar work is in
  `TomGrozev/*`; `aslater3` has no matching branch, so the run would either
  refuse or build upstream sources without the MT8167 defconfig/DTB.
- Its `contract-checks` job does run `build.tests.test_multi_target`
  (`build-release.yml:340`), so it is the other place the generalized validators
  run, but only once the product workflows run on upstream component branches.

Enabling fork sources would change the deliberate source pinning: the product
build refuses fork-local fixes (`build-release.yml:213-216`). That needs my
decision; it is not part of this plan.

## State after the collaborator invite (2026-11-26 evening)

The bot (`<BOT_ACCOUNT_A>`) is now a collaborator with `push: true`, `admin:
false` on all three forks, and its token carries `repo`, `workflow` and
`write:packages`. Two follow-up checks narrow the earlier blocker:

- `LibreEcho-Platform` now lists 2 workflows (`button-backport.yml`,
  `ota-release.yml`) and 0 runs. Their `created_at` is
  `2026-11-26T06:44:13Z`, nine minutes before the bot's `MemberEvent`
  (`06:53:04Z`), and the repo has no `PushEvent` after 2026-11-23. Registration
  therefore came from my enabling the fork's workflows, not from a push.
- `LibreEcho-Linux` and `LibreEcho` still list `total_count: 0` workflows and
  0 runs, although their default branch `main` does contain the files
  (`checks.yml`, `next-lts-canary.yml`, `parity.yml`; `build-release.yml`,
  `flash-container.yml`, `publish-news.yml`, `publish-release.yml`,
  `release-gate.yml`). The default branches are correct, so a default-branch
  change is not needed.
- A branch push made while a fork is disabled does not register workflows: the
  Linux fork's `CreateEvent` for `feature/lidar-support` at
  `2026-11-22T11:09:18Z` (after the fork) carried that branch's `checks.yml` and
  still left the list empty.
- `/actions/permissions` returns 403 for all three repos ("You must have
  repository read permissions or have the repository Actions policies
  fine-grained permission"), so the token's role (`write`, not `admin`) cannot
  flip the fork switch. Enabling it stays a fork-level setting.

Conclusion: my enabling took effect on `LibreEcho-Platform` only. The
two repos that host the actual CI (`LibreEcho-Linux`, `LibreEcho`) still need
the fork-level "I understand my workflows, go ahead and enable them" click, or
an admin grant so a token can do it.

The GitHub-side 404s are consistent with that: `gh workflow run checks.yml
--ref feature/lidar-support` answers "not found on the default branch" because
no workflow is registered at all, not because the branch's copy is missing.

One local limiter: this session's shell policy gates network writes
(`git push`, `gh workflow run`, `gh api -X PUT`) behind an interactive approval
that a subagent cannot obtain. The dispatch and push commands below are ready
to run but were not executed here.

## Smallest plan to a hosted run

1. I enable workflows on `TomGrozev/LibreEcho-Linux` and
   `TomGrozev/LibreEcho` (Actions tab → "I understand my workflows, go ahead
   and enable them"; `LibreEcho-Platform` is already registered). No secrets are
   needed: both workflows use `permissions: contents: read`.
2. Publish only what the runs need. Chosen approach (2026-11-26): a scratch
   ref for LibreEcho, no topic-branch change; no push at all for Linux.
   - `LibreEcho-Linux feature/lidar-support` is already published at
     `cfb5ab1145c` and equals the local head, so the kernel lane needs no push.
   - `LibreEcho feature/lidar-support`: the fork is at `7bdab28`, the local head
     `1c844cd` is a plain fast-forward (the two bot commits `be15ef0`,
     `1c844cd`). Publish them under a CI-only ref that leaves the topic branch
     at `7bdab28`:
     ```
     git -C private/forks/LibreEcho push fork \
       1c844cd:refs/heads/ci/lidar-target-contracts
     ```
     This publishes the two bot-authored commits (`be15ef0`, `1c844cd`) on a
     new public branch; the topic branch and its history are untouched and my
     signature is not involved. Delete the ref once the runs are recorded
     (`git -C private/forks/LibreEcho push fork --delete ci/lidar-target-contracts`).
   - `LibreEcho-UI feat/wake-word-selection` (`f662af6..b65ed2c`) and
     `amonet mt8167-lidar` have no hosted lane in this plan.
3. Dispatch and collect URLs (after the push in step 2, and after I enable
   workflows in step 1):
   ```
   # Linux kernel lane, on the already-published cfb5ab11.
   # Expected matrix: radar_puffin, biscuit (arm) and lidar (arm64); a manual
   # dispatch sets run_build=true. Artifacts are workflow artifacts only;
   # nothing is released.
   gh workflow run checks.yml -R TomGrozev/LibreEcho-Linux \
     --ref feature/lidar-support

   # LibreEcho release gate on the CI ref that carries 1c844cd. platform_ref
   # defaults to main and only my Platform is cloned, so pass the
   # Lidar branch to exercise the Lidar target tools.
   gh workflow run release-gate.yml -R TomGrozev/LibreEcho \
     --ref ci/lidar-target-contracts -f platform_ref=feature/lidar-support

   gh run list -R TomGrozev/LibreEcho-Linux --limit 3
   gh run list -R TomGrozev/LibreEcho --limit 3
   gh run watch <run-id> -R <repo> --exit-status
   ```
   (run by me or by a token with `actions:write`/`workflow` scope on
   Tom's repos; the bot's token has the scope but the enablement is the gate).
4. Record the run URLs, per-job conclusions and the arm64 artifact digests in
   this file. The `checks.yml` run's artifacts are workflow artifacts only
   (`kernel-artifacts`); nothing is released or published.

### Reauth detail

`tools/reauth.py reauth --apply` (formerly `private/tools/rewrite_fork_commits.py`)
refuses `--no-sign`, signs with the configured key (`commit_as_me` is unavailable
to subagents), and requires a `backup/*/<branch>` tag that equals the current head. The existing
`backup/2026-11-25/*` tags point at pre-first-rewrite heads, so today every
branch would be refused; a fresh tag for each head is needed before the run.
Because the rewrite produces new SHAs, the push must use `--force-with-lease`
pinned to the current remote SHA (`7bdab28` for `LibreEcho
feature/lidar-support`), not a plain push.

## Actions only I can take

- Enable workflows on `TomGrozev/LibreEcho-Linux` and `TomGrozev/LibreEcho`
  (Actions tab → "I understand my workflows, go ahead and enable them").
  `LibreEcho-Platform` is already enabled. Check with
  `gh api repos/<owner>/<repo>/actions/workflows --jq .total_count`: it must be
  non-zero for the dispatch to resolve.
- Approve the `LibreEcho` publication command in step 2 (option c chosen
  2026-11-26: `1c844cd:refs/heads/ci/lidar-target-contracts`; no topic-branch
  change, no force).
- Decide the reauth question for the three bot-authored heads (signing key is
  mine; it is not in this environment: `GNUPGHOME` points at a neutral
  keyring and `user.signingkey` is the bot key). This does not gate the hosted
  runs; it gates the upstream PRs.

## Expected artifacts (for step 4)

The `checks.yml` run builds `radar_puffin`, `biscuit` and `lidar` from
`libreecho/targets.json`. The Lidar (arm64) entries are named
`libreecho-kernel-lidar-Image`, `libreecho-kernel-lidar-dtb`,
`libreecho-kernel-lidar-System.map`, `libreecho-kernel-lidar-config` and the
matrix bundle `libreecho-linux-arm64-<sha>-lidar`
(`checks.yml:168-250`). Record each artifact's `sha256` from
`gh api repos/<owner>/<repo>/actions/artifacts/<id>/zip` (download and hash), and
the run/job conclusions.
