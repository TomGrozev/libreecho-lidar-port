# Phase 7: target contract generalization and Lidar registration

Fork: `private/forks/LibreEcho`, branch `feature/lidar-support`, not pushed.
Base: `bc167529` (upstream main). `main` was not moved.

Commits:

- `eefd59899614a8a99a1f98b633aaa1fc3b1a4b0d`: feat(release): generalize target contracts beyond MT8163
- `257404952e47bbea2bd73dd9295c8516d4515762`: feat(release): register the Lidar target

## Commit 1: generalization (no Lidar data)

- `release/target.schema.json`: global `soc`, `arch`, `layout_profiles`,
  `kernel` and `platform` consts become enums; Radar and Biscuit pin their old
  values in per-target `allOf` blocks. Schema id stays `libreecho-target-v1`;
  no new required fields.
- `build/ci/target_registry.py`: canonical identity map drives descriptor
  validation; `accepted_targets()`; explicit `INSTALLER_TARGETS`.
- `build/ci/validate-targets.py`: emits `KERNEL_ARCH`.
- `build/ci/ota_v2_product.py`, `ota_v3_product.py`,
  `plan-target-manifest.py`, `prepare-dev-release.py`,
  `prepare-stable-release.py`, `release_completeness.py`: SoC and canonical
  Platform parser path come from the descriptor; OTA/manifest `architecture`
  stays the userspace `armv7` value for every target.
- `build/ci/prepare-stable-release.py`: fails before any output when the
  target is not hardware-accepted.
- `build/ci/release_route.py`: stable/prd routes require every requested target
  to be accepted.
- `build/ci/prepare-twrp-installs.py`, `sign_ota_candidate.py`: per-target
  slug and parser path.
- `build/build.sh`: kernel arch, defconfig path, image name, boot subdir,
  cross prefix and DTB from the descriptor; fail-closed arm64 guard naming the
  missing hosted aarch64 cross, with a `ponytail:` upgrade path
  (`build/build.sh:404-416`).
- `.github/workflows/build-release.yml`: kernel cache key derives arch and
  defconfig through `validate-targets.py --shell` and includes
  `inputs.targets` instead of the `radar_puffin-biscuit` literal.
- `build/tests/test_multi_target.py`: `PARITY_TARGETS` scopes shared-field,
  release, publisher, TWRP and signing assertions; installer sync test uses
  `INSTALLER_TARGETS`.

## Commit 2: Lidar data

- `release/targets/lidar.json`: target `lidar`, SoC `mt8167`, kernel arch
  `arm64`, userspace `armv7`, `mt8167_arm64_defconfig`,
  `libreecho-lidar.dtb`, `LIDAR`, `tools/mt8167-arm64`, verifier `lidar`,
  `lidar@1`, `hardware_accepted: false`, layout `["kaeru"]`.
  Canonical sha256: `b57f3cecc965a9d39fd54f50c420ba0acc3a1bb37e508187dc5caeb67a23cf28`.
- Schema `lidar` `allOf` block; `KNOWN_TARGETS`/`IDENTITY` registration.
- Tests: descriptor shape and cross-SoC rejection, OTA v1 control with
  `soc=mt8167` accepted while `mt8163` is rejected, stable-preparation refusal,
  unchanged Radar/Biscuit digests, route rejection of an unaccepted target.

## Parity proof

Radar and Biscuit descriptor files are byte-identical to `bc167529`; their
canonical digests remain
`b9e8c5a78178f697634aa3a705ef52efe9f039a162413e289d3e85df3a5b39ab` and
`7c58bec0e9f09652d7ff7ce587c0eb58ee3bd5a22b320ff127f3f85c1690c454`.
`validate-targets.py` still prints exactly those two lines; asset names, tags
and manifests are unchanged. A regression test asserts the digests.

## layout_profiles: why `kaeru`

A layout profile records the boot-chain/unlock generation a target's flash
layout uses: `docs/porting/README.md:335` shows Biscuit as
`["amonet", "pinned"]`, and `docs/install/README.md:203-208` defines the Kaeru
unlock route and its fastboot/recovery button behaviour. `AGENTS.md:70-88`
describes Kaeru as the current v2.0.0 chain with `expdb` holding the LK-stage
payload. Lidar is already Kaeru fastboot with A/B `boot_a`/`boot_b` and has no
Amonet stage (Platform `tools/mt8167-arm64/libreecho_platform_targets.py:63-93`),
so its only applicable profile is `["kaeru"]`; reusing `amonet` would claim a
chain generation the device never has.

## INSTALLER_TARGETS

The one-shot installer still hardcodes Radar and Biscuit identity in
`tools/libreecho-install.py`, and its future `TARGET_INDEX` would otherwise
have to list every registered target. `build/ci/target_registry.py:14-20`
therefore keeps `INSTALLER_TARGETS = ("radar_puffin", "biscuit")` with a
`ponytail:` comment naming the upgrade path: delete the constant once the
installer gates support every registered target. It is deliberately not
derived from `hardware_accepted`, so accepting Lidar later cannot silently add
it to the installer.

## Tests

Environment: the Platform checkout lives at
`private/forks/LibreEcho-Platform` (branch `feature/lidar-support-0.14.6`,
read-only), not at the default sibling `platform/`. Tests honour
`LIBREECHO_PLATFORM_SRC`.

| Command | Tree | Result |
|---|---|---|
| `python3 -m unittest discover -s build/tests -p 'test_*.py'` | baseline worktree `bc167529`, no override | 20 unique failing IDs (Platform checkout absent) |
| same with `LIBREECHO_PLATFORM_SRC=…/LibreEcho-Platform` | baseline worktree | exit 0, all pass |
| `python3 -m unittest discover -s build/tests -p 'test_*.py'` | modified, no override | identical 20 IDs (`diff` empty) |
| same with `LIBREECHO_PLATFORM_SRC=…/LibreEcho-Platform` | modified | exit 0, all pass |
| `python -m unittest tools.test_release_tools` | modified | 108 tests, OK |
| `python3 build/ci/validate-targets.py --targets lidar` | modified | lidar, sha `b57f3cec…cf28` |
| `python3 -m unittest build.tests.test_multi_target.DescriptorTests` | modified | 18 tests, OK |

The temporary worktree at `/tmp/libreecho-baseline` was removed. The GitHub
workflow was not executed locally.

## Remaining: hosted arm64 kernel support (part of the generalization item)

Deferred, not dropped. Product CI currently provisions only an armhf userspace
cross, so an arm64 kernel cannot be built there; `build.sh` fails closed with a
clear message until this lands.

1. Pin an aarch64 kernel cross toolchain in the public inputs:
   `.github/workflows/build-release.yml:352` (`prepare-public-inputs`) and
   `:477-497` (musl toolchain build/cache steps), mirroring
   `build/ci/armhf_toolchain.py:7,55,60` and
   `build/inputs/armhf-cross-toolchain.lock.json`.
2. Select it in the kernel build: `build/build.sh:404-416` currently only maps
   arch to image/subdir and rejects arm64 without `LIBREECHO_KERNEL_CROSS`.
3. Add an `mt8167` branch for the MT8163-only production checks:
   `build/build.sh:54` (`TOOLS_DIR` hardcodes `tools/mt8163-arm32`),
   `:928-958` (MT8163 board/PMIC closure), `:960` (`AEABI`, arm32-only),
   `:974-982` (MT8163 audio topology), and `:2400` (connectivity bundle
   `mt8163-v181-stock-v1`). The Radar source-marker block `:993-1046` is
   guarded by source-file existence, so it does not fail on MT8167 but should
   still be scoped per target.
