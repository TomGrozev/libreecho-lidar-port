# Integration branches and lab OTA builds

This page covers the source side of the port: where the forks and generated worktrees
live, how topic branches combine into an integration branch, and how `tools/integrate.py`
and `tools/lab-build.py` build and install a lab OTA. `AGENTS.md` holds the rules; this
page holds the layout, the commands and the recipes.

## Layout

| Path | Purpose |
| --- | --- |
| `private/forks/<repo>` | The owner's fork checkout. Extra worktrees may be attached for topic work. |
| `private/integration/<repo>` | Generated worktree on branch `integration`. Rebuilds replace its contents. |
| `integration.json` | Per-repo base, topic list in merge order, and `in_ota`. |
| `private/integration/integration.lock.json` | Written by a rebuild: each integration head, the base, the topic heads, and the manifest sha256. |
| `tools/lab-build.json` | Every build input that is not a repository, pinned by path and sha256. |
| `private/artifacts/builds/v<version>/` | Build output: boot images, OTA bundle, logs, `provenance.json`, `SHA256SUMS`. |

The integration worktree is never edited by hand. A rebuild recreates the branch from
the manifest base and replays the topic merges.

## Branch model

Each repository has one base ref in `integration.json`. A topic branch starts from that
base:

| Topic | Use |
| --- | --- |
| `fix/general-fixes-from-lidar-port` | Fixes that also help the MT8163 boards. One per repository where such fixes exist. |
| `feat/<name>` | A general feature that is not Lidar-specific. It needs its own manifest entry and its own PR. |
| `feature/lidar-support` | Lidar work. Where the manifest lists both, it is stacked on the general fixes topic, so it merges after it. |

The manifest order is the merge order. `rebuild` merges each topic with
`git merge --no-ff`, so the integration history keeps one merge commit per topic.

Old heads stay reachable. Use `archive/<branch>-<date>` for a head a rebase or move
takes off its branch, and `backup/<date>/<branch>` when a cleanup replaces a branch.
Commit only to a topic branch or under an archive tag.

## tools/integrate.py

Run it from the workspace root. `--workspace PATH` or `$LIBREECHO_WORKSPACE` overrides
the root.

`python3 tools/integrate.py status [repo...]` prints, for each repository: the base and
its commit, the integration worktree branch, head and dirty state, and each topic's
ahead/behind count, whether the base contains it, where it is checked out, its changed
file count, and any files two topics share.

`python3 tools/integrate.py rebuild [repo...]` recreates the integration branch and
writes the lock (`tools/integrate.py:319`, `:473`):

- It enables `rerere.enabled` and `rerere.autoupdate` in the fork.
- It fetches the base remote. A tag or local base is not fetched unless it is missing,
  then tags are fetched. `--no-fetch` skips this.
- It refuses a dirty integration worktree, then resets the branch to the base and
  merges the topics in manifest order.
- `--only-in-ota` skips repositories whose `in_ota` is not true.

`python3 tools/integrate.py check-lock` verifies that the lock's manifest sha256
matches `integration.json` and that each recorded worktree exists, is clean, and has
the recorded head (`:501`).

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
worktrees (`tools/lab-build.py:1148`). The steps are:

1. Read `tools/lab-build.json` and pick the version. The default is the highest
   existing lab version plus one patch; `--version X.Y.Z` overrides it.
2. Unless `--no-integrate` is set, run `integrate.py rebuild --only-in-ota` and then
   `check-lock`.
3. Read the lock and refuse a dirty or missing integration worktree.
4. Verify every pinned file and tree in `lab-build.json` against its sha256.
5. Build the kernel, the UI bundle, the 16 MiB boot images, the audio engine and
   the feature payloads.
6. Write the product's CI candidate catalog and run the product OTA pipeline from
   the LibreEcho integration worktree: `build/ci/plan-target-manifest.py
   --target lidar` emits the run directory (`feature-plan.json`,
   `feature-assets.json`, `target.manifest`, `ota-assets/` and the provenance
   record), then `build/ci/ota_v3_product.py` signs it with the lab key. The
   release tag has the product's dev form
   `radar-puffin-build-<sha7>-<source_id16>-<build_id16>`
   (`.github/workflows/build-release.yml:258-265`): `sha7` is the LibreEcho
   integration head, `source_id` hashes the product, Platform, Linux and UI
   lock heads, and `build_id` hashes `lab:<version>`. The signed tar is
   `libreecho-<tag>.ota.tar`, and the target's published asset names carry the
   `libreecho-lidar-` prefix. The lab version and the `dev` channel are kept.
7. Run the verification checks against the tar, the run directory and the built
   artifacts.

The kernel cache key is the Linux integration head plus the pinned toolchain tree
sha256, the defconfig and the DTB target (`:429`). A hit reuses
`private/artifacts/builds/cache/kernel/<head>/`. `--kernel-prebuilt DIR` uses
`DIR/{Image,config,libreecho-lidar.dtb}` instead. `--lock PATH` reads another lock and
implies `--no-integrate`.

What `lab-build.json` pins:

- `files`: toolchains and the aarch64 cross tree, the ARM32 components, busybox, adbd,
  boot control and update tools, Wi-Fi firmware and licence, the stock boot image, the
  lab OTA signing and public keys, the wake-word payload, `sendspind`, the feature
  catalog, the stock boot backup and the adb binary.
- `trees`: the aarch64 cross toolchain, hashed over its file tree.
- `directories`: input directories that must exist, such as the host libraries and the
  tinyalsa work tree.
- `values`: the empty-tree hash and the superseded OTA public key.

The output directory holds `build.log`, `provenance.json` (tool, config, manifest, lock,
source heads, kernel, UI, inputs, OTA and outputs, with the check list) and
`SHA256SUMS`. A failing check fails the build.

`python3 tools/lab-build.py deploy VERSION --host HOST --yes` installs a finished build
over Wi-Fi adb (`:1343`). It refuses without `--yes`, rechecks the deliverables against
`provenance.json`, pushes the signed tar and every `ota-assets/` file into
`/data/libreecho/update/asset-cache/<sha256>.part`, and runs
`libreecho-update-fetch assemble-generation` on the device. The device assembles
`/data/libreecho/generations/<txn>` from the signed manifest and those cached parts
without a network fetch, then `libreecho-update install` writes the inactive slot.
Deploy reboots into that slot and polls until it reports the expected generation as
installed, up to 20 minutes. It then reads the boot slot back and compares its hash.
`--host` defaults to `$LAB_DEVICE_HOST`.

The device assembly reads each cached part only when its size and sha256 match the
signed manifest (`libreecho-generation` `assemble`); a cache miss falls back to an
allowlisted HTTPS release base, which deploy seeds against so this cannot happen.
This offline path is reasoned from the Platform script and has not yet run on the
device.

Deploy writes the device and reboots it, so each run needs its own hardware approval.
Build never talks to the device.

## Recipes

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
4. Add the branch to the Phase 8 PR table in `PLAN.md`.

### Rebase onto a moved upstream

1. Tag the old head: `git tag archive/<branch>-<date> <branch>`.
2. Fetch the base remote and rebase the topic onto the new base.
3. If the base ref changed, update `base` in `integration.json`.
4. Resolve conflicts on the topic branch, never in the integration worktree, when the
   topic is what changed.
5. Run `integrate.py rebuild` and `check-lock`.

### Cut a lab OTA

1. Run `python3 tools/integrate.py rebuild --only-in-ota` and `check-lock`.
2. Run `python3 tools/lab-build.py build`. Note the version it prints.
3. Read `private/artifacts/builds/v<version>/build.log` and `provenance.json`; every
   check must pass.
4. Install only after separate hardware approval:
   `python3 tools/lab-build.py deploy <version> --host <device>:5555 --yes`.

The build is host evidence. A new integration kernel is untested on hardware until a
deploy confirms the slot.
