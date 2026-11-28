# v0.2.26 rebuild with the step-33 kernel/UI fixes

Host only, 2026-11-22. Nothing was installed, booted or committed.

## 1. How the earlier v0.2.26 was built

`artifacts/phase-06/ota-step33-followup/` (08:37) came from
`experiments/phase-06/build_images.sh --output-dir artifacts/phase-06/images-step33-followup`
with the kernel at `artifacts/phase-06/kernel` (byte-identical to
`artifacts/phase-06/latency/cpufreq`: `Image 8acf87fe…`, config `0ade3894…`, DTB
`e8727c88…`) and a clean detached UI worktree at `e564bf5` (empty diff hash
`e3b0c442…`). `Image 8acf87fe…` is the build of `fix/lidar-port-identity` HEAD
`77931cc969448da586fd09f38bf61c1fd3b4938e`; `git reflog` shows `77931cc` as the
tip and there are no commits after it. The only config delta against our build
is `CONFIG_SENSORS_LM75=y`; the base commit already carries the cpufreq change.
Verified by reflog/branch scan, so no later kernel commit is missing from ours.

## 2. Inputs used

- Kernel: `artifacts/phase-07-prep/kernel/{Image,config,libreecho-lidar.dtb}`
  (`Image de09ed1d…`, config `26ffe02e…`, DTB `a28044aa…`), built from
  `77931cc` + the uncommitted `KernelFixes.md` changes.
- UI: `repos/LibreEcho-UI` working tree, HEAD `e564bf569775…` plus the
  uncommitted step-33 changes. Source diff hash computed with the builder's own
  algorithm: `3926c062eab0810b81f9e28ffec3fa8c25e93c5c4f1db8e42ded0c5dfcfcdf8c`.
  Source provenance: `SOURCE_DIRTY=1`, digest `e19845c7…`.

The shared `repos/LibreEcho-UI/build/` was not cleaned or reused. The worktree
was copied to `/tmp/libreecho-ui-v26-build/src` (including `.git` and the
uncommitted files) and the bundle was built there.

## 3. Exact commands

```sh
mkdir -p /tmp/libreecho-ui-v26-build/src
rsync -a repos/LibreEcho-UI/ /tmp/libreecho-ui-v26-build/src/

mkdir -p artifacts/phase-06/components-step33-fixes/ui-bundle \
         artifacts/phase-06/components-step33-fixes/logs
env LD_LIBRARY_PATH=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
  LIBREECHO_UI_CROSS_COMPILE=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf- \
  LIBREECHO_UI_MBEDTLS_ROOT=/workspace/libreecho/artifacts/phase-06/components/mbedtls-arm32 \
  LIBREECHO_OPUS_ARCHIVES_DIR=/workspace/libreecho/artifacts/phase-05/toolchains/sources/opus \
  LIBREECHO_OPUS_CC=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-gcc \
  LIBREECHO_OPUS_AR=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-ar \
  LIBREECHO_OPUS_HOST=arm-linux-gnueabihf \
  LIBREECHO_UI_MUSL_NATIVE_ROOT=/workspace/libreecho/artifacts/phase-05/toolchains/musl \
  LIBREECHO_UI_MUSL_SYSROOT=/workspace/libreecho/artifacts/phase-05/toolchains/musl \
  LIBREECHO_UI_MUSL_CC=/workspace/libreecho/artifacts/phase-05/toolchains/musl/usr/bin/armv7-alpine-linux-musleabihf-gcc \
  LIBREECHO_UI_MUSL_NATIVE_LIB=/workspace/libreecho/artifacts/phase-05/toolchains/musl/usr/lib \
  repos/LibreEcho-Platform/tools/mt8163-arm32/ui/build_ui_bundle.sh \
    /tmp/libreecho-ui-v26-build/src \
    artifacts/phase-06/components-step33-fixes/ui-bundle/bundle \
  > artifacts/phase-06/components-step33-fixes/logs/ui-build.log 2>&1

KERNEL_DIR=$PWD/artifacts/phase-07-prep/kernel \
UI_BUNDLE_DIR=$PWD/artifacts/phase-06/components-step33-fixes/ui-bundle/bundle \
UI_DIFF_SHA256=3926c062eab0810b81f9e28ffec3fa8c25e93c5c4f1db8e42ded0c5dfcfcdf8c \
  experiments/phase-06/build_images.sh \
    --output-dir $PWD/artifacts/phase-06/images-step33-fixes \
  > artifacts/phase-06/components-step33-fixes/logs/images-build.log 2>&1

mkdir -p artifacts/phase-06/ota-step33-fixes
uv run --with pynacl python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image artifacts/phase-06/images-step33-fixes/boot-lidar-v2.img \
  --feature-catalog artifacts/phase-06/features-airplay2-latency/feature-catalog.json \
  --release lidar-lab-v0.2.26 --version 0.2.26 \
  --update-channel dev --service-profile production --config-schema 1 \
  --signing-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output artifacts/phase-06/ota-step33-fixes/lidar-lab-v0.2.26.ota.tar
```

`experiments/phase-06/build_images.sh` gained three opt-in environment
overrides, defaults unchanged: `KERNEL_DIR` (default `artifacts/phase-06/kernel`),
`UI_BUNDLE_DIR` (default `artifacts/phase-06/components/ui-bundle/bundle`) and
`UI_DIFF_SHA256` (default the empty-diff hash). All other recipe inputs, the
lab key and the dev channel are unchanged.

## 4. Results

UI bundle manifest (`ui_manifest_sha256=36dbcbc3c9afdbea876dcbe4ee27a9591a271269f1ac00ea75c0a13e849205f8`).

| Boot image | sha256 |
|---|---|
| `boot-lidar-dev.img` | `2304a34d4c130ebed8c8dbe3329cdce721a50f9dc0076e2b28c53fb3941953da` |
| `boot-lidar-v1.img` | `8cf9530547421082bc0a959c2328e02c3678803a7d2549c1825a69a69d65ac33` |
| `boot-lidar-v2.img` (OTA payload) | `bbe29a43e4624009e23bead9ee738af92dc62d7fcb2593e8554aaace63c60bbe` |

Verifier output (all three):

```
lidar_recovery_image_contract=PASS android_v0=yes mtk_wrapper=yes arm64_kernel=yes lidar_dtb=yes initramfs_arm32=yes image_profile=ota service_profile=production feature_policy=preserve ota=yes gzip_kernel_bytes=5829655 dtb_collection_bytes=1028366 ramdisk_bytes=5765724 margin_to_16mib_bytes=4149248 status=PREPARED_NOT_FLASHED
```

OTA:

- Bundle: `artifacts/phase-06/ota-step33-fixes/lidar-lab-v0.2.26.ota.tar`
- sha256: `a1866152c30693c42d905f27d41da768659c4164a6a7780d2c923514e3c82ddd` (16,793,600 bytes)
- Transaction: `txn-47f1e4ac45f4d1d18417b8c8`
- `libreecho-update-verify <pub> target.manifest target.manifest.sig` → `ota_manifest_signature=PASS`

## 5. Inclusion proof

Extracted boot.img from the tar is byte-identical to `boot-lidar-v2.img`
(`bbe29a43…`).

- Kernel: file offset 2048, `kernel_size=6858533`; the first 512 bytes are the
  MTK header, the following 5,829,655 bytes are gzip. Inflated result sha256
  `de09ed1d9b3a9485d92eedf11a3a9fd303b6e16376c3e074ee73a3428ea5ba7a`, `cmp`
  identical to `artifacts/phase-07-prep/kernel/Image`.
- DTB: the kernel section payload is `gzip_kernel + dtb collection`
  (5,829,655 + 1,028,366). The extracted collection at offset
  `2048+512+5829655` has sha256
  `42bd5054cbd9475d79a19629392448a33185ed445f3cd2b70875d2ee1e497389`, the
  manifest value. Entry 4 (index 4, 23,395 bytes, the packed DTB) is our
  23,306-byte DTB plus the `/chosen` initrd properties the builder adds: the
  576-byte window around `als_name`/`taos_als` is byte-identical in both, the
  `tmp112` string sits at the same offset 12,843, and `board-thermal` is present.
  The manifest records `inputs.dtb.sha256 = a28044aa…`.
- UI: the ramdisk xz unpacks to a newc cpio; `usr/local/sbin/libreecho-web`
  contains `rolling-back` and `e564bf56977527b5378f1b4f0e60bc16535428a5`
  (plus the dirty-tree digest `e19845c7…`);
  `usr/local/sbin/libreecho-timed` contains `/data/libreecho/config/time-epoch`.
  The image manifest records `ui.commit=e564bf5…` and
  `ui.diff_sha256=3926c062…`.

## 6. Not done

No device access, no install, no reboot, no commit. The new bundle was not
flashed; the device state is unchanged.

---

# v0.2.27 (fix/lidar-als, committed UI)

Host only, 2026-11-22. Nothing was installed, booted or committed.

Same recipe as v0.2.26 above. Inputs:

- Kernel `artifacts/phase-07-prep/kernel-als/`: `Image 53417fd7390f2b7e…`,
  DTB `fe0fc1391396c895…` (23,326 bytes), config `26ffe02e…`.
- UI: clean clone of `repos/LibreEcho-UI` HEAD
  `27a4363a7612010e68e9b63683d6cce6a36cae53` at
  `/tmp/libreecho-ui-v27b` (`SOURCE_DIRTY=0`, digest `e19845c7…`); builder diff
  hash is the clean value `e3b0c442…`.

`experiments/phase-06/build_images.sh` also gained a `UI_COMMIT` environment
override (default `e564bf5…`) for this build.

```sh
git clone --quiet --no-hardlinks /workspace/libreecho/repos/LibreEcho-UI /tmp/libreecho-ui-v27b

mkdir -p artifacts/phase-06/components-step35-als/ui-bundle \
         artifacts/phase-06/components-step35-als/logs
env LD_LIBRARY_PATH=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
  LIBREECHO_UI_CROSS_COMPILE=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf- \
  LIBREECHO_UI_MBEDTLS_ROOT=/workspace/libreecho/artifacts/phase-06/components/mbedtls-arm32 \
  LIBREECHO_OPUS_ARCHIVES_DIR=/workspace/libreecho/artifacts/phase-05/toolchains/sources/opus \
  LIBREECHO_OPUS_CC=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-gcc \
  LIBREECHO_OPUS_AR=/workspace/libreecho/artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-ar \
  LIBREECHO_OPUS_HOST=arm-linux-gnueabihf \
  LIBREECHO_UI_MUSL_NATIVE_ROOT=/workspace/libreecho/artifacts/phase-05/toolchains/musl \
  LIBREECHO_UI_MUSL_SYSROOT=/workspace/libreecho/artifacts/phase-05/toolchains/musl \
  LIBREECHO_UI_MUSL_CC=/workspace/libreecho/artifacts/phase-05/toolchains/musl/usr/bin/armv7-alpine-linux-musleabihf-gcc \
  LIBREECHO_UI_MUSL_NATIVE_LIB=/workspace/libreecho/artifacts/phase-05/toolchains/musl/usr/lib \
  repos/LibreEcho-Platform/tools/mt8163-arm32/ui/build_ui_bundle.sh \
    /tmp/libreecho-ui-v27b \
    artifacts/phase-06/components-step35-als/ui-bundle/bundle \
  > artifacts/phase-06/components-step35-als/logs/ui-build.log 2>&1

KERNEL_DIR=$PWD/artifacts/phase-07-prep/kernel-als \
UI_BUNDLE_DIR=$PWD/artifacts/phase-06/components-step35-als/ui-bundle/bundle \
UI_COMMIT=27a4363a7612010e68e9b63683d6cce6a36cae53 \
UI_DIFF_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 \
  experiments/phase-06/build_images.sh \
    --output-dir $PWD/artifacts/phase-06/images-step35-als \
  > artifacts/phase-06/components-step35-als/logs/images-build.log 2>&1

mkdir -p artifacts/phase-06/ota-step35-als
uv run --with pynacl python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image artifacts/phase-06/images-step35-als/boot-lidar-v2.img \
  --feature-catalog artifacts/phase-06/features-airplay2-latency/feature-catalog.json \
  --release lidar-lab-v0.2.27 --version 0.2.27 \
  --update-channel dev --service-profile production --config-schema 1 \
  --signing-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key artifacts/phase-05/ota/lab-key/ed25519-public.hex \
  --output artifacts/phase-06/ota-step35-als/lidar-lab-v0.2.27.ota.tar
```

Results:

- UI bundle `ui_manifest_sha256=b885f7e938bbf2b9ce09d416b958221dea7f8a1e309f37584183ff70eef480ce`.
- Images: dev `10855496b32f2afb…`, v1 `7619af6d3e4cdc67…`, v2
  `3e71c0bceb55f3a8e8ae8e7d1a6771f9c00f927759812a9a5a8483603510c773`.
- Bundle `artifacts/phase-06/ota-step35-als/lidar-lab-v0.2.27.ota.tar`,
  sha256 `e611c9c9f8cb44dd8874596fe41854f33bb2a31169381a030b62b516942ddd14`
  (16,793,600 bytes), transaction `txn-b0a9e76b738c1b4d1b64ae8a`;
  `ota_manifest_signature=PASS`.
- Verifier (all three, v2 shown):

```
lidar_recovery_image_contract=PASS android_v0=yes mtk_wrapper=yes arm64_kernel=yes lidar_dtb=yes initramfs_arm32=yes image_profile=ota service_profile=production feature_policy=preserve ota=yes gzip_kernel_bytes=5829703 dtb_collection_bytes=1028386 ramdisk_bytes=5765536 margin_to_16mib_bytes=4149248 status=PREPARED_NOT_FLASHED
```

Inclusion proof (`/tmp/v27-incl`): tar `boot.img` is byte-identical to
`boot-lidar-v2.img` (`3e71c0bc…`). Kernel: offset 2048, `kernel_size=6858601`
(512-byte MTK header + 5,829,703-byte gzip); inflated sha256
`53417fd7390f2b7ec9c6fd5073674b3528d50ea0b13efa15c4bb17cf1af1ccf6`, `cmp`
identical to `kernel-als/Image`. DTB: collection at `2048+512+5829703` has
sha256 `55403f4b4e7d729c34c931813d6e7a959493f703e90d6cfdd08707a0add68f8d`
(manifest value); entry 4 is 23,415 bytes, its 320-byte window around
`boot-on` is byte-identical to ours (offsets 22,115 vs 22,162), and `tmp112`
sits at the same offset 12,855. Manifest records `inputs.dtb.sha256=fe0fc139…`,
`ui.commit=27a4363…`, `ui.diff_sha256=e3b0c442…`.

Host disk was full (1.5 MiB free). `uv cache prune` freed 106 MiB and the
superseded v0.2.26 intermediates (`images-step33-fixes`,
`components-step33-fixes`) were moved to `/tmp/` (not deleted); the v0.2.26
bundle and its generation tree are untouched. No device access, no commit.

