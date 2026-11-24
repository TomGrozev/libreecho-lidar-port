# Lab OTA v0.2.35 (corrected inputs)

Host-only build: no device access, no install, no GBL in the bundle. All device
steps at the bottom are **unverified**: this unit was not reachable.

Status: **complete on the host**. Kernel, Sendspin sources, sendspind, UI
bundle, audio engine, airplay2 payload, boot images, signed OTA v3 bundle, and
all host validators ran green, with one expected check that cannot pass (see
"Sendspin note").

## Inputs (exact commits)

| Input | Source | Commit |
|---|---|---|
| Kernel | `private/forks/LibreEcho-Linux-618`, branch `fix/lidar-port-identity` | `47feddd6b58f7d3cbc22a50940ecc6a44c3af833` |
| Kernel base (`kernel-step36-thermal`) | same branch | `8cb65710c72f` (parent of `47feddd6`) |
| Platform | `feature/lidar-support-0.14.6` | `02ef8ad6a2e0f9faa59a83f2510ed3c7cbb8be38` |
| UI | `feature/lidar-support-0.14.6` | `f584cf7314d72d9e921a60a91a9aaf91929bbd8a` |
| UI required fixes | same branch | `0cc5507` (announce), `81aaae3` (radio setting), `f584cf7` (radio panel) |

`47feddd6` is a direct child of `8cb65710`, so `kernel-step36-thermal` and the
uart2 DTS are the same branch; no branches were combined. The kernel was built
at `47feddd6` from a clean worktree.

Platform's main checkout had uncommitted peer work
(`tools/mt8163-arm32/airplay/*`, `tools/mt8167-arm64/libreecho_platform_targets.py`).
The build used a detached worktree at the Platform commit instead, so that peer
work is **not** in the bundle.

### UI link workaround (recorded, not for the branch)

UI HEAD does not link `esphomed`: `7f5c29a` calls `le_service_command()` from
`esphomed.c` but leaves `src/service_env.c` out of `ESPHOMED_SOURCES`. The build
worktree `src/UI` carries one uncommitted Makefile change adding
`src/service_env.c` to that list; it is not committed and should be fixed on the
UI branch. The image records `source_diff_sha256` so the diff is traceable.

### Sendspin note

`sendspind` was rebuilt from UI `f584cf7314` with the pinned sources
(`build_sendspind.sh`; deps staged by `fetch-public-deps.py --feature sendspin`).
Its sha256 is `36572977d922…e41e4`, **byte-identical to v0.2.33's binary**. No
sendspind-linked source changed between `715dd4f` and `f584cf7` (`git diff
--stat` over `src/adapter/sendspin`, `src/adapter/sendspind.cpp` and the adapter
C files is empty), so a fresh build reproduces the same bytes. The binary is
freshly built, not reused; the "differs from v0.2.33" check cannot pass and is
recorded as a known outcome, not a failure.

## Commands run

Workspace root `/workspace/libreecho`; `D=private/artifacts/phase-07/ota-v0.2.35`.

## Build commands used (record; scripts since deleted)

The hand build and install scripts named below were removed in favour of
`tools/lab-build.py`. The commands are kept as the record of how v0.2.35 was made;
they are not runnable from this repository.

```sh
# Platform and kernel worktrees at the exact commits (peer work excluded)
git -C private/forks/LibreEcho-Platform worktree add --detach \
  $PWD/$D/src/Platform 02ef8ad6a2e0f9faa59a83f2510ed3c7cbb8be38
git -C private/forks/LibreEcho-Linux-618 worktree add --detach \
  $PWD/$D/src/Linux-618 47feddd6b58f7d3cbc22a50940ecc6a44c3af833

# Kernel (LLVM, same recipe as phase-06 step36)
cd $D/src/Linux-618
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=step36 \
  KBUILD_BUILD_TIMESTAMP="2026-11-22 00:00:00 UTC"
make -s O=/tmp/lidar-618-ota0235b ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make -s O=/tmp/lidar-618-ota0235b ARCH=arm64 LLVM=1 -j$(nproc) \
  Image mediatek/libreecho-lidar.dtb
cp /tmp/lidar-618-ota0235b/arch/arm64/boot/Image $D/kernel/Image
cp /tmp/lidar-618-ota0235b/arch/arm64/boot/dts/mediatek/libreecho-lidar.dtb $D/kernel/libreecho-lidar.dtb
cp /tmp/lidar-618-ota0235b/.config $D/kernel/config
/usr/bin/dtc -I dtb -O dts -o /tmp/ota0235.dts $D/kernel/libreecho-lidar.dtb

# Pinned Sendspin sources and fresh sendspind
python3 private/forks/LibreEcho/build/ci/fetch-public-deps.py \
  private/forks/LibreEcho/build/inputs/public-inputs.json --feature sendspin \
  --output $PWD/$D/deps \
  --patch-dir $PWD/$D/src/Platform/tools/mt8163-arm32/sendspin/patches \
  --source-lock $PWD/$D/src/Platform/tools/mt8163-arm32/sendspin/SOURCE.lock \
  --receipt $PWD/$D/deps-receipt.json
LD_LIBRARY_PATH=private/artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
CROSS_PREFIX=$PWD/private/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf- \
  bash $D/src/Platform/tools/mt8163-arm32/sendspin/build_sendspind.sh \
  $PWD/$D/src/UI $PWD/$D/deps $PWD/$D/sendspind

# UI bundle (f584cf7 + the Makefile workaround)
COMP_DIR=$PWD/$D/components/ui UI_SOURCE_DIR=$PWD/$D/src/UI \
  bash private/lab/phase-07/sendspin-silence/deploy/build_components_sendspin.sh ui

# Audio engine from Platform HEAD
private/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-gcc \
  -O2 -std=c99 -Wall -I$D/src/Platform/tools/mt8163-arm32/airplay \
  -Iprivate/artifacts/phase-06/features-airplay2-lidar/work/tinyalsa-e43025bbf702eb7dd8edd48c1eb50530c60f1de8/include \
  -o $D/engine/libreecho-audio-engine \
  $D/src/Platform/tools/mt8163-arm32/airplay/{audio_engine,aec_reference,audio_sink,audio_timing,audio_visualizer,playback_status}.c \
  -Lprivate/artifacts/phase-06/features-airplay2-lidar/work/tinyalsa-e43025bbf702eb7dd8edd48c1eb50530c60f1de8/src \
  -ltinyalsa -ldl -lm
# then arm-linux-gnueabihf-strip --strip-unneeded

# airplay2 payload: base = features-715dd4f root, fresh sendspind + engine
cp -a private/artifacts/phase-07/features-715dd4f/root $D/payload/root
install -m0755 $D/sendspind/libreecho-sendspind $D/payload/root/usr/local/sbin/
install -m0755 $D/engine/libreecho-audio-engine $D/payload/root/usr/local/sbin/
bash private/forks/LibreEcho/build/package_feature_payload.sh airplay2 \
  $D/payload/root $D/payload/staging/probe.payload.squashfs \
  $D/payload/staging/probe.manifest.json
python3 private/lab/phase-07/ota-v0.2.35/make_catalog.py $D

# Boot images (needs qemu-arm-static on PATH for the ramdisk parser check)
export PATH=$PWD/private/artifacts/phase-05/host-tools/qemu/usr/bin:$PATH
KERNEL_DIR=$PWD/$D/kernel \
LIDAR_TOOLS=$PWD/$D/src/Platform/tools/mt8167-arm64 \
UI_BUNDLE_DIR=$PWD/$D/components/ui/ui-bundle/bundle \
UI_SOURCE=$PWD/$D/src/UI \
UI_COMMIT=f584cf7314d72d9e921a60a91a9aaf91929bbd8a \
UI_DIFF_SHA256=021ce53e60a11de62f2bfa10ab5709de4aef1704b2cf2265e831d6f669714df9 \
  bash private/lab/phase-07/sendspin-silence/deploy/build_images_sendspin.sh \
  --output-dir $PWD/$D/images

# Signed OTA v3 bundle
python3 private/lab/phase-05/ota/make_lab_ota.py \
  --boot-image $D/images/boot-lidar-v2.img \
  --feature-catalog $D/feature-catalog.json \
  --release lidar-lab-v0.2.35 --version 0.2.35 \
  --update-channel dev --service-profile production \
  --signing-key private/artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key private/artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output $D/ota/lidar-lab-v0.2.35.ota.tar
```

## Artifacts and sha256

| File | sha256 |
|---|---|
| `kernel/Image` | `272090a9c38fce616f15bd1a68bf2aee3ada763e0cf93a6d8e01b526b40089d2` |
| `kernel/config` | `26ffe02e85fe0f051970103b5a1410ee6e90f8b48a7e325eed8f7f9d1147912f` |
| `kernel/libreecho-lidar.dtb` | `0e9cc4ffd16b6ece79d5c698a15bb35aa5e252c73276f9525f9e73f64154913a` |
| `sendspind/libreecho-sendspind` | `36572977d9221f2389fe6deec9a8f674307da3418aa1886da74d4b02419e41e4` |
| `engine/libreecho-audio-engine` | `9334df030810136e9c0c5413d90aa4e54c46d0d0b4d83e767c8f1756ca3d1ea5` |
| `libreecho-lidar-base-airplay2-ad80d0d5….payload.squashfs` | `ad80d0d572eabf7cddae4e38b6cb47c858ff43386d6969b6f24f1b0a50a7c1dc` |
| `libreecho-lidar-base-airplay2-ad80d0d5….manifest.json` | `ffd4bcfc3a31d4c9fe172c0c3b7fc7e94f3e9627933791e1d68334f42a864c33` |
| `images/boot-lidar-dev.img` | `8b9c6f493a0cace4633e1feec3ce2cc6099aaebb92de9b28d607e8770887e229` |
| `images/boot-lidar-v1.img` | `f6f566692e7ac21a86f67f470ee26dfd1f9f6fca76317952f66037606231bd69` |
| `images/boot-lidar-v2.img` | `357ad590e6bed19b0cebb6c56563d0d5c392cd67b4e8b40aca11efb887246384` |
| `images/boot-lidar-v2.ramdisk.cpio.xz` | `136f7c7bd286ec2aed0478e08cf11987ea7fb240b6830362e3e561274504039b` |
| `feature-catalog.json` | see `SHA256SUMS` |
| `ota/lidar-lab-v0.2.35.ota.tar` | `e37034da43ebf2fa4e4592a7c47121f081329c8047781d1734b30d03619cd0b4` |
| `ota/generations/txn-48142a2f934809419cb5ac35/target.manifest` | see `SHA256SUMS` |
| `build-info.json` | see `SHA256SUMS` |
| `SHA256SUMS` (50 deliverable files) | `8f7ef276a27206ad505f444fff0b5c245b9dae101eddff20b7ad10f6598ce7eb` |

UI in the image: `source_commit=f584cf7314…`,
`source_diff_sha256=021ce53e60a11de62f2bfa10ab5709de4aef1704b2cf2265e831d6f669714df9`.

`SHA256SUMS` covers the deliverable tree but skips the build worktrees
(`src/`, `deps/`, `components/`, `payload/root`), which are inputs, not
artifacts. `build-info.json` holds the machine-readable record.

## Host checks (all run, all green)

| Check | Result |
|---|---|
| Kernel config | `CONFIG_SENSORS_LM75=y`, `CONFIG_THERMAL=y`, `CONFIG_CPU_THERMAL=y` |
| DTB contract | `verify_lidar_dtb.py` PASS: `compatible=amzn,lidar-pvt`, reboot mode `/soc/watchdog@10007000/reboot-mode`; `board-thermal` + `ti,tmp112` present; **no** `uart-has-rtscts` anywhere |
| Image build | `lidar_recovery_image_contract=PASS` for dev, v1, v2; payload image `boot-lidar-v2.img` within margin (4.03 MiB free) |
| Image inputs | `boot-lidar-v2.manifest.json` kernel/dtb/config hashes match the files above |
| Ramdisk | `target_id=lidar`; `/etc/libreecho/ota-public-key.hex` = lab key; `lidar_radio_bringup` and `last_check=wifi-radio`/`target-identity` gates present (also exercised by the image verifier under qemu) |
| OTA signature | Ed25519 `target.manifest` verifies with lab public key; the v0.2.33 public key is rejected |
| Release components | `check-release-components.py --target lidar`: `donor_gate=cleared`, `component_gate=cleared`, 21 components, no GBL/EFR32 firmware |
| Payload binaries | extracted squashfs `libreecho-sendspind` = `36572977…`, `libreecho-audio-engine` = `9334df03…` |
| Sendspin freshness | freshly built; byte-identical to v0.2.33 (source-level explanation above) |

## On-device install and check steps (unverified, not run)

1. Install without a GBL: `ota/lidar-lab-v0.2.35.ota.tar` through the lab OTA
   path (adb push + `libreecho-update-verify` as the hand install script, since
   removed, did); the bundle writes the
   inactive slot only.
2. Reboot into the new slot; confirm `boot_state=confirmed`
   (`libreecho-bootctl status`).
3. Thermal: `for z in /sys/class/thermal/thermal_zone*; do echo $(cat $z/type) $(cat $z/temp); done`
   → `board-thermal <non-zero>` (~25000 at idle).
4. Announce: trigger an announcement from Home Assistant; audio plays (the
   `0cc5507` chunk-extension fix is in `libreecho-esphomed`).
5. Radio setting: the web UI shows the Lidar radio panel and the setting
   persists across reload (`81aaae3`, `f584cf7`).
