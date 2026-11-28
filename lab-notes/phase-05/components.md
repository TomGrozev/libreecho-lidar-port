# Phase 5 components and images

Host builds from 2026-11-18, rebuilt 2026-11-19 (see the rebuild note under Images) and run
on hardware through step 6 on 2026-11-21 (`README.md` step 6, run 7: PASS). Paths are
relative to the workspace root.

## Components

`experiments/phase-05/build_components.sh <target>` builds each component from the pinned
Product sources with the Product `build/build.sh` invocations. Logs are in
`artifacts/phase-05/components/logs/`.

| Target | Output under `artifacts/phase-05/components/` | sha256 |
|---|---|---|
| `toolchain` | `../toolchains/musl` (musl-cross-make, Product script unmodified) | n/a |
| `musl-loader` | `musl/ld-musl-armhf.so.1` | `47ed5c21aca427b893859aa9ee1ca7a0ce9494f4e0e7dd6ee4136d9766f9f060` |
| `busybox` | `busybox/busybox` (304 applets) | `fed10234e996e9647d753ab5ee196d69f465ece1fe9962e401a0df7ef96cf3de` |
| `libsodium` | `libsodium/lib/libsodium.a` | `fe2407251fcc7c89300a264d73c257cb609750ef5f7a6eec36606b0d259613ff` |
| `bootctl` | `ota-control/libreecho-bootctl` | `4f19413de86355809051b316e99b6334198a5fc8ce3889b357f90fb8761b6224` |
| `update-verify` | `ota-control/libreecho-update-verify` | `bfc00578d1006f589d257a796f688f7bdd729fe4cf7bbbe2e271dc95ff557aaf` |
| `adbd` | `adbd/adbd` | `3651b39f524bd8f07f1a9b85e00ec284017b5558788a3715d8aa08132866b6e0` |
| `mdns` | `mdns-runtime/manifest.json` | `e700b693905c74b768f4a2db50430a8c7bd6303c98a3e0cd367e5f6a9195ec65` |
| `ui` | `ui-bundle/bundle/share/libreecho/ui-manifest.txt` | `1e8783e155c47e17401c84ed3989269c1209db6ad4badf7683c59fa87bf01576` |

Host differences from the Product CI runner, all inside `build_components.sh`:

- The musl toolchain build runs under bwrap with `CC="gcc -std=gnu11"` and
  `CXX="g++ -std=gnu++14"`, because host GCC 16 defaults to C23 and C++20, which the pinned
  GCC and binutils predate. A `/usr/lib` shim adds the Debian multiarch library paths the
  script copies from.
- The UI build uses wrappers in `toolchains/armhf-cc/` that pass `--sysroot` to the staged
  Debian armhf compiler. Product uses a system cross compiler with a built-in sysroot.

Checks run on the outputs:

- `qemu-arm-static busybox --list` (loader under `-L`): 304 applets, none named `busybox`.
- The ARM update verifier under qemu accepted the lab signature over a v2 `target.manifest`
  and rejected the same manifest with one appended byte (exit 1).

## Images

`experiments/phase-05/build_images.sh` builds and verifies three images in
`artifacts/phase-05/images/` from the stock `boot_a` readback
(`dumps/20261110-lidar-readback/boot_a.bin`), the Phase 5 kernel and the components above.
Each carries `libreecho.lab=<name>` on its command line so the running image is visible in
`/proc/cmdline`.

| Image | Profiles | sha256 | xz ramdisk | Margin to 16 MiB |
|---|---|---|---|---|
| `boot-lidar-dev.img` | development, diagnostic, UI | `c04feb346aace48b6326c66a1750925ea3682feafaaa18c27326b44902d9a263` | 2,897,876 | 8,247,296 |
| `boot-lidar-v1.img` | ota, production, UI, mDNS | `9da8886ca63696c5dc13f968f356f499732c072b1dec5d991df8d025737a239a` | 5,382,724 | 5,761,024 |
| `boot-lidar-v2.img` | ota, production, UI, mDNS | `7e73d1b800cfa46aee50abe6cf580f8e5927d8777801c3a2fcb0339d48f8c4b0` | 5,382,724 | 5,761,024 |

All three use the dev update channel, the `preserve` feature policy and the lab OTA key.
The gzip kernel is 4,603,904 bytes and the 19 stock DTBs plus the Lidar DTB take 1,024,374.
The Lidar verifier printed `lidar_recovery_image_contract=PASS` for each. The rebuild
from 2026-11-19 includes the MUSB `rx_kick` backport (`experiments/phase-05/hw-20261118/adb-fix.md`),
the `no_disconnect` FunctionFS mount, the UDC rebind supervisor, the UI startup
readiness backoff and the audio-profile gate: a target without
`/etc/libreecho/audio-profile` neither requires nor starts the local assistant, while
MT8163 keeps its previous service graph. The UI bundle changed, so its manifest hash
above is new, and both OTA lab bundles below embed these images.

`userdata-plain.simg` (`f82f10ffcabbfa3a6b9e0bac28454fac80833e2b467bb199256c8eb98dff6169`,
1,503,764 bytes) is an empty `LIBREECHO_DATA` filesystem. A userdata image with the v1
generation staged is 248 MB of programmed data, and the installer refuses anything above LK's
128 MiB download limit. Splitting a sparse image across downloads is untested on Kaeru, so the
lab route delivers generations over adb instead.

## OTA bundles

Built with `experiments/phase-05/ota/make_lab_ota.py` (release `lidar-lab-v0.2.N`, version
`0.2.N`, dev channel, production, lab key, catalog `artifacts/phase-05/ota/lab-run/feature-catalog.json`):

| Bundle | Boot image | Transaction |
|---|---|---|
| `artifacts/phase-05/ota/lab-v1/lidar-lab-v0.2.11.ota.tar` | v1 | `txn-65c78379f4bb2fced5b2249a` |
| `artifacts/phase-05/ota/lab-v2/lidar-lab-v0.2.12.ota.tar` | v2 | `txn-508529626fbd711fdbf6bf1c` |

`lidar-lab-v0.2.11.ota.tar` and `lidar-lab-v0.2.12.ota.tar` (16,793,600 bytes
each) are the current pair and the one step 6 run 7 used on hardware
(`hw-20261118/step6-ota-run7/`: v0.2.12 installed, booted `_b` and confirmed with
`state=installed` and `features_state=ready`). Earlier pairs (v0.2.5/v0.2.6 through
v0.2.9/v0.2.10) are the run 1 to 6 builds and stay in the directories.
Both boot images contain the `esphome_service_ready` integration-bit gate and
the `read_bcb` last-try window fix.

Known issue seen on run 7: after the successful confirm, `libreecho-update status` still
shows the stale `restart_record=1` (`reason=ota-health-confirm-failed`) and
`ota_transaction_state=rollback`, while `state=installed` and the confirmed slot are
correct. Recorded in `notes.md` under known issues.

Later (2026-11-22): the table above stops at v0.2.12 because Phase 5 closed then.
Later lab bundles (v0.2.13 up to v0.2.28) are recorded in
`../phase-06/components.md` and, for v0.2.26 to v0.2.28,
`../phase-06/hw-20261121/README.md` steps 34 to 37 (v0.2.27 and v0.2.28 in
`step35-als/` and `step37-rekey/`). The device runs v0.2.28 as of step 37.
