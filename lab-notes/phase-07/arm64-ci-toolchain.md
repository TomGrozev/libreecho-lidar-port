# Phase 7: hosted aarch64 kernel cross toolchain

Fork: `private/forks/LibreEcho`, branch `feature/lidar-support`, not pushed.
Base: `bc167529`; branch tip before this work: `257404952e47bbea2bd73dd9295c8516d4515762`.

Scope: the two remaining parts of the `build.sh` / CI generalization item: the
fail-closed arm64 kernel guard and the MT8163-only production gates, plus a
pinned aarch64 kernel cross in the public inputs. Installer work is separate.

## Toolchain lock

`build/inputs/aarch64-cross-toolchain.lock.json` pins 33 amd64 host packages:
the aarch64-linux-gnu gcc-13/binutils cross, glibc 2.39 `libc6-dev-arm64-cross`,
`linux-libc-dev-arm64-cross`, and their host runtime dependencies.

- Index digests: noble `2a6a199e…92451`, noble-updates `3bce1e3f…85d14`,
  noble-security `dca33d8c…3dde3`; selection prefers security > updates >
  release. InRelease digests are recorded per pocket.
- Trust anchor is the same Ubuntu 2018 archive key as the ARMHF lock
  (`F6EC…C93C`); every archive sha256/size was checked against the signed
  `Packages.xz` after download.
- Target is `aarch64-linux-gnu-glibc-dynamic`. The lock explicitly does not
  claim host independence: the prefix carries no amd64 libc, so the cross
  compiler executes against the runner libc. Only the target closure is pinned.

## Code

- `build/ci/armhf_toolchain.py`: the materializer/verifier now takes a
  `Family` (schema ids, receipt name, target, prefix path, stage prefix,
  generator). `ARMHF` preserves every module constant and default, so the
  existing 79-test suite passes unchanged. New `fetch` subcommand downloads the
  locked URLs with retries, re-hashes each file, deletes a file that does not
  match, and runs the archive verifier before returning.
- `build/ci/aarch64_toolchain.py`: thin CLI binding `AARCH64`. Families reject
  each other's lock schema, so an aarch64 stage/verify cannot consume the ARMHF
  lock.
- `.github/workflows/build-release.yml`: `prepare-public-inputs` now fetches,
  stages and re-verifies the aarch64 prefix, caches prefix+archives under the
  lock hash, publishes `aarch64-root-<source_set_id>`, and exposes a receipt
  digest. `build-image` downloads it, sets `LIBREECHO_AARCH64_CROSS`, adds the
  cross's host lib dir to `LD_LIBRARY_PATH`, and computes the kernel cache key
  from the **first selected target's** arch/defconfig and the matching compiler
  bytes. The Radar/Biscuit key inputs are unchanged, so their key value stays
  byte-identical.
- `build/build.sh`: `TOOLS_DIR` and every path derived from it moved after the
  descriptor is resolved; `KERNEL_CROSS` is `LIBREECHO_AARCH64_CROSS` for
  `arm64` and `CROSS` for `arm`; the fail-closed guard is gone; DTB path uses a
  per-arch DTS subdir (`arch/arm64/boot/dts/mediatek`); the MT8163 USB/PMIC/
  codec closure, `AEABI`/`OABI_COMPAT`, Radar source markers and the MT8163
  connectivity-bundle verifier argument are arm32-only, with an MT8167 branch
  requiring `USB_CONFIGFS_{ACM,NCM}`, `MTK_PMIC_WRAP`, `REGULATOR_RT5739`,
  `MT7668_SDIO`, `BT_MTKSDIO`, `SND_SOC_MT8516{,_AMAZON_LIDAR}`.
- `tools/test_build_release_workflow.py`: the kernel-key assertions now name
  the descriptor-derived key and assert the old literal is absent.

## Tests

| Command | Result |
|---|---|
| `python3 -m unittest build.tests.test_armhf_toolchain` | 79 tests, OK (1 skip) |
| `python3 -m unittest build.tests.test_aarch64_toolchain` | 4 tests, OK (1 skip; real stage/verify covered by the manual run) |
| real `aarch64_toolchain.py stage/verify` on the 33 downloaded debs | PASS, 2791 files, tree `8d39939e…ea0e`, receipt `23317c71…c561` |
| `python3 -m unittest tools.test_build_release_workflow` | 33 tests, 1 failure (`cffi` wheel) |

Baseline confirmation: in a detached worktree at `bc167529`,
`test_stable_publisher_installs_reviewed_verifier_closure` fails identically:
the reviewed closure only ships a cp311 cffi wheel and this host is Python
3.14, and `test_cache_layers` passes. The cache-key failure is therefore
introduced by `eefd5989` (which dropped the literal) and is fixed by updating
the assertion; the cffi failure is environmental baseline.

## Kernel build

Local build with the staged pinned prefix (`/tmp/a64/prefix`, tree
`8d39939e…ea0e`), kernel `LibreEcho-Linux-618` at `fix/lidar-port-identity`:

```
make O=/tmp/lidar-kbuild ARCH=arm64 CROSS_COMPILE=/tmp/a64/prefix/usr/bin/aarch64-linux-gnu- \
  LD=/tmp/a64/prefix/usr/bin/aarch64-linux-gnu-ld.bfd mt8167_arm64_defconfig
KBUILD_BUILD_TIMESTAMP=<commit date> make ... Image mediatek/libreecho-lidar.dtb
```

Result: `Image` (15 MiB) sha256
`1d81b03fb0f48367f6ed9a5fa06db2964e214a1fd02e9fd4527ad5dffb481fd7`;
`arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb` sha256
`a8e1957314334d9a03aa6c96082a6d82a1202ee02729cdc2097d8355d6bd5bc7`.

The first attempt also proved the DTB make target must be
`mediatek/libreecho-lidar.dtb`, not the bare file name; `build.sh` now carries
a per-arch `KERNEL_DTB_TARGET`.

## Not verified

- GitHub workflow not executed; the aarch64 cache-restore path was exercised
  locally through `stage`/`verify`.
- `build.sh` was syntax-checked (`bash -n`) but a full `build.sh` run needs the
  complete public-input inventory and was not attempted.
