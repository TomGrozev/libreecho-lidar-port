# Integration branches and lab OTA builds

The forks and generated worktrees live under `work/`. The topic branches combine
into an integration branch. `tools/integrate.py` and `tools/lab-build.py` build
and install a lab OTA. `AGENTS.md` holds the rules and
[BUILDING.md](../../BUILDING.md) is the fresh-clone build guide; below are the
layout, the commands and the recipes.

## Layout

| Path | Purpose |
| --- | --- |
| `work/forks/<repo>` | Your fork checkout, cloned by `tools/workspace.py init`. Extra worktrees may be attached for topic work. |
| `work/integration/<repo>` | Generated worktree on branch `integration`. Rebuilds replace its contents. |
| `integration.json` | Per-repo fork and upstream URLs, base, topic list in merge order, and `in_ota`. |
| `work/integration/integration.lock.json` | Written by a rebuild: each integration head, the base, the topic heads, and the manifest sha256. |
| `work/inputs/` | Public build inputs fetched and hash-verified by `workspace.py init`. |
| `work/builds/v<version>/` | Build output: boot images, OTA bundle, logs, `provenance.json`, `SHA256SUMS`. |
| `private/` | Private build inputs: `private/local.json` (input paths), the OTA signing keys, the stock boot backup. Never published, never committed. |

You never edit the integration worktree by hand. A rebuild recreates the branch
from the manifest base and replays the topic merges.

The manifest names these forks, each cloned under its `work/forks/` path:

| Repo | Fork path |
| --- | --- |
| `LibreEcho-Platform` | `work/forks/LibreEcho-Platform` |
| `LibreEcho-UI` | `work/forks/LibreEcho-UI` |
| `LibreEcho-Linux` | `work/forks/LibreEcho-Linux` |
| `LibreEcho` | `work/forks/LibreEcho` |
| `LibreEcho-Installer-Web` | `work/forks/LibreEcho-Installer-Web` |
| `kaeru` | `work/forks/kaeru` |
| `amonet` | `work/forks/amonet` |
| `amonet-koboreru` | `work/forks/amonet-koboreru` |

`tools/check.py` fails when a manifest repo has no row here.

## Prepare steps

`python3 tools/workspace.py init` reads `integration.json`, clones the forks, rebuilds the
integration branches and their lock, prepares the build image, and fetches the public build
inputs. It also sets `core.hooksPath` to `.githooks`, so the versioned pre-commit hook
(private-tree guard, identifier scan when `private/` is present, then `tools/check.py`)
applies.

The flags:

- `--no-integrate` skips the integration rebuild.
- `--no-image` skips the build image.
- `--build-image` builds `libreecho-build:local` from the product's
  `build/container/Containerfile`, even when `tools/lab-build.json` pins a digest.
- `--no-inputs` skips the input fetch.

The image is the Ubuntu 24.04 CI runner baseline. It provides the compilers, the cross
toolchains, the pinned host packages and CPython 3.11. The product's public inputs are
staged separately under `work/inputs/`. With a digest, `init` pulls `name@digest`; with a
null digest, it builds the local tag.

`python3 tools/workspace.py doctor` reports what a build still needs in one list: host
tools, podman and the image, free disk below 20 GB, clones, branches, inputs, and empty
`private/local.json` entries. It exits 1 while anything is missing.

## Branch model

Each repository has one base ref in `integration.json`. A topic branch starts
from that base unless its `topics` entry sets `base` to another topic, which
stacks the branches in merge order:

| Topic | Use |
| --- | --- |
| `fix/general-fixes-from-lidar-port` | Fixes that also help the MT8163 boards. One per repository where such fixes exist. |
| `feat/<name>` | A general feature that is not Lidar-specific. It needs its own manifest entry and its own PR. |
| `feature/lidar-support` | Lidar work. Where the manifest lists both, it is stacked on the general fixes topic, so it merges after it. |
| `feat/lidar-radio` | Thread/Zigbee radio work, stacked on `feature/lidar-support` and merged after it. It is not part of the first PR stack; the branch is kept so the work is not lost and can merge once the first stack lands. |

The manifest order is the merge order. `rebuild` merges each topic with
`git merge --no-ff`, so the integration history keeps one merge commit per topic.

Old heads stay reachable through the reflog, not a tag. A rebase or rewrite leaves the
old head at `<branch>@{1}`, and each fork sets `gc.reflogExpire` and
`gc.reflogExpireUnreachable` to `never` so it does not expire. Tag a commit only when
evidence cites it, such as a build that ran on hardware.

## tools/integrate.py

Run it from the workspace root. `--workspace PATH` or `$LIBREECHO_WORKSPACE` overrides
the root.

`python3 tools/integrate.py status [repo...]` prints, for each repository: the base and
its commit, the integration worktree branch, head and dirty state, and each topic's
ahead/behind count, whether the base contains it, where it is checked out, its changed
file count, and any files two topics share. `--strict` exits 1 when an integration or
topic worktree is dirty, or a topic does not contain the manifest base commit.

`python3 tools/integrate.py audit [repo...]` is read-only and reports, per repository:
topic commits already in the base (`git cherry` patch-id matches), the same patch-id on
two topic branches, topics not based on the manifest base, and branches on the `fork`
remote that the manifest does not list. It exits 1 when any repository has a problem.

`python3 tools/integrate.py rebuild [repo...]` recreates the integration branch and
writes the lock (`write_lock`, run by `cmd_rebuild`):

- It enables `rerere.enabled`, `rerere.autoupdate`, `gc.reflogExpire` and
  `gc.reflogExpireUnreachable` in the fork.
- It fetches the base remote. A tag or local base is not fetched unless it is missing,
  then tags are fetched. `--no-fetch` skips this.
- It refuses a dirty integration worktree, then resets the branch to the base and
  merges the topics in manifest order.
- It refuses while `integration.json` has uncommitted changes in the port repo, so the
  lock pins a committed manifest; `--allow-dirty-manifest` overrides that.
- `--only-in-ota` skips repositories whose `in_ota` is not true.
- It refuses while a lab build holds `work/builds/.build.lock`, because resetting a
  worktree mid-compile makes the compiler read half-merged files. Only the build's own
  call passes `--allow-during-build`; an environment variable does not exempt a
  rebuild, so a stray export cannot skip the check.

`python3 tools/integrate.py check-lock` verifies that the lock's manifest sha256
matches `integration.json` and that each recorded worktree exists, is clean, and has
the recorded head (`cmd_check_lock`).

### Conflict handling

A conflicting merge stops the rebuild and leaves the merge in progress. Resolve it in
one of two ways:

1. Fix the commit on the topic branch, then rerun the rebuild. This is the normal fix
   when the topic itself is wrong.
2. Resolve once in the integration worktree: edit the files, `git add` them, and run
   `git commit --no-edit`. `rerere` records the resolution and `rerere.autoupdate`
   applies it on later rebuilds. Rerun the rebuild.

Do not commit unrelated work in the integration worktree. `rerere` keys on the
conflict hunk, so the recorded resolution applies to the same conflict later.

## tools/lab-build.py

`python3 tools/lab-build.py build` produces a signed lab OTA from the integration
worktrees (`cmd_build`). It holds a non-blocking `flock` on
`work/builds/.build.lock` for the whole build, including the container run, so a second
build fails instead of corrupting the first. The steps are:

1. Read `tools/lab-build.json` and pick the version. The default is the highest
   existing lab version plus one patch; `--version X.Y.Z` overrides it.
2. Unless `--no-integrate` is set, run `integrate.py rebuild --only-in-ota` and then
   `check-lock`.
3. Read the lock, compute the source id from its heads, and refuse a dirty or missing
   integration worktree. A successful attempt with the same source id is reused
   unless `--rebuild` is set.
4. Start an attempt directory named `<stamp>-v<version>-<source id>` and drive the
   product's own build from the LibreEcho integration worktree inside the build image
   (`build/build.sh --target lidar --profile ota --no-publish`). That produces
   the kernel, the UI bundle, the boot images (sized by `BOOT_SIZE`), the audio
   engine and the feature payloads, and runs the product OTA pipeline:
   `build/ci/plan-target-manifest.py --target lidar` emits the run directory
   (`feature-plan.json`, `feature-assets.json`, `target.manifest`, `ota-assets/`
   and the provenance record), then `build/ci/ota_v3_product.py` signs it with
   the lab key. The release tag is the product's dev form that `release_tag()`
   derives: `sha7` is the LibreEcho integration head, `source_id` hashes the
   product, Platform, Linux and UI lock heads, and `build_id` hashes
   `lab:<version>`. The signed tar is `libreecho-<tag>.ota.tar`, and the target's
   published asset names carry the `libreecho-lidar-` prefix.
5. Run the verification checks against the tar, the run directory and the built
   artifacts, write `provenance.json` and `SHA256SUMS`, and promote the attempt to
   `work/builds/v<version>/`.

The build runs in the image named by `build_image` in `tools/lab-build.json`: with a
digest, `name@digest`; with a null digest, the local tag `libreecho-build:local`.
`LIBREECHO_BUILD_IMAGE` overrides the image. `--no-container` builds with the host
toolchain instead. A promoted build refuses to overwrite an existing non-empty version
directory. Failed attempts stay under `work/builds/` for inspection, and the five newest
are kept.

The environment for the product build step (build roots, toolchain variables,
the stock boot and key paths, the OpenThread Border Router source) is the
product fork's `build/README.md`, section "Building Lidar locally"; you
supply the two private inputs through `private/local.json` (see
[BUILDING.md](../../BUILDING.md)).

`--lock PATH` reads another lock and implies `--no-integrate`. `--stock-boot`,
`--ota-signing-key` and `--ota-public-key` override the `private/local.json` paths.

What `lab-build.json` holds:

- `build_image`: the image name and digest, or a null digest for the local tag.
- `builds_dir`: the output root, `work/builds`.
- `values`: the product build arguments, `target` and `profile`.

The build directory under `work/builds/` holds `build.log`, `provenance.json` (tool,
config, image, manifest, lock with heads, sources, private input digests, product run,
OTA and outputs, with the check list) and `SHA256SUMS`. A failing check fails the build.

`python3 tools/lab-build.py deploy VERSION --host HOST --yes` installs a finished build
over Wi-Fi adb (`cmd_deploy`). It refuses without `--yes`, rechecks the deliverables against
`provenance.json`, pushes the signed tar and every `ota-assets/` file into
`/data/libreecho/update/asset-cache/<sha256>.part`, and runs
`libreecho-update-fetch assemble-generation` on the device. The device assembles
`/data/libreecho/generations/<txn>` from the signed manifest and those cached parts
without a network fetch, then `libreecho-update install` writes the inactive slot.
Deploy reboots into that slot and polls until it reports the expected generation as
installed, up to 20 minutes. It then reads the boot slot back and compares its hash.
`--host` defaults to `$LAB_DEVICE_HOST`, then `$LIDAR_WIFI`.

The device assembly reads each cached part only when its size and sha256 match the
signed manifest (`libreecho-generation` `assemble`); a cache miss falls back to an
allowlisted HTTPS release base, which deploy seeds against so this cannot happen.
This offline path is reasoned from the Platform script and has not yet run on the
device.

Deploy writes the device and reboots it, so each run needs its own hardware approval.
Build never talks to the device.

## Recipes

### Publishing

Publishing the forks is done by the maintainer's private tooling, which is not part of this
repository. Nothing is pushed by the public tools: `integrate.py` and `lab-build.py` only
read the local forks and write under `work/`.

### Add a general fix

1. In the fork, create or reuse the general topic from its base:
   `git switch -c fix/general-fixes-from-lidar-port <base>`.
2. Commit the fix there.
3. If the branch is new, add it to the repository's `topics` in `integration.json`
   with `"scope": "general"`, in merge order.
4. Run `integrate.py status`, then `rebuild`, then `check-lock`.

### Add a Lidar change

1. Commit on `feature/lidar-support` in the fork.
2. Run `integrate.py rebuild <repo>` and `check-lock`. The branch is already in the
   manifest after the general fixes topic, so the merge order does not change.

### Add a new feat/* topic

1. Create `feat/<name>` from the repository base in the fork and commit there.
2. Add an entry to that repository's `topics` in `integration.json`:
   `{"branch": "feat/<name>", "scope": "general"}`, in the order it should merge.
3. Run `integrate.py rebuild`, then `check-lock`.
4. Add the branch to the Phase 8 PR table in `docs/plan.md`.

### Rebase onto a moved upstream

1. Note the old head with `git rev-parse <branch>`; after the rebase it stays at
   `<branch>@{1}`.
2. Fetch the base remote and rebase the topic onto the new base.
3. If the base ref changed, update `base` in `integration.json`.
4. Resolve conflicts on the topic branch, never in the integration worktree, when the
   topic is what changed.
5. Run `integrate.py rebuild` and `check-lock`.

### Cut a lab OTA

1. Run `python3 tools/integrate.py rebuild --only-in-ota` and `check-lock`.
2. Run `python3 tools/lab-build.py build`. Note the version it prints.
3. Read `work/builds/v<version>/build.log` and `provenance.json`; every
   check must pass.
4. Install only after separate hardware approval:
   `python3 tools/lab-build.py deploy <version> --host <device>:5555 --yes`.

The build is host evidence. A new integration kernel is untested on hardware until a
deploy confirms the slot.
