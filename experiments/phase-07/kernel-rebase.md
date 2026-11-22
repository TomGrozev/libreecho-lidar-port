# Kernel rebase onto the 6.18 LTS: work in progress

Status: **branches created, the Lidar series ported, the target tooling
generalized, the README and parity tooling made line-correct, the next-LTS
canary ported to this line, and the arm64 build plus every host-runnable CI
step passing** (`Image` and the Lidar DTB). Nothing was pushed; the main
checkout, all pre-existing branches and all tags are untouched.

## Bases

| Ref | Commit | Note |
| --- | --- | --- |
| upstream base | `fd7cfd39c88596fec816639ad83cbf3e9d316372` | kernel.org `v6.18.64` tag, already present locally |
| LibreEcho tooling source | `31596dc43218` | `origin/main`, 0.14.6 (6.1-based tooling tree) |
| Lidar kernel source | `8cb65710c72f` | `fix/lidar-port-identity`, `v6.18.64-35-g8cb65710` |
| `linux-6.18` | `fd7cfd39c885` | pristine base, no commits on top |
| `feature/6.18-lts-line` | `600d0257d7f3` | five tooling commits on `linux-6.18` |
| `feature/lidar-support-6.18` | `f07f26f4ab68` | 32 ported commits plus the target row, on `feature/6.18-lts-line` |

Worktrees: `/tmp/wt-line` (tooling) and `/tmp/wt-lidar618` (Lidar series).
Build tree: `/tmp/build-lidar` (`O=` out-of-tree, nothing written to the
worktrees). No fetch, push, gc or tag creation was run.

### Branch-name decision

`refs/heads/feature/lidar-support` already exists in this repository at
`6046668bd5ed` (the 6.1 production Lidar branch) and is checked out in the main
checkout. The hard rule forbids resetting an existing branch or changing the
main working tree, so the 6.18 branch is `feature/lidar-support-6.18`. Rename
it to `feature/lidar-support` only after the 6.1 branch is archived with owner
approval.

## `feature/6.18-lts-line`

Five commits, no kernel file touched:

1. `758ce622f3ed` (`libreecho: carry the repository tooling onto the 6.18 LTS
   line`) takes these paths from `31596dc` verbatim: `.github/` (SECURITY,
   renovate env, `checks.yml`, `next-lts-canary.yml`, `parity.yml`),
   `AGENTS.md`, `README.md`, `renovate.json`, `libreecho/`
   (`next_lts_canary.sh`, `parity.json`, `parity_check.sh`,
   `run_contract_tests.py`, `targets.json`, `test_next_lts_canary.py`,
   `test_targets.py`, `validate_targets.py`) and
   `firmware/i2s_to_spi_v34.bin`. 17 files, +1436 lines.
2. `c4e8fd6fc4d4` (`libreecho: generalize the target tooling for the 6.18
   line`): the target descriptor now carries `arch`, `defconfig`, `dtb` and
   `image` per row, the validator and tests are data-driven, and `checks.yml`
   gains the arm64 lane and arch/image paths.
3. `49abf05db1f2` (`libreecho: skip an empty build lane instead of failing
   CI`): an empty matrix include list is invalid on GitHub, so a lane expands
   a placeholder entry that its `if` guard skips, and publishing tolerates a
   skipped lane for the other arch.
4. `a36dab4a9374` (`libreecho: document the 6.18 line and drop 6.1 parity
   tooling`): `README.md` is rewritten for this line (branches, target table,
   CI lanes, arm64 build recipe, contract tests, 6.18.y update flow), and
   `parity.yml`, `parity.json` and `parity_check.sh` are removed because a
   byte-identical comparison against pinned LibreEcho-Linux-6.1 sources can
   only hold on a 6.1 tree. The 6.1 line keeps those three files.
5. `600d0257d7f3` (`libreecho: port the next-LTS canary to the 6.18 line`): the
   branch point defaults to `v6.18.64`, the build plans every target of the
   replayed tree from `targets.json` and skips cleanly for an empty table,
   and `CANARY_TARGET_TAG` allows an offline run against a local tag. The
   workflow installs the arm64 toolchain and the tests use 6.18 fixtures.
   `README.md` now documents the canary and keeps only the hardware-boot gap.

### Target table on this line

The owner decision keeps MT8163 on the 6.1 line, so the 6.18 line has no arm32
target sources and `libreecho/targets.json` is `{}`. The generalized validator
accepts an empty table (`Validated 0 targets; 0 unique build(s)`, exit 0); the
Lidar branch adds its single row. Two consequences are deliberate:

- `libreecho/validate_targets.py` no longer requires the exact 6.1 target set.
  It validates each present row (id shape, `arch` in `arm`/`arm64`, defconfig
  name, in-tree `.dtb` path, image matching the arch), orders rows by
  `ORDER = radar_puffin, biscuit, lidar` so the build owner never depends on
  JSON key order, and plans one build per distinct tuple.
- `libreecho/test_targets.py` keeps the synthetic arm32 parity, arm64 and
  divergent-tuple cases, adds the empty-table case, and checks the committed
  table itself only for schema validity so the same file passes on both
  branches.

`libreecho/run_contract_tests.py` now skips a listed test that is absent on
this line (the 6.1 contract tests) and does not treat upstream kernel tests
under `tools/` as LibreEcho-owned. `AGENTS.md:3-9` describes the arm64-only
line, the target table and the validator instead of the 6.1 connectivity
subtree.

### CI behaviour on this line

`checks.yml` keeps `docs_gate`, validates the table, and then:

- `arm32_kernel` is skipped on this line and on the Lidar branch (empty lane).
- `arm64_kernel` is skipped on this line, and builds `Image` plus the DTB on
  the Lidar branch with `CONFIG_COMPAT=y` asserted.
- `target_artifacts` runs only for a non-empty publish lane and is no longer
  suppressed when the other arch's build job was skipped.

### README and parity tooling

`README.md` now describes this line only: base and branches, the target table
and its validator, the `checks.yml` lanes and artifact names, the arm64 build
recipe with `CONFIG_COMPAT`, the contract-test runner, the merge flow for a
new 6.18.y, and the nightly canary. It states that parity tooling stays on the
6.1 line and that only a hardware boot remains as a gap.

Parity cannot be made correct for 6.18 by changing pins: the three files build
the tree and `aslater3/LibreEcho-Linux-6.1` at `ea26b8a` and require
byte-identical `zImage`, DTB, `System.map` and `.config` outputs. A 6.18
kernel can never match that. Deleting them is the clean cutover, so
`checks.yml` is the only build workflow besides the nightly canary, and no
workflow references parity any more.

### Nightly next-LTS canary

`next_lts_canary.sh` now belongs to this line: `BRANCH_POINT` defaults to
`v6.18.64`, the series is every non-merge commit after that tag and after the
currently merged stable tag, and the build step reads the replayed tree's own
`libreecho/targets.json` through its validator. It builds one tuple per
distinct target with the arch's cross prefix, checks that the image and DTB
exist, and reports `Build: skipped` when the table is empty, so the
tooling-only line passes instead of failing on a 6.1 defconfig.
`CANARY_TARGET_TAG` replays onto a local tag for offline runs;
`next-lts-canary.yml` installs the arm64 toolchain and the canary's unit tests
now use `v6.18.64` and `v6.18.65` fixtures.

## `feature/lidar-support-6.18` commit table

Method: `git rev-list --no-merges --reverse v6.18.64..8cb65710`, minus the one
duplicate, applied with `git cherry-pick` (authors preserved). Every pick
applied without conflict, and the branch was then rebased three times onto the
growing 6.18-lts-line without conflict. `git patch-id --stable` over the source
range (32 unique ids after deduplicating `c3babd92785b`) and over the ported
range gives identical 32-member sets, so every ported commit is byte-identical
in patch content to its source (the only difference is the dropped duplicate
and the two merge commits).

Classification: LIDAR = board driver/DTS/config; GENERIC = kernel fix that is
not board-specific; no DEBUG commit exists in the source range.

| New hash | Subject | Class | Source |
| --- | --- | --- | --- |
| `b24f7eb16fd6` | feat(lidar): import MT7668 gen4 SDIO WLAN driver | LIDAR | `fd4465fddf21` |
| `9d89ceccea8a` | feat(lidar): add MT8516 audio front end platform driver | LIDAR | `810659733f1e` |
| `c2dae8b7b4c8` | feat(lidar): add Amazon Lidar sound card | LIDAR | `6253cf33107e` |
| `d25de6c5f0a4` | feat(lidar): add biquad and mono mix controls to tlv320aic32x4 | LIDAR | `351020d8e28b` |
| `5ec4d159f2df` | feat(lidar): support TDM and BCLK-only clocking on tlv320adc3xxx | LIDAR | `b0bd662b88c2` |
| `e861d20c51ca` | feat(lidar): add audio devicetree for the Lidar board | LIDAR | `67d308b82963` |
| `5cfdb29cbdcd` | docs(lidar): describe BCLK-only clocking for tlv320adc3xxx | LIDAR | `12ea437df304` |
| `63ad358052c6` | fix(lidar): port mt7668 to the v6.18 cfg80211 API | LIDAR | `0c17cb8f1f72` |
| `0e6d2007ad7d` | fix(lidar): avoid duplicate is_world_regdom symbol | LIDAR | `275ab69ce648` |
| `5dac8c9703d8` | feat(lidar): port MT8516 reset and MSDC2 support to 6.18 | LIDAR | `cc3a80e7124c` |
| `fbc4eb263063` | feat(lidar): carry privacy and light-sensor drivers to 6.18 | LIDAR | `384b3095ae0c` |
| `f781eedde3c4` | feat(lidar): restore LibreEcho frame ABI on is31fl32xx | GENERIC | `8f7321878c27` |
| `8c1f4cf7cdf2` | feat(lidar): carry MUSB receive fix and isoc PIO quirk | GENERIC | `3f0c178d3a93` |
| `08a241614e6d` | feat(lidar): carry MT7668 Bluetooth firmware fixes | GENERIC | `683af3909fde` |
| `2bf59582b12f` | feat(lidar): add MT8516 AFE node | LIDAR | `afae82a6d9d1` |
| `5722b8c24e8e` | feat(lidar): support the RT5738 Vproc buck | LIDAR | `9861cdf549e1` |
| `3e457032132e` | feat(lidar): read privacy state from a GPIO on Lidar | LIDAR | `a9a04ce81806` |
| `a86df159bd01` | feat(lidar): add the Lidar board DTS and defconfig | LIDAR | `16bfee37a733` |
| `98ce15f3ce60` | proc: handle a NULL mm in map_files lookup and readdir | GENERIC | `21df2d810525` |
| `45f278e5cc99` | feat(lidar): build the audio and MT7668 Wi-Fi drivers in | LIDAR | `a8e6b233ac9e` |
| `d61ce251f7ff` | fix(lidar): stop 8250_mtk entering 16650 sleep on power-down | GENERIC | `9fc4128dab60` |
| `bf07f205848f` | fix(lidar): let the MSDC hosts bind on 6.18 | LIDAR | `a8e7d8264ce7` |
| `32b4a5cbff0a` | fix(lidar): complete the MUSB rx_kick port on 6.18 | GENERIC | `15e16539a61d` |
| `32f89a1b0ca8` | fix(lidar): cache the AIC32x4 page selector so page-0 writes stick | LIDAR | `d70e787ff949` |
| `fbd886a2b8fa` | fix(lidar): number mtk 8250 ports from the serial aliases | GENERIC | `89b7f3f07a51` |
| `5c16a5189ef1` | fix(lidar): name the privacy node amz_privacy | LIDAR | `3f2711ac4690` |
| `54910bc96321` | fix(lidar): enable mediatek-cpufreq so the OPP table reaches 1.3 GHz | LIDAR | `77931cc96944` |
| `bd49b774c9e8` | fix(mt8167): keep the MFG power domains off by default | LIDAR | `c2b2e5ec9ed6` |
| `f76ddcfe50bb` | feat(lidar): bind the TSL2540, the tmp112 and a board thermal zone | LIDAR | `8985a44d45a8` |
| `0b55e655a1f0` | fix(tsl2540): undo every probe registration in remove() | LIDAR | `074992b7f473` |
| `60771ade2876` | fix(lidar): power the ambient light sensor on at probe | LIDAR | `b8eaba14e3f1` |
| `2cbf96db64d1` | feat(lidar): give the board thermal zone stock trip points | LIDAR | `8cb65710c72f` |
| `f07f26f4ab68` | libreecho: register the Lidar target in the target table | tooling | new |

The GENERIC rows are still carried on this branch: the 6.1 tree does not use
these drivers, and Phase 8 scopes them to `feature/lidar-support`.

### Lidar target row

`f07f26f4ab68` sets `libreecho/targets.json` to one row:
`lidar`, `arm64`, `mt8167_arm64_defconfig`, `mediatek/libreecho-lidar.dtb`,
`Image`. The validator then reports `Validated 1 targets; 1 unique build(s)`
and emits one arm64 build lane plus one publish lane.

## Dropped items

- `a0ba8dfafcd5` and `2e0a62088c79` (merge commits): the branch graph is
  linearized; both merge resolutions are already in the final trees of the
  commits below and above them.
- `c3babd92785b` `feat(lidar): add audio devicetree for the Lidar board`: its
  patch is identical to `67d308b82963` (`git diff` of the two patches is
  empty, both add `arch/arm64/boot/dts/mediatek/libreecho-lidar-audio.dtsi`
  with 127 identical lines). Keeping both would create the file twice.
- No debug-only commit exists in `v6.18.64..8cb65710`; grep over messages for
  debug/hack/WIP/temp returns nothing, so nothing was dropped for that reason.

## Conflict resolutions

None. All 32 picks applied cleanly because the tooling commits only add or
change the tooling paths and no Lidar commit touches them; all three later
rebases replayed without conflict for the same reason.

The diffs that do need explaining:

- `arch/arm64/boot/dts/mediatek/libreecho-lidar-audio.dtsi:1-127`: added by
  `64f857cef753`, not by the dropped duplicate `c3babd92785b`; the final bytes
  are those of `8cb65710:.../libreecho-lidar-audio.dtsi`.
- `libreecho/targets.json`, `libreecho/validate_targets.py`,
  `libreecho/test_targets.py`, `libreecho/run_contract_tests.py`,
  `.github/workflows/checks.yml` and `AGENTS.md:3-9`: the tooling adaptation
  described above. They differ from both `8cb65710` (which has no generalized
  descriptor at all) and the 6.1 target set by design.

## Diff check against `fix/lidar-port-identity`

- `git diff --name-status v6.18.64 fix/lidar-port-identity` versus
  `git diff --name-status v6.18.64 feature/lidar-support-6.18`: the target
  branch has exactly the same 228 kernel entries plus the 14 tooling files it
  carries (242 changed files in total; the three parity files are absent on
  both sides).
- `git diff --stat 8cb65710 feature/lidar-support-6.18` is exactly those 14
  tooling files, 1444 insertions and no deletions: no Lidar file, DTS, driver,
  binding or defconfig differs. MT7668 (about 216k lines), MT8516 AFE,
  AIC32x4/ADC3xxx, IIO libreecho, amz_privacy, rt5739, is31fl32xx, MUSB,
  btmtksdio, 8250_mtk, mt8167 pmdomain, `fs/proc/base.c`,
  `libreecho-lidar.dts` and `mt8167_arm64_defconfig` all match byte for byte.
- `git patch-id --stable`: source set (32 unique patch ids after deduplicating
  `c3babd92785b`) equals ported set (32), checked at the final heads.

## Build

Environment: host `aarch64-linux-gnu-gcc` 16.2.0, GNU make, 12 jobs, `dtc`
built in-tree from `scripts/dtc` (no system `dtc`).

```
make -C /tmp/wt-lidar618 O=/tmp/build-lidar ARCH=arm64 \
     CROSS_COMPILE=aarch64-linux-gnu- mt8167_arm64_defconfig   # pass
make ... olddefconfig                                          # pass, no change
make ... -j12 Image dtbs                                       # pass
```

All three commands exited 0, and `Image dtbs` was re-run after each rebase and
after the final tooling commit, so the final head `f07f26f4ab68` is the one
built. `Image` is 13,410,816 bytes
(14:35, `sha256 c1386f48d5649d4e0acdf4291bdac61d06b19ea2a2771aaebabb775682a8ba98`);
the value moves between runs because the UTS version embeds the build timestamp,
not because the tree changed. `vmlinux`, `vmlinux.unstripped`, `System.map` and
`modules.builtin` were produced in the same pass, with no compiler error or
warning-as-error stop.

- `mt8167_arm64_defconfig` configures without warnings; `olddefconfig` reports
  no change.
- `arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb` built (24,032 bytes,
  `sha256 a8e1957314334d9a03aa6c96082a6d82a1202ee02729cdc2097d8355d6bd5bc7`)
  as part of the same `dtbs` pass. One DTC warning came from upstream
  `arch/arm64/boot/dts/mediatek/mt8516.dtsi:494-517` (`resets` property needs
  `#reset-cells` in `infracfg`); it is not introduced by this branch and does
  not fail `dtbs`.
- `.config` fingerprint: `sha256 c866c90c8b4024af9d362765a2e386b55d45cd0e4402ed1114e6e43cd1b51f29`,
  unchanged across the tooling work.
- Key configs resolved `=y`: `CONFIG_COMPAT`, `CONFIG_MT7668_SDIO`,
  `CONFIG_SND_SOC_MT8516`, `CONFIG_SND_SOC_MT8516_AMAZON_LIDAR`,
  `CONFIG_SND_SOC_TLV320AIC32X4`, `CONFIG_SND_SOC_TLV320ADC3XXX`,
  `CONFIG_LEDS_IS31FL32XX`, `CONFIG_AMZ_PRIVACY`, `CONFIG_SENSORS_TSL2540`,
  `CONFIG_REGULATOR_RT5739`.
- Not run: booting the `Image` on hardware (out of scope; no device access).
  The build is a host/cross-compile result only, not a support claim.

## Checks run on both heads

Host-runnable parts of `.github/workflows/checks.yml`, run in the worktrees at
the final heads:

| Step | `feature/6.18-lts-line` | `feature/lidar-support-6.18` |
| --- | --- | --- |
| `libreecho/test_targets.py` | 13 tests OK | 13 tests OK |
| `libreecho/validate_targets.py` | exit 0, 0 targets | exit 0, 1 target, 1 arm64 lane |
| `libreecho/run_contract_tests.py` | exit 0, 2 passed, 22 skipped | same |
| `git diff --check` | clean | clean |
| `docs_gate` detect step | exit 0, `run_build=true` (fail-closed, no remote fetch in the worktree) | same |
| YAML parse of the remaining workflows | `checks.yml` and `next-lts-canary.yml` ok | same |
| `libreecho/test_next_lts_canary.py` | 3 tests OK | 3 tests OK |
| `next_lts_canary.sh` offline replay (`CANARY_TARGET_TAG=v6.18.64`) | 5/5 commits apply, build skipped, exit 0 | 38/38 commits apply, arm64 `lidar` build ok, exit 0 |
| parity files | absent (removed) | absent |
| arm64 build step | lane skipped (no target) | `Image` + DTB built, `CONFIG_COMPAT=y` |

Skipped or not host-runnable:

- The arm32 build: no `arm-linux-gnueabihf-` toolchain is installed, and this
  line has no arm32 target anyway.
- `docs_gate`'s documentation-only branch and the push/PR base fetch: both
  worktrees have no fetchable remote base offline, so the step took its
  fail-closed `run_build=true` path.
- `actions/checkout`, the artifact upload/download steps, and any GitHub
  expression evaluation: GitHub-side only, not executed here (`actionlint` is
  not installed).
- The 22 contract-test skips are the 6.1-line tests listed in
  `run_contract_tests.py` whose paths do not exist on this line.

## Archive tags (created 2026-11-22, owner approved; local only, not pushed)

| Tag | Branch | Tip |
| --- | --- | --- |
| `archive/lidar-support-6.1` | `feature/lidar-support` | `6046668bd5ed` |
| `archive/lidar-port-identity-6.18` | `fix/lidar-port-identity` | `8cb65710c72f` |
| `archive/lidar-6.18` | `feature/lidar-6.18` | `89b7f3f07a51` |
| `archive/lidar-6.18-audio` | `feature/lidar-6.18-audio` | `12ea437df304` |
| `archive/lidar-6.18-mt7668` | `feature/lidar-6.18-mt7668` | `275ab69ce648` |
| `archive/lidar-6.18-boot` | `fix/lidar-6.18-boot` | `15e16539a61d` |
| `archive/lidar-6.18-volume` | `fix/lidar-6.18-volume` | `d70e787ff949` |
| `archive/experiment-lidar-console-wdt` | `experiment/lidar-console-wdt` | `79801bc0efe1` |
| `archive/experiment-lidar-lk-slot-source` | `experiment/lidar-lk-slot-source` | `79d8d10e16b6` |
| `archive/experiment-lidar-musb-rx-kick` | `experiment/lidar-musb-rx-kick` | `7594c5780db2` |
| `archive/experiment-lidar-usb-upstream-glue` | `experiment/lidar-usb-upstream-glue` | `a251a739ff78` |
| `archive/experiment-lidar-wdt-fetch-diag` | `experiment/lidar-wdt-fetch-diag` | `a251a739ff78` |

All tags above are annotated and point at the listed tips. The source branches
are kept.

## Next steps

- Push the two branches and run the GitHub workflow on the Lidar branch (needs
  a push, which is out of scope for this session).
- Boot the built `Image` on Lidar hardware (needs device access).
- Done 2026-11-22 (owner approved): the 6.1 branch `feature/lidar-support` was
  renamed `feature/lidar-support-6.1` (still checked out in the main checkout,
  working tree unchanged), and `feature/lidar-support-6.18` was renamed
  `feature/lidar-support` (head `f07f26f4ab68`). Neither has an upstream set,
  and no remote branch of that name exists. Nothing pushed.

## Stacking on the maintainer's `feature/linux-6.18` (2026-11-22, in progress)

Owner decision: the PR base is `aslater3:feature/linux-6.18`, not our own
6.18 line. Work happens on a new branch `feature/lidar-support-on-upstream`
in worktree `/tmp/wt-k-up`, created from a fresh fetch of
`origin/feature/linux-6.18` (`16989cef41b7`, 102 commits on `v6.18.57`). No
existing branch, tag, worktree or main checkout was changed; nothing pushed.

### Base difference that matters

His branch is **`v6.18.57` + `2926d88bb7fc` (Linux 6.18.58) + 101 LibreEcho
commits**, not `v6.18.64`. Anything the Lidar series takes from stable
`v6.18.59..v6.18.64` must be backported separately. That audit is done; the
result and the two backports are recorded below.

His tree already carries the 6.1 drivers ported onto 6.18, including
`amz_privacy.c`, `drivers/iio/light/libreecho/*`, the Radar-Puffin
`tlv320aic32x4` extension (`330a4effc455`, 1081 lines) and the Radar-Puffin
clock/PLL special case. That is why the Lidar series cannot be applied
byte-identically.

### Applied (32 of 32)

First eleven picks landed on `33eae80e8a84`; the complete series is on
`001e6e7ecd`. Authors preserved, applied in source order with
`git cherry-pick -x`:

| New hash | Subject | Resolution |
| --- | --- | --- |
| `9a98045c52f3` | feat(lidar): import MT7668 gen4 SDIO WLAN driver | clean |
| `ef5bf1573fbc` | feat(lidar): add MT8516 audio front end platform driver | clean |
| `7a9efa9ac91f` | feat(lidar): add Amazon Lidar sound card | clean |
| `a8c3623a9851` | feat(lidar): add biquad and mono mix controls to tlv320aic32x4 | **conflict, merged** |
| `2760cbeb9e3d` | feat(lidar): support TDM and BCLK-only clocking on tlv320adc3xxx | clean |
| `5de16b28cf78` | feat(lidar): add audio devicetree for the Lidar board | clean |
| `3395c944875f` | docs(lidar): describe BCLK-only clocking for tlv320adc3xxx | clean |
| `1d4d2689653f` | fix(lidar): port mt7668 to the v6.18 cfg80211 API | clean |
| `b6e59d439300` | fix(lidar): avoid duplicate is_world_regdom symbol | clean |
| `de36e36bc1a5` | feat(lidar): port MT8516 reset and MSDC2 support to 6.18 | clean |
| `33eae80e8a84` | feat(lidar): carry privacy and light-sensor drivers to 6.18 | **conflict, took lidar sides** |

`5ec4d159` and `e861d20` were each applied once and then re-offered by a
stale pick list; the second attempt was empty (`git cherry-pick --skip`), so
the branch holds exactly one copy of each.

### `tlv320aic32x4` merge (the one semantic conflict)

His `330a4effc455` and the Lidar commit both extend the same file from the
same `v6.18.64` blob, so 13 hunks conflicted. Resolution keeps both features:

- struct: his `component`, `defer_playback_unmute`, `playback_mono`,
  `playback_active`, `diag_lock` plus the Lidar biquad/`dac_mix`/
  `dac_channels`/`clks[]` members;
- his diagnostic macros and `aic32x4_log_playback_state()` are kept after the
  Lidar biquad helpers;
- his Radar-Puffin clock helper now indexes the shared `aic32x4->clks[]` by
  name (`AIC32X4_CLK_PLL`, `_NADC`, `_MADC`, `_NDAC`, `_MDAC`, `_BDIV`) and
  keeps its `clk_set_rate()` error checks;
- `set_bias_level()` uses the shared clock slice (`NUM_BIAS_CLKS`) and his
  `bias-enter`/`bias-exit` logging; the `devm_clk_bulk_get()` re-fetch is gone;
- probe combines his `aic32x4->component` assignment with
  `aic32x4_get_clocks()`, his HPL/HPR bootstrap route writes and the Lidar
  biquad/channel initialisation;
- DAC widgets keep his single `"Playback"` stream name and gain the Lidar
  `_E` pre-PMU biquad replay handler;
- regmap `max_register` keeps his `AIC32X4_MAX_DSP_REG` (page 46), which
  covers the Lidar biquad pages 44/45; the Lidar `AIC32X4_MAX_REG` duplicate
  was dropped from the header;
- **mono routing**: `aic32x4_dac_chan()` keeps his MonoRight mapping
  (`RDAC2RCHN | LDAC2RCHN`) as the default, so MT8163 and Radar-Puffin are
  unchanged. `001e6e7ecd` adds a parsed `libreecho,mono-left` property that
  the Lidar codec node sets; on Lidar mono playback therefore follows the
  `db8242a` left-slot convention (`RDAC2LCHN | LDAC2LCHN`). The gate is DT
  data, not a board-name test in the codec.

### Driver-file conflict (`fbc4eb2`)

His tree already has the same 6.1 drivers. The diff of that commit against
his tree touches only additive lines (includes, non-static helper exports,
Makefile entries), so the Lidar side was taken and the result is his file
plus those additions.

### Picks 12-32 (applied)

Branch head `001e6e7ecd`; all 32 source commits are now on the branch (the
last three are `6b5c4b071f9c` thermal trips, preceded by the pick commits
below). Applied in source order with `-x`; new hashes in order:

`9c1e1539dfef` (is31fl32xx frame ABI), `77be391420f3` (MUSB receive fix and
isoc PIO quirk), `bdcd9cc3ff19` (MT7668 Bluetooth fixes), `a129349ae6e6`
(MT8516 AFE node), `18eea3fb94e5` (RT5738 Vproc buck), `e386db2c42db`
(privacy state from GPIO), `9e101f6634ee` (Lidar board DTS and defconfig),
`cc25504088a2` (proc NULL mm), `104621864a29` (build audio and MT7668 in),
`f56ffa219576` (8250 16650 sleep), `4153e4ff9aa0` (MSDC hosts bind),
`038facc5fda1` (MUSB rx_kick port completion), `1bcf3b5bacb4` (AIC32x4 page
selector), `c1ee59a77e5d` (mtk 8250 port numbering), `198f8385c42b`
(`amz_privacy` name), `9ee669b29acf` (mediatek-cpufreq OPP), `f1ea2386b604`
(MT8167 MFG domains), `1175bcf4002d` (TSL2540/tmp112/thermal zone),
`c9ecaf54b752` (tsl2540 remove), `f4d3103f4f30` (ALS probe power),
`6b5c4b071f9c` (thermal trips).

Conflicts and their resolutions:

- `9c1e1539dfef` `drivers/leds/leds-is31fl32xx.c`: his tree already has the
  frame ABI plus an explicit all-off frame staged in `is31fl32xx_init_regs()`.
  Took the Lidar side (frame ABI, 22 kHz re-staged after reset,
  `is31fl3236_family()` covering the 3236A) and re-inserted his all-off
  staging before the 22 kHz write, so both behaviours hold.
- `77be391420f3` `drivers/usb/musb/musb_gadget.c`: kept his MT8163 restart
  diagnostic print and its `epio`, and used the Lidar `musb_g_rx_kick()`
  instead of `rxstate()` on the OUT path.
- `038facc5fda1` `drivers/usb/musb/musb_gadget.c`: the completion rewrites
  rx_kick as a work item with runtime-PM accounting. Took its `u16 csr` and
  OUT branch (`pm_runtime_get_noresume` + `queue_work(&ep->rx_kick)`), kept
  his diagnostic print, and restored the `{` after `if (req->tx)`.
- `001e6e7ecd` (new) `sound/soc/codecs/tlv320aic32x4.c` +
  `libreecho-lidar-audio.dtsi`: the Lidar-side mono gate described above.

### Build fix, dtb delta and stable backports

The conflict resolution had left three merge leftovers in
`sound/soc/codecs/tlv320aic32x4.c`: two stale `clk_set_parent(clocks[...])`
calls in `aic32x4_component_probe()` (his probe body, already covered by
`aic32x4_get_clocks()`), and a duplicate `aic32x4_component_remove()`. The
first definition already released the shared clocks, so the second was folded
into it (`clk_bulk_put()`, then `aic32x4->component = NULL`). The fix was
committed as `fixup! feat(lidar): add biquad and mono mix controls to
tlv320aic32x4` and squashed into that pick with
`git rebase -i --autosquash` (`GIT_SEQUENCE_EDITOR=true`), so the commit that
introduced the conflict now also carries its fix.

The same autosquash was used for a contract test that the privacy-state pick
left stale: `tools/mt8163_mute_lamp_contract_test.py` still expected the
pre-Lidar `mute_lamp_show()` gate, while the GPIO-input gate is
`if (priv->hw_latch || priv->state_input)`. That test change is squashed into
`feat(lidar): read privacy state from a GPIO on Lidar`.

Head trail: `001e6e7ecd82` (start) -> `1a6de42b4373` (biquad fixup squashed)
-> `72f51314b1fb` (backports added) -> `23f3c3340969` (contract fixup
squashed, target/CI commit on top). Because the second squashed commit sits
early in the series, every later hash in the tables above was rewritten; the
current branch has 36 commits over his head and the final head is
`23f3c3340969`.

arm64 build: `make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu-
O=/tmp/build-k-up -j$(nproc) Image dtbs` exits 0. The only warnings in files
the branch touches are in the imported MT7668 vendor driver: 272
`-Wmissing-prototypes`, 78 `-Wempty-body`, 4 `-Wimplicit-fallthrough=`, and one
each of `-Wmisleading-indentation`, `-Wenum-conversion`, `-Waddress`,
`-Wunused-function`, `-Wunused-but-set-parameter=`, `-Wrestrict` and
`-Wcast-function-type`. No non-vendor file warns. `.config` keeps
`CONFIG_COMPAT=y`. One warning exists in his diagnostic
`drivers/usb/gadget/function/f_fs.c` (`%d` versus `ssize_t`), a file the
branch does not modify.

dtb delta against `/tmp/build-lidar`: decompiling both with the tree's
`scripts/dtc/dtc` gives exactly one added property,
`libreecho,mono-left;` in the `aic32x4` codec node, from the mono gate commit.
That is why the image hashes differ (`a8e195731433...` old and
`00cb1a6e2249...` new); the property shifts the structure block and strings
table, so the whole file is re-serialised.

Stable audit (range `2926d88bb7fc..v6.18.64`, 2872 commits). No commit in the
range touches any of the 222 files the 33 Lidar commits modify. Dependency
paths were searched separately. Two fixes were picked with `git cherry-pick
-x` at the tip:

- `f78cf428744d` `wifi: cfg80211: fix out-of-bounds read in valid_rule()`
  (`4a81139583c2`): cfg80211 is built for the MT7668 driver and parses the
  regulatory database; the fix bounds the whole rule.
- `09db0effc310` `ASoC: tlv320aic32x4: Prevent division by zero in divider
  callbacks` (`0a71f66c8f3e`): the Lidar codec's `clk_set_rate()` path goes
  through `tlv320aic32x4-clk.c`.

Considered and rejected as not needed for this board: the musb host
three-strikes fix (`148fcb7faf16`, AM335x/DSPS host path, Lidar uses the
peripheral role), the 76-file `sockaddr_unsized` revert (`9d275d40b6ec`, an
API cleanup with no Lidar user), the Bluetooth L2CAP/hci_sync fixes (core
stack behaviour not exercised by this series), and the iio:light, mmc,
mediatek clk and thermal fixes, which name other drivers.

Target table and CI: `libreecho/targets.json` now has `arch` and `image` next
to `defconfig` and `dtb`, and a `lidar` row (`arm64`,
`mt8167_arm64_defconfig`, `mediatek/libreecho-lidar.dtb`, `Image`). The
validator resolves sources under `arch/<arch>/`, requires the image name the
arch defines, and deduplicates lanes by the full tuple. `checks.yml` builds
every tuple from the matrix, installs the matching cross toolchain, asserts
`CONFIG_COMPAT=y` on arm64 and the existing CFG80211/MUSB symbols on arm32,
and names artifacts with the arch. Host checks pass: `test_targets.py` 11/11,
`test_next_lts_canary.py` 3/3, `run_contract_tests.py` 22/22.

Not built: MT8163 arm32. `arm-linux-gnueabihf-gcc` is not installed on this
host, so the arm32 lane runs only in CI. The arm64 image, dtbs, the
`CONFIG_COMPAT` grep and the dtb comparison were run locally.
