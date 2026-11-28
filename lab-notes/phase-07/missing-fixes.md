# Why the Thread service and the announce fix are absent from lab OTAs v0.2.43/v0.2.44

Read-only investigation, 2026-11-26. No branch was checked out, moved or committed; the only
worktrees created were detached ones under `/tmp` and both were removed.

Two different causes:

- **Thread**: the code is on the integration branches and in the built image tree, but
  `tools/lab-build.py` never passes the Thread inputs to the MT8167 builder, so every image
  manifest records `"thread": {"enabled": false}`. The commits are *not* the problem.
- **Announce fix**: the patch is genuinely missing from the UI topic branch. It was dropped by
  the 2026-11-25 branch rebuild (`branch: Reset to wip/general-fixes-rebuild`), which replayed
  the esphomed chunk-framing *test* but not the fix it guards.

---

## (a) Thread service

### a.1 Reachability of each named commit (Platform)

`private/forks/LibreEcho-Platform`:

```
$ git for-each-ref --contains=ca8c09f1841b2d02d307aa3cbfd65c238f0da830 --format='%(refname)'
(no output)

$ git reflog show feature/lidar-support --date=iso | grep -n ca8c09f18
ca8c09f18 feature/lidar-support@{2026-11-24 18:58:50 +1100}: commit: feat(lidar): package the Thread border router service
e347165b7 feature/lidar-support@{2026-11-24 18:58:52 +1100}: commit (amend): feat(lidar): package the Thread border router service
```

`ca8c09f18` is reachable from **no branch and no tag**. It is not a lost patch: it was amended
two seconds later into `e347165b7`, which is the first Thread commit of the 0.14.6-based
branch. Every later form descends from the amend, so nothing was lost there.

The other three:

| Commit | Refs containing it | Content on the current topic branch |
| --- | --- | --- |
| `3617d6650` | `refs/remotes/fork/feature/lidar-support-0.14.6` | `95b0052d8 feat(lidar): stage radio helpers and harden otbr build` |
| `02ef8ad6a` | `refs/remotes/fork/feature/lidar-support-0.14.6` | folded into `f3da78658` / `95b0052d8` |
| `40bf6f0b69` | `refs/tags/backup/2026-11-24/feature/lidar-support-0.14.6` only | `f3da78658 feat(lidar): ship the Thread border agent with D-Bus and Avahi` |

Drop trail (reflog):

```
40bf6f0b6 feature/lidar-support@{2026-11-24 20:24:49}: commit   (last commit of the 0.14.6 lane)
2ebe8111a feature/lidar-support@{2026-11-24 20:39:25}: branch: Reset to 2ebe8111a...   <-- restack onto origin/main
57b18ea59 feature/lidar-support@{2026-11-24 21:09:13}: commit
... 2026-11-25 08:53/09:12/09:20/09:26 ... 
b7a15578d feature/lidar-support@{2026-11-25 20:23:48}  (current manifest head)
```

So the reset at 2026-11-24 20:39:25 is the step that took the 0.14.6 commits off the branch.
Unlike the UI case, the restack **replayed the Thread work as new commits** on the new base:

```
$ git log --oneline origin/main..feature/lidar-support | grep -i 'thread\|radio helpers'
f3da78658 feat(lidar): ship the Thread border agent with D-Bus and Avahi
95b0052d8 feat(lidar): stage radio helpers and harden otbr build
c6aa20de9 feat(lidar): package the Thread border router service
```

`git cherry feature/lidar-support fork/feature/lidar-support-0.14.6` prints `+` for
`e347165b7`, `3617d6650`, `02ef8ad6a`, but `patch-id` matches are the wrong test here: the
rewrites carry different init pins and hunk context. The substance is present, checked by
content:

- `02ef8ad6a` (validate the radio helpers *before* writing them) is in
  `tools/mt8167-arm64/build_recovery_image.py:add_lidar_thread_runtime`: the `.gbl`/regular-file
  loop runs over both inputs, and only the second loop writes (`:694-704`).
- `40bf6f0b69`'s SOURCE.lock/`build_otbr_deps.sh`/`build_otbr.sh` changes are on the branch, and
  its private dbus/avahi daemons were deliberately replaced by the shared `libreecho-mdnsd`
  responder (`thread/libreecho-threadd:27-36,174-190`, manifest `discovery: shared-avahi-dbus`).
- The two built artifacts recorded in `thread-service.md` are still on disk and match its hashes:

```
$ sha256sum private/artifacts/phase-07/thread/otbr-build/src/agent/otbr-agent
95ebc60f2d14cc35e4288a974f9e53ba18c83e1ae9fce4da4f17e247b3403172  .../otbr-agent
```

Other repos, for completeness:

- UI `81aaae3` / `947841ea9`: only on `refs/remotes/fork/feature/lidar-support-0.14.6` and
  archive tags; the topic branch carries the same radio-setting change as `520f90c` (the
  2026-11-25 restack). `git cherry` reports `+ 81aaae3`, again for pins/context.
- Product `73508b6 feat(release): refuse images and bundles carrying EFR32 firmware`: only on
  archive tags; present on the topic as `c566639` (same subject, `git log --grep`).
- Linux `47feddd6 fix(lidar): run the EFR32 uart without hardware flow control`: only on
  `refs/remotes/fork/fix/lidar-port-identity` and archive tags; the property is present in
  `feature/lidar-support`: `arch/arm64/boot/dts/mediatek/libreecho-lidar.dts` has no
  `uart-has-rtscts` (only the comment at `:726-727`).

### a.2 The actual cause: lab-build never asks for Thread

Platform integration head `afab881c2` does contain the runtime (`git ls-tree -r HEAD` lists
`tools/mt8163-arm32/efr32/lidar-efr32.c`, `tools/mt8163-arm32/otbr/*`,
`tools/mt8167-arm64/thread/libreecho-threadd`). But:

```
$ grep -n 'build_recovery_image' tools/lab-build.py
656:        log.run([sys.executable, lidar / 'build_recovery_image.py', *build_common,
```

`build_common` and the two image specs in `build_images()` (`tools/lab-build.py:600-690`) pass
`--mdns-runtime`, `--wpa-supplicant`, `--tinyplay/--tinycap/--tinymix`, but **never
`--lidar-efr32` or `--otbr-agent`**. A grep of `tools/lab-build.py` for
`otbr|thread|efr32|avahi|dbus` returns no matches at all.

The builder stages the whole runtime only as a pair
(`tools/mt8167-arm64/build_recovery_image.py:794-799`, `:982`); `tools/mt8167-arm64/README.md:157-159`
documents the flags as the only way in ("one without the other is refused, and both are refused
outside `--target lidar`"). Its manifest default is
`'thread': {'enabled': False}` (`:951`). Result, in both shipped builds:

```
$ jq -r '.thread' private/artifacts/builds/v0.2.43/images/boot-lidar-v2.manifest.json
{ "enabled": false }
$ jq -r '.thread' private/artifacts/builds/v0.2.44/images/boot-lidar-v2.manifest.json
{ "enabled": false }
```

which matches the device read (`hw-2026-11-26/11-thread-announce-state.log`): no
`/usr/local/sbin/otbr-agent`, no `lidar-efr32`, no `/etc/init.d/libreecho-threadd.init`.

Two more gaps the fix must cover:

1. **No `lidar-efr32` binary has ever been built.** `glob private/artifacts/**/lidar-efr32`
   finds nothing; `private/artifacts/phase-07/thread/` holds `otbr-build/.../otbr-agent` and
   `.../ot-ctl` plus the armhf wrapper scripts, but not the radio tool.
2. **`otbr-agent` is not pinned** in `tools/lab-build.json` (it is not under `files`/`directories`).

### a.3 Fix plan (Platform / lab-build; `tools/` is ForkTools-owned)

1. **Build the two ARM32 static binaries** (reproducible, from the integration worktree source;
   the otbr build is the heavy one documented in `thread-service.md`):

```sh
cd private/artifacts/phase-07/thread
# radio tool, from the integration source
private/artifacts/phase-07/thread/build/bin/arm-linux-gnueabihf-gcc \
  -O2 -Wall -Wextra -Werror -static \
  -o lidar-efr32 \
  private/integration/LibreEcho-Platform/tools/mt8163-arm32/efr32/lidar-efr32.c
# border agent + deps (only if the existing artifact is not reused)
OTBR_DEPS_ARCHIVES=$PWD/sources \
ARM_CC=$PWD/build/bin/arm-linux-gnueabihf-gcc \
ARM_CXX=$PWD/build/bin/arm-linux-gnueabihf-g++ \
  sh private/integration/LibreEcho-Platform/tools/mt8163-arm32/otbr/build_otbr_deps.sh $PWD/deps
OT_BR_SRC=$PWD/otbr-src OTBR_DEPS=$PWD/deps \
ARM_CC=$PWD/build/bin/arm-linux-gnueabihf-gcc \
ARM_CXX=$PWD/build/bin/arm-linux-gnueabihf-g++ \
  sh private/integration/LibreEcho-Platform/tools/mt8163-arm32/otbr/build_otbr.sh $PWD/otbr-build
```

`arm-linux-gnueabihf-gcc -static` must produce `ELF 32-bit LSB executable, ARM, EABI5,
statically linked`; the builder enforces the ELF contract
(`shared.require_elf_contract(destination, 0x05000400, ...)`) so a dynamic binary fails the
image build, not the device.

2. **Pin them in `tools/lab-build.json` `files`** (same shape as `sendspind`):

```json
"otbr_agent": {"path": "private/artifacts/phase-07/thread/otbr-build/src/agent/otbr-agent",
               "sha256": "95ebc60f2d14cc35e4288a974f9e53ba18c83e1ae9fce4da4f17e247b3403172"},
"lidar_efr32": {"path": "private/artifacts/phase-07/thread/lidar-efr32",
                "sha256": "<sha256 of the built tool>"}
```

3. **Pass the pair in `tools/lab-build.py:build_images()`**, added to `build_common` (or to the
   `specs` extra list so only the OTA image carries it):

```python
'--lidar-efr32', inputs.path('lidar_efr32'),
'--otbr-agent', inputs.path('otbr_agent'),
```

Verification needs no extra flag: `verify_recovery_image.py:521` calls `validate_thread()` on
the manifest record, so a built image with `thread.enabled=true` is checked against
`start_order`, `discovery`, file hashes and the ELF contract automatically
(`verify_recovery_image.py:313-355`).

No commit or cherry-pick is required on any fork for Thread, only the harness change plus the
two pinned binaries.

---

## (b) Announce fix (UI `0cc5507`)

### b.1 All three spellings are the same patch

```
$ for c in 0cc5507 dc8a7d9 26a0168; do git show $c | git patch-id --stable; done
eaf78126b415924d194d5ac26e3f24092e9c22da 0cc5507cf1a62ff556e47eee698a6648ea8255fb
eaf78126b415924d194d5ac26e3f24092e9c22da dc8a7d99a64fcf55ae90ef9c96ffcd9f592f609e
eaf78126b415924d194d5ac26e3f24092e9c22da 26a01684cccff6d2bc5227c569ac835283e6eade
```

Reachability now:

```
$ git branch -a --contains 0cc5507           ->  remotes/fork/feature/lidar-support-0.14.6
$ git for-each-ref --contains=0cc5507        ->  .../lidar-support-0.14.6,
    refs/tags/archive/fork/feature/lidar-support-0.14.6-2026-11-25,
    refs/tags/archive/lidar-support-0.14.6-ui-2026-11-24,
    refs/tags/backup/2026-11-24/feature/lidar-support-0.14.6
$ git for-each-ref --contains=26a0168        ->  refs/tags/archive/fix/general-fixes-from-lidar-port-2026-11-25-review
$ git for-each-ref --contains=dc8a7d9        ->  archive/feature-lidar-support-2026-11-25,
    archive/feature/lidar-support-2026-11-25, archive/fix/general-fixes-from-lidar-port-2026-11-25,
    archive/trial-integration-2026-11-24
```

It is on **no branch of `integration.json`**: `git grep CHUNK_SIZE_EXT 520f90c` is empty, and

```
$ git merge-base --is-ancestor 0cc5507 e44b9ba   -> exit 1
```

(`e44b9ba` is the v0.2.44 UI integration head; `972bd742` is v0.2.43's, same topic head.)

### b.2 When and how it dropped

`git reflog show fix/general-fixes-from-lidar-port --date=iso` (UI fork):

```
dc8a7d9 fix/general-fixes-from-lidar-port@{2026-11-24 20:39:46}: cherry-pick: fix(esphomed): ignore chunk extensions in chunked replies
...
19e172c ...@{2026-11-25 08:50:11}: rebase (finish): ... onto 4b62b0aa4...   (fix still present: 37f9c83 tree has dc8a7d9)
a1e38fc ...@{2026-11-25 09:22:26}: branch: Reset to wip/general-fixes-rebuild
fa95d0f ...@{2026-11-25 20:23:48}   (current manifest head)
```

The rebuilt branch is where it goes missing:

```
$ git log --oneline a1e38fc | head
a1e38fc fix(api): bound voice pipeline restarts
d4dc6e6 test(esphomed): pin chunk framing across read boundaries
f3cd4a4 fix(micd): stop logging a phantom stream stop
...
```

The hand-picked rebuild kept the **test** (`d4dc6e6`, later `62052de`) that asserts chunk
framing across read boundaries, and dropped the **fix** that handles chunk extensions. The
subsequent 20:23 restack preserved that content, so `fa95d0f`/`520f90c` carry the test and not
the fix. The phase-08 reconcile docs did not catch it: `LibreEcho-UI-reconcile.md` compares only
`refs/remotes/fork/feature/lidar-support`, never the parallel `feature/lidar-support-0.14.6`
lane where the patch lived.

### b.3 Fix plan (UI)

Placement per `AGENTS.md`: esphomed chunk framing is a general fix, and the original drop was
from the general topic, so it goes on `fix/general-fixes-from-lidar-port` (the lidar topic is
stacked on it and inherits it).

1. Cherry-pick in the UI fork:

```sh
cd private/forks/LibreEcho-UI
git switch fix/general-fixes-from-lidar-port
git cherry-pick -x 0cc5507cf1a62ff556e47eee698a6648ea8255fb   # == dc8a7d9 == 26a0168
```

2. Expected conflict, verified in a detached `/tmp` worktree at `fa95d0f` (removed afterwards):

```
Auto-merging src/adapter/esphome_playback.c
Auto-merging tests/test_esphomed_http.c
CONFLICT (content): Merge conflict in tests/test_esphomed_http.c
```

Only the test file conflicts; `src/adapter/esphome_playback.c` and `.h` merge cleanly (the
`CHUNK_SIZE_EXT` stage and `chunk_ext` field apply unmodified). Resolve by keeping this side of
each conflict:

- the function block: take 0cc5507's `chunk_framing()` (it already contains the `split_cases`
  coverage from the dropped-in `split_boundaries()`), discard the HEAD-only `split_boundaries()`;
- `main()`: keep the incoming `chunk_framing();`, drop `split_boundaries();`;
- keep 0cc5507's `bad[]` entry removal (`"3;ext=1\r\n..."` is no longer an error case); it
  applies cleanly.

Then `git add tests/test_esphomed_http.c && git cherry-pick --continue`, and run the suite the
commit adds: `tests/run_tests.sh` (needs the staged mbedTLS prefix) or at least
`tests/test_esphomed_http.c`.

No conflict on the Platform side; nothing else to port.

---

## Rebuild and deploy

After (a) is wired and (b) is on the UI general branch:

```sh
# workspace root
python3 tools/integrate.py rebuild LibreEcho-UI LibreEcho-Platform
python3 tools/integrate.py check-lock
python3 tools/lab-build.py build            # next patch version, e.g. 0.2.45
python3 tools/lab-build.py deploy 0.2.45 --host <device> --yes   # device write: needs approval
```

Acceptance after deploy (read-only):

- `jq -r '.thread' private/artifacts/builds/v0.2.45/images/boot-lidar-v2.manifest.json` ->
  `"enabled": true` with three file records.
- On device: `ls /usr/local/sbin/{otbr-agent,lidar-efr32}` and
  `/etc/init.d/libreecho-threadd.init status` (radio still `none` until I select
  Thread, so status should report `radio choice is none`).
- `strings /usr/local/sbin/libreecho-esphomed | grep -i ext` will not show the enum; confirm the
  fix instead by `sha256` of the binary matching the new provenance and by sending an HA TTS
  announcement through the extension-emitting proxy from `announce-bug/notes.md`.

## Ownership note

`tools/lab-build.py` and `tools/lab-build.json` belong to **ForkTools**; this document only
specifies the change. The UI cherry-pick lands on a topic branch owned by the UI fork work.
