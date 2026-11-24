# Donor-derived artifacts, capture and release refusal

Date: 2026-11-24. Host-only. No device access, no dump bytes in a repository.

## What was added

### Generator

`LibreEcho-Platform` `feature/lidar-support-0.14.6` `f9ac5cd9ab`,
`tools/mt8167-arm64/prepare/lidar_donor_artifacts.py`.

- Reads a backup directory and its `libreecho-lidar-backup-v1` manifest and
  calls `lidar_backup_set.require_complete_backup` first. A missing, resized or
  changed area is a refusal; nothing is written and no manifest appears.
- Requires the backup `boot0` to start with `EMMC_BOOT` and hash to the
  reviewed 2019 preloader
  `fb987ad9cd2af5e4d86e6476f1f154e555795d915d247a23110b80ed0363de45`.
- Requires the backup `tee1` to be an MTK ATF image.
- Writes `boot0-preloader.bin`, `tee1-stock.bin`, and, with a pinned Koboreru
  image, `tee1-stock-tail.bin` and the composed `tee1-stage.bin`.
- Writes `donor-artifacts.json` (`libreecho-lidar-donor-artifacts-v1`) with
  the backup manifest sha256 and one size/sha256 record per artifact.
- Refuses an output path inside a git checkout unless it starts with
  `private/`, `local/` or `local-firmware/`; a path outside every checkout is
  accepted. All writes are temp-file plus rename.

`lidar_prepare.py` now calls the generator in its install stage and consumes
`tee1-stage.bin` and `boot0-preloader.bin` from the manifest. The old
`build_chain` and `load_reviewed_preloader` helpers are gone. `install` takes
`--donor-dir`; `run` uses `<session>/donor-artifacts`. The preloader pin is
imported from the generator, so one constant owns it.

### Capture

`f9ac5cd9ab`, `tools/mt8167-arm64/prepare/capture_stock_gbls.py`.

Lab evidence for the location and identity is
`private/lab/phase-06/hw-20261121/step25-efr32/stock-firmware.txt` (read from
the stock `system_a` mount on 2026-11-21):

| Source in rootfs | Size | sha256 |
| --- | --- | --- |
| `system/vendor/firmware/silabs/xncp-fw.gbl` | 186480 | `1d9ed42ff12168f00394f84685c698e671f158874bc0dd2c7956388ebd212406` |
| `system/vendor/firmware/dsr/zb_mux_rcp.gbl` | 145216 | `4e138f84cd2b7f5eaba1835999e98df5b6750f07429fb6ab7e4df8b261f61849` |

The script reads a host directory only. It refuses a character/block device,
a non-regular file, a path that escapes the source root, a size or sha256
mismatch, and an existing destination with different bytes. It refuses an
output directory inside a checkout that is not private/local, and it writes
`local-firmware/.gitignore` (`*`, `!.gitignore`) so the GBLs cannot be staged.
Default output is `local-firmware/`.

### Release refusal

`LibreEcho` `feature/lidar-support` `f449b3f339`, corrected by `8e0d52f43c`.
`tools/prepare-release.py` `reject_donor_derived_artifacts` is called by
`tools/check-release-components.py` for its `--artifacts` paths. It refuses:

- GBL and EFR32/Gecko radio firmware, by calling `tools/radio_firmware.py`
  (`73508b6`). Those rules exist only there; `prepare-release.py` repeats no
  GBL suffix, name or magic.
- `88 16 88 58` (MTK preloader/LK/TEE header) and `EMMC_BOOT` (boot0
  preloader) at offset 0, only with `--target lidar` or a donor generator
  manifest. Radar and Biscuit releases ship MTK-headed LK, boot and Amonet
  images by design, so they must pass.
- Any sha256 from a `--donor-manifest` produced by the generator, at every
  target.

`prepare-release.py` runs the scan before writing provenance. A test with
Radar/Biscuit-shaped MTK images proves the default passes and the Lidar target
refuses. The published Radar and Biscuit asset files were not fetched for this
check; the scoping decision comes from their known boot-chain payloads and the
synthetic fixture, so that part is host-only and unverified against the live
release set.

## Tests run on the host

- `cd private/forks/LibreEcho-Platform && python3 -m unittest tools.mt8167-arm64.prepare.test_lidar_prepare tools.mt8167-arm64.prepare.test_lidar_donor_artifacts tools.mt8167-arm64.prepare.test_capture_stock_gbls`:
  49 tests OK.
- `cd private/forks/LibreEcho && python3 -m unittest tools.test_release_tools.DonorDerivedArtifactGateTests`:
  7 tests OK, including the Radar/Biscuit-shaped asset case.
- `python3 tools/check-release-components.py`: `component_gate=cleared
  component_count=21` (the committed catalog count on this branch).
- `python3 -m py_compile` on every changed Python file: OK.

All fixtures are synthetic: a 2 MiB fake preloader, a 5 MiB fake ATF tee1, a
fake Koboreru, and fake GBLs. No real dump byte is in either repository.

## Unverified (deferred until a second device arrives)

- No stage ran against hardware. The generator never touches a device, but
  its inputs on a real unit are the backup files that the `backup` stage has
  not yet produced on hardware.
- The reviewed-preloader pin was not checked against a fresh dump read. It
  matches the Phase 3 source
  (`private/lab/phase-03/sources/boot0_2019_area1.bin`); the generator will
  refuse if a future dump differs.
- The capture script was not run against a mounted stock rootfs. Its pins come
  from the 2026-11-21 read.
- The release scan was tested with synthetic bytes only; no real release
  artifact was checked.

## On-device steps (each needs separate approval)

1. Enter BROM and run `lidar_prepare.py ... backup`. This produces the
   manifest the generator verifies.
2. Run `lidar_donor_artifacts.py --backup-dir <backup> --out private/artifacts/lidar-chain --koboreru <built image> --koboreru-sha256 <hex>`.
   Review `donor-artifacts.json` and confirm the four records.
3. Continue with `drill`, `stock-boot` and `install`; `install` regenerates the
   same artifacts under the session directory and writes only their bytes.
4. To capture the stock GBLs from a unit, mount or extract its `system_a` on
   the host, then run `capture_stock_gbls.py --source <rootfs>`. Do not point
   it at `/dev` or an adb-forwarded path.
