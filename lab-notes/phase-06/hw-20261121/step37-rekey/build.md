# Step 37: rebuild Phase 5 artifacts and re-key the lab OTA (v0.2.28)

Status: **incomplete** at the time this note was written (host build running).
`artifacts/phase-05/` was deleted; the old OTA signing seed is unrecoverable, so the lab
key rotated and v0.2.28 is built trusting the new key. No device access in this step.

## Key rotation (done)

`artifacts/phase-05/ota/lab-key/` was regenerated with
`repos/LibreEcho-Platform/tools/mt8163-arm32/ota/generate_ota_key.py`:

```sh
python3 repos/LibreEcho-Platform/tools/mt8163-arm32/ota/generate_ota_key.py \
  --private-key artifacts/phase-05/ota/lab-key/ed25519-seed.hex \
  --public-key  artifacts/phase-05/ota/lab-key/ed25519-public.hex
install -m 0600 artifacts/phase-05/ota/lab-key/ed25519-seed.hex   keys/ota-lab/ed25519-seed.hex
install -m 0644 artifacts/phase-05/ota/lab-key/ed25519-public.hex keys/ota-lab/ed25519-public.hex
```

| Item | Value |
|---|---|
| new public key hex | `42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18` |
| new public key file sha256 | `3efab6b623594c5ea582e2d40f3bda0ec224702593f91fe4acaee4d457b67e0a` |
| old public key hex | `25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d` |
| old public key file sha256 | `420e9763add79b3f9012c9da9eeeab2e929eff5d697e29c4f7a7b6fb5b724f28` |

The seed exists only in `artifacts/phase-05/ota/lab-key/ed25519-seed.hex` (0600) and the
durable `keys/ota-lab/` copy (0700 dir, seed 0600); it is never written under `repos/` or
into a commit. The temporary `/tmp/key-recover` copy was removed.

`experiments/phase-05/ota/README.md` records the rotation and both key values.

## Input staging (script written, not yet run to completion)

`stage_inputs.py` in this directory downloads and hash-checks, from the recorded locks:

- `toolchains/armhf-archives/*.deb` from `build/inputs/armhf-cross-toolchain.lock.json`
  (direct `archive.ubuntu.com` URLs, sha256 pinned in the lock);
- `components/mdns-packages/*.deb` from `ports.ubuntu.com/ubuntu-ports`, pool path resolved
  from the `noble`/`noble-updates` `binary-armhf` Packages indexes, sha256 from
  `build/inputs/mdns-packages.lock.json`;
- `toolchains/sources/{musl-1.2.5.tar.gz,busybox-1.37.0.tar.bz2,libsodium-1.0.18.tar.gz,
  mbedtls-3.6.7.tar.bz2,opus/{libogg-1.3.5,opus-1.4,opusfile-0.12}.tar.gz}` with the
  hashes from the component `SOURCE.lock` files and `build/inputs/public-inputs.json`;
- `toolchains/sources/aosp-system-core` (`platform/system/core`
  `4f247d753a8865cd16292ff0b720b72c28049786`, matching `adbd/SOURCE.lock`).

Run: `python3 experiments/phase-06/hw-20261121/step37-rekey/stage_inputs.py`.

The musl cross toolchain is rebuilt by `experiments/phase-05/build_components.sh toolchain`
under `bwrap` with the recorded host workarounds (GCC 16 gets `-std=gnu11`/`-std=gnu++14`,
a `/usr/lib` shim supplies the Debian multiarch paths, and
`toolchains/bin/curl` rewrites `ftp.gnu.org/gnu` to `mirrors.kernel.org/gnu`). Log:
`step37-rekey/toolchain-build.log`.

Still to stage/produce manually because no script records them:

- `toolchains/mbedtls-build-venv`: CPython 3.11 venv with `jinja2==3.1.6`,
  `jsonschema==4.25.1` (README of `mt8163-arm32/mbedtls`).
- `toolchains/kernel-uapi/include`: `export_uapi_arm.sh` (`make ARCH=arm headers` from
  `repos/LibreEcho-Linux` 6.1.178, as `build-release.yml` "Export Linux UAPI headers" does).
- `host-tools/root/usr/bin/dpkg-deb`: the Arch `dpkg` package's binary plus its shared
  libraries (the mDNS builder needs it; it is not installed on this host).
- `host-tools/qemu/usr/bin/qemu-arm-static`: Arch `qemu-user-static` 11.1.3.

## Status 2026-11-22 (step37-rekey, in progress)

- Input staging: `stage_inputs.py armhf mdns` PASSES (`stage-inputs6.log`, 30 armhf +
  43 mdns debs). Two upstream rotations needed fallbacks that are now in the script:
  cached-hash short-circuit for `libapparmor1 4.0.1really…24.04.7` and a Launchpad
  `+files` fallback for `libaudit-common 1:3.1.2-2.1build1.1`. All 7 musl-cross-make
  source tarballs were pre-seeded from `hashes/*.sha1` (`/tmp/toolchain-sources`, all match).
- Toolchain: `build_components.sh build_toolchain`'s bwrap /usr/lib shim breaks on this
  Arch host (`make: /bin/sh: No such file or directory`, then `sleep` 127). Replaced by
  `build-public-toolchain-host.sh` (product script with the Debian multiarch lib copy
  redirected to `/usr/lib`, PRESEED injection point for the tarballs). Run:
  `TC=$PWD/artifacts/phase-05/toolchains; PATH=$TC/bin:$PATH PRESEED=/tmp/toolchain-sources
  RUNNER_TEMP=$TC/runner-tmp JOBS=12 CC='gcc -std=gnu11' CXX='g++ -std=gnu++14'
  bash experiments/phase-06/hw-20261121/step37-rekey/build-public-toolchain-host.sh $TC/musl`
  (log `toolchain-host-build.log`; needs `experiments/phase-06/hw-20261121/inputs` symlink
  to `repos/LibreEcho/build/inputs`).
- `build_components.sh armhf-toolchain` started (`armhf-stage.log`) from the 30 staged debs.

## Build order that remains

1. `build_components.sh` targets `musl-loader busybox libsodium bootctl update-verify adbd mdns`;
   compare each output sha256 with `experiments/phase-05/components.md`.
2. Reconstruct `artifacts/phase-05/ota/lab-run/feature-catalog.json` and
   `ota/assets/*` from the sealed generation tree in
   `artifacts/phase-06/ota-step35-als/generations/txn-b0a9e76b738c1b4d1b64ae8a/features/`
   (bytes are the same payloads and manifests; the catalog's paths name
   `artifacts/phase-05/ota/assets/libreecho-radar-puffin-*` files, whose sha256 and sizes
   must match the catalog).
3. Build the step-37 UI bundle from `repos/LibreEcho-UI` `f43dadef8d6616812c53b38b1e3690491a1cacce`
   (clean tree, source diff identity `e3b0c442…`), into
   `artifacts/phase-06/components-step37-v0228/ui-bundle` (copy of the Phase 6
   `build_components.sh` with `COMP` repointed so the shared `components/` tree is untouched).
4. `experiments/phase-06/build_images.sh --output-dir artifacts/phase-06/images-step37-v0228`
   with `KERNEL_DIR=artifacts/phase-06/kernel-step36-thermal`
   (`Image f444f4d0…`, built from `LibreEcho-Linux-618` `8cb65710c72f`) and
   `UI_BUNDLE_DIR=…components-step37-v0228/ui-bundle/bundle`, `UI_COMMIT=f43dadef8d66…`,
   `UI_DIFF_SHA256=e3b0c442…`.
5. Sign v0.2.28 from the step-37 v2 image with `experiments/phase-05/ota/make_lab_ota.py`
   (same catalog, dev channel, production, new key) into
   `artifacts/phase-06/ota-step37-v0228/`.
6. Verify: boot ramdisk `ota-public-key.hex` equals the new key; new-key signature PASS and
   old-key `25be6d6b…` FAIL; boot `Image` hash equals `f444f4d0…`; DTB decompile shows the
   board-thermal trip points; micd binary hash comes from UI `f43dade`; boot.img is 16 MiB
   with `ANDROID!` magic; record `boot.img` sha256 and the OTA transaction id.

## 2026-11-22 rerun (RebuildRekey2)

Race found: two `build_components.sh toolchain` runs and two `stage_inputs.py` runs were
writing the same trees. All were killed, `RebuildRekey` stood down, and a single-owner
pipeline was installed (`build_toolchain_locked.sh` / `run_toolchain_host.sh`, both guarded
by `flock /tmp/libreecho-toolchain.lock`; `run_step37.sh` waits on the same lock).

Input staging complete and hash-checked (`stage_inputs.py`, logs `stage-inputs*.log`):

- `toolchains/armhf-archives/`: 27/27 debs at lock sha256; `armhf-root` staged (39 tools,
  `armhf-stage.log`).
- `components/mdns-packages/`: 43/43 debs at lock sha256. Two pinned versions had left
  `ports.ubuntu.com`: `libapparmor1_…24.04.7` and `libaudit-common_…build1.1` came from
  `https://launchpad.net/ubuntu/+archive/primary/+files/` (pool file name without epoch);
  the cached-hash short-circuit and Launchpad fallback are in `stage_inputs.py`.
- `toolchains/sources/`: all archives plus `aosp-system-core` `4f247d75…`, sha256-checked.
- `toolchains/kernel-uapi/include`: 942 ARM32 headers from `repos/LibreEcho-Linux` 6.1.178
  via `export_uapi_arm.sh` (log `kernel-uapi-arm.log`). A first export used `ARCH=arm64`;
  adbd then failed on the arm64 `asm/sigcontext.h` (`__uint128_t vregs`).
- `toolchains/mbedtls-build-venv`: CPython 3.11.18, `jinja2 3.1.6`, `jsonschema 4.25.1`.
- `host-tools/root/usr/bin/dpkg-deb`: Arch `dpkg 1.23.11-1` (package sig verified with
  `pacman-key`, "Good signature from Carl Smedstad"); shared libs resolve on host.
- `host-tools/qemu/usr/bin/qemu-arm-static`: Arch `qemu-user-static 11.1.3-1` (sig verified,
  "David Runge"), `qemu-arm version 11.1.3`.
- `ota/assets/`: all eight feature files, each sha256 equal to the
  `features-airplay2-latency/feature-catalog.json` entry.

Toolchain: the phase-05 `build_components.sh toolchain` bwrap `/usr/lib` shim fails on this
Arch host (`make: /bin/sh: No such file or directory` in children). The product script ran
through `build-public-toolchain-host.sh` (pin, hashes, SONAME patch and hygiene steps
unchanged; only the Debian multiarch lib-copy paths point at `/usr/lib` and `PRESEED` is
honoured), wrapped by `run_toolchain_host.sh`; log `toolchain-host-build.log`.

Pipeline: `run_step37.sh` (components + hash compare -> UI `f43dade` ->
`images-step37-v0228` -> `ota-step37-v0228`), then `verify_step37.sh`.

## Result 2026-11-22 (host; device untouched except read-only preflight)

- Components: all seven byte-identical to `experiments/phase-05/components.md`
  (`hash-compare.txt`: musl-loader, busybox, libsodium, bootctl, update-verify, adbd, mdns).
- Images: `artifacts/phase-06/images-step37-v0228`, `lidar_recovery_image_contract=PASS`
  for v2 (`image_profile=ota service_profile=production`, `images-step37.log`).
  `boot-lidar-v2.img` sha256 `a7b266b74af89ae203d35b8460866ebb6d654d64742089ad5a4bbb0b838f82dc`.
- OTA: `artifacts/phase-06/ota-step37-v0228`, transaction `txn-bac8cf84d19b53cb0c24cdc4`,
  bundle sha256 `54d0dc6f…`.
- `verify_step37.sh` rc=0 (`verify-step37.log`): 16 MiB `ANDROID!`; ramdisk key = new key;
  packed Image = step-36 thermal `f444f4d0…`; 19 appended DTBs, one with board-thermal;
  manifest signature PASS with new key, FAIL with old `25be6d6b…`. The kernel check first
  failed because it ignored the 512-byte MediaTek `KERNEL` header; fixed in the script.
- Versus v0.2.27 (`images-step35-als/boot-lidar-v2.img`): same 19-DTB layout; only the Image
  and the Lidar DTB differ. That DTB equals the step-36 DTB plus the builder's
  `/chosen linux,initrd-start/end` (end − start = ramdisk size 5764464).
- micd: ramdisk `usr/local/sbin/libreecho-micd` `53b0c710…` = UI bundle built from
  `f43dadef8d66` with empty source diff (`ui-manifest.txt` `source_commit`).
- Device preflight (`install_slot_a.sh preflight`, read-only, `hw/`): running slot b
  confirmed, p10 `boot_a` 32768 sectors, no pending record; slot b `3e71c0bc…`, slot a
  before `bbe29a43…`. The leftover `restart-record` is evidence only
  (`libreecho-init:3651-3655`); boot decisions read `update/state` (`installed`).

## Hardware 2026-11-22: slot a bootstrap (owner-approved write, activate, reboot, confirm)

- `install_slot_a.sh write`: device hash and p10 readback `a7b266b7…`; slot b untouched.
  `activate`: slot a prio 15 tries 3; slot b prio 14 success 1. `reboot`: slot a booted in
  ~30 s (boot_id `1a3ea80f…`); device key `42a501c3…` (logs `hw/`).
- Slot a did not self-confirm: boot-health `mode=first-boot state=skipped
  last_check=first-install-transaction-invalid`. A stale `first-install.pending`
  (`slot=b boot_sha256=7e73d1b8…`, mtime 1970, never cleared by the earlier first install)
  failed the slot/hash match at `libreecho-init:3110-3117`. Out-of-scope platform issue: a
  stale record blocks every later first-boot confirm.
- Manual probes (read-only, 3 rounds): `/data` mounted, adb TCP, `libreecho-web.init status`
  rc 0; board-thermal 5 trip points; no oops/panic; agentd/sttd/ttsd stopped as on v0.2.27.
- Owner chose manual confirm: `libreecho-bootctl confirm a` rc 0 (slot a success 1, slot b
  success 1), stale record removed (copy `hw/first-install.pending.stale`, sha256 `6f4d34a6…`).
- `install_slot_a.sh reboot` now exits nonzero when slot a does not confirm.

## Hardware 2026-11-22: signed v0.2.28 OTA to slot b (owner-approved; logs `hw-ota/`)

- `install_ota.sh`: `libreecho-generation verify` rc 0, `signature=PASS` with the device's new
  key, `libreecho-update install` rc 0 (slot b), reboot, confirmed by init in OTA mode at
  11:37 (`mode=ota state=confirmed`). `generation` = `current` = `txn-bac8cf84…`.
- Slots: b prio 15 success 1 (running), a prio 14 success 1; both hold `a7b266b7…`, new key.
- Fixes on hardware (`fix-checks.log`): board-thermal trips 55 hot, 57/58/59 passive,
  60 critical, cooling `cpufreq-cpu0`; no "No trip points"; micd phantom-stop count 0 with a
  real `calibrated mono microphone stream started`; two micd processes as designed; ALS lux
  2884.
- `ota_transaction_state=rollback` in status is the retained `rolled-back` history marker
  (`libreecho-update:470-473`), present before step 37; not this install.
- `install_ota.sh` logs "adb back on slot a" before the device goes down (reconnect races
  the reboot, inherited from step 36); the confirmed-state poll is the real gate.
