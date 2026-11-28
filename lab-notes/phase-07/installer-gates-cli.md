# Phase 7: Lidar in the one-shot CLI installer

Fork: `private/forks/LibreEcho`, branch `feature/lidar-support`, based on
`257404952` (register the Lidar target). Local only, not pushed.

## What changed

The installer keeps one gate chain for every target; Lidar adds data to the
existing tables rather than a second path.

- **Identity**: `TARGET_INDEX` now carries the descriptor identity for all three
  targets: `release_slug`, `fastboot_products`, `soc`, `arch`, `hw_profile`,
  `boot_slots`. Lidar is `LIDAR`, `mt8167`, `arm64`, `lidar@1`
  (`release/targets/lidar.json`). `verify_fastboot_product` therefore accepts a
  Lidar only when the fastboot product is `LIDAR`, and rejects a mismatched
  product or a cross-target override.
- **Pin**: `TARGET_PIN_RULES` adds `lidar: "already-converted"`.
  `plan_fastbrick` requires `oem kaeru-version` to answer `OKAY`; a stock
  refusal or an indeterminate answer refuses before any write, and the function
  returns `None` (no brick) on success. `AMONET_PINS` has no Lidar entry, so
  `select_amonet_payload("lidar", ...)` still refuses. An install manifest for a
  target without a pin must carry an empty `amonet` record.
- **Payload geometry**: Lidar keeps `boot_a`/`boot_b` as the 16 MiB stores. The
  geometry gate now rejects any `boot_a_x`/`boot_b_x` on a target with the
  already-converted rule instead of treating it as a legacy Amonet layout.
- **Userdata geometry**: `USERDATA_LIDAR_STOCK_BYTES = 9647071 * 512`
  (Platform `tools/mt8167-arm64/libreecho_platform_targets.py:35` and
  `tools/mt8167-arm64/install/lidar_install.py:18`). Lidar is in
  `USERDATA_EXACT_TARGETS`: only that size is accepted. Radar and Biscuit keep
  their existing exact-stock plus floor/cap rule, including both legacy Amonet
  sizes.
- **Readback**: `verify_adb_payload_readback` takes the target and accepts only
  `boot_a`/`boot_b` for Lidar (`READBACK_NAMES`). Radar and Biscuit still accept
  either `boot_X_x` or `boot_X`.
- **State**: the existing `board in TARGET_INDEX` check now accepts `lidar`
  without a new state phase or field.
- **OTA plan**: `_target_ota_plan` builds the immutable v3 control fields from
  the target's descriptor identity. `soc` is `mt8167`; `architecture` stays
  `armv7` because OTA manifests carry the userspace architecture
  (`build/ci/ota_v3_product.py:59`), while the kernel is arm64. The installer's
  standalone v3 closure now derives its target from the asset prefix instead of
  the biscuit/radar fallback.
- **Registry**: `INSTALLER_TARGETS` is deleted; every `KNOWN_TARGETS` entry is
  installer-supported, so `build/ci/target_registry.py` and the installer sync
  test compare against `KNOWN_TARGETS`. The sync test also checks `soc`, `arch`,
  `hw_profile` and `boot_slots` against each descriptor.

No code writes `expdb`, preloader, `lk_a`/`lk_b` or `tee1`/`tee2`: the only
fastboot flashes in the installer remain `brick` (Amonet targets only),
`userdata`, and `boot_{slot}`. The userdata-only format is unchanged.

## Contract for the web installer

`private/lab/phase-07/installer-lidar-contract.json` exports
`fastboot_product`, `hw_profile`, `userdata_sectors`, `boot_slots`, `pin_rule`
and the v3 `ota_plan`.

## Commit

`7f0d5c6` (local, not pushed): `feat(release): support Lidar in the one-shot
installer`. Files: `tools/libreecho-install.py`,
`tools/libreecho-install.py.sha256`, `tools/test_release_tools.py`,
`build/ci/target_registry.py`, `build/tests/test_multi_target.py`.

## Tests

Environment: `LIBREECHO_PLATFORM_SRC=/workspace/libreecho/private/forks/LibreEcho-Platform`.

| Command | Result |
|---|---|
| `python -m unittest tools.test_release_tools` | 115 tests, OK |
| `python -m unittest discover -s build/tests -p 'test_*.py'` | 375 tests, OK (5 skipped) |
| `python -m unittest tools.test_release_tools.LidarInstallerGateTests` | 7 tests, OK |
| `python -m unittest tools.test_initial_installer_publication.InstallerPublicationTests.test_checked_in_installer_matches_its_sha256_sidecar` | OK |

The Lidar gate tests cover: product-only identity, Kaeru-only pin with no
`flash` command, exact userdata geometry and rejection of other sizes, rejection
of a legacy `_x` layout, `boot_a`/`boot_b` readback names, the v3 plan identity,
state acceptance, and unchanged Radar/Biscuit geometry and readback.

## Unverified

- No hardware was touched; the Lidar identity/pin/geometry/readback paths are
  covered by command-level mocks only.
- The Lidar release producers that will emit an initial-install manifest with an
  empty Amonet record were not built or run here.
- `lidar-v*` release tags are not introduced; the installer's `RELEASE` pattern
  still names `radar-puffin-*` product tags, and per-target asset prefixes are
  derived as before.
