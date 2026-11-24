# Lab OTA v0.2.37

Host-only build: no device access, no install, no GBL in the bundle, no Thread
border-agent commits. Device steps at the bottom are **unverified** (not run).

Status: **complete on the host**. `--verify-only` exits 0 with every check PASS.

v0.2.37 carries both lines of work that were split across the installed v0.2.36
and the host-only v0.2.35 rebuild: the 47feddd6 kernel (thermal zone, no
`uart-has-rtscts`) and the loudness settings (`hp_driver_gain=6`,
`lo_driver_gain=6`), now committed rather than carried as working-tree edits.

## Inputs vs v0.2.36

| Input | v0.2.36 (installed) | v0.2.37 |
|---|---|---|
| Kernel source | `8cb65710` (`kernel-step36-thermal`) | `47feddd6b58f7d3cbc22a50940ecc6a44c3af833` |
| Kernel Image | `f444f4d0…` | `272090a9c38fce616f15bd1a68bf2aee3ada763e0cf93a6d8e01b526b40089d2` |
| Kernel DTB | `a8e19573…` (had `uart-has-rtscts`) | `0e9cc4ffd16b6ece79d5c698a15bb35aa5e252c73276f9525f9e73f64154913a` |
| Platform | `0a4d7a6e0` + uncommitted loudness edits | `7011650f9b246e27709a3c2298433f442d281426` (clean detached worktree) |
| Loudness change | uncommitted in the working tree | committed as `671a2caf9` (on `02ef8ad6a`) |
| UI | `470eb36`, bundle reused from `components-470eb36` | `29a7a0ae00e955fea4bca09cb2edd640f76e77dc`, bundle built clean from a worktree |
| UI wake-word selection | absent | `7f5c29a` (in `29a7a0a`) |
| Wakeword feature | older phase-05 asset | prebuilt qemu-verified `3d199f8b…` payload, waked `d11ac4ec…` |
| Audio engine | `951100e8…` (dirty tree) | `951100e8…` (same bytes, now from a committed tree) |

`7011650f9` is `671a2caf9` plus the reduced-ORT LayerNorm operator list; both
`02ef8ad6a` and `671a2caf9` are ancestors of it (`git merge-base
--is-ancestor`, checked in the build and in the proof). The Platform build
worktree is detached at `7011650f9`, so uncommitted peer work in
`private/forks/LibreEcho-Platform` (the `tools/mt8163-arm32/otbr/` edits) is
excluded from the bundle.

## Provenance of the run

The build was executed by a separate omp session with a hand build script that has
since been deleted (`tools/lab-build.py` replaces it). This note's author did not
start that process and did not modify its outputs; the performed checks are the
`--verify-only` pass over its artifacts. The kernel hashes were confirmed
independently before and after the build.

## Verification

The `--verify-only` replay exited 0 with 42 PASS lines. Log:
`private/artifacts/phase-07/ota-v0.2.37/verify-v0237.log`.

The script's guards refuse unless the kernel Image/DTB match `272090a9…` /
`0e9cc4ff…`, the Platform worktree is clean at `7011650f9`, the UI worktree is
clean at `29a7a0a`, and the wakeword payload/manifest/waked hashes match.

## Artifacts and sha256

| File | sha256 |
|---|---|
| `kernel/Image` (input) | `272090a9c38fce616f15bd1a68bf2aee3ada763e0cf93a6d8e01b526b40089d2` |
| `kernel/libreecho-lidar.dtb` (input) | `0e9cc4ffd16b6ece79d5c698a15bb35aa5e252c73276f9525f9e73f64154913a` |
| `engine/libreecho-audio-engine` | `951100e8b50e2752c6cee89aae9a6f5917848b32e08e7f8fef1bb3f5d3bff1d0` |
| `libreecho-lidar-base-airplay2-63fa8db….payload.squashfs` | `63fa8dbcc9717e55ca8dc84e3aff7f440f9dd0672f255d5b1daebfe201bb48a5` |
| `libreecho-lidar-base-airplay2-63fa8db….manifest.json` | `03bb45b4e8c84903f1fa01e91e126628f6a549b4395c9b843b1ac8a1cee84363` |
| `libreecho-lidar-base-wakeword-3d199f8b….payload.squashfs` | `3d199f8b7805f4a499b380d414fdee63e0b6790f8e361dce06803eb4cba38af4` |
| `libreecho-lidar-base-wakeword-9431c19f….manifest.json` | `9431c19f3c175ae296acb40604dab5f16f883cbfc6f424ae6d55d459cd448980` |
| `images/boot-lidar-dev.img` | `d73c761839de54f8f6653b0c61481cc50b38c030f1cbfd83a56c4585c64b30d2` |
| `images/boot-lidar-v1.img` | `b0f24d8d4f8627e856fd5dd85da290d65d7c36224c3d32dc0def569e12fefe39` |
| `images/boot-lidar-v2.img` | `d834f11b248277c574a51bea83b042071ef2e371af0d026518aefd3a5bdc28df` |
| `images/boot-lidar-v2.ramdisk.cpio.xz` | `525765809c78d86609790c88d6227d9d5a8be9f103c498f078a23fe2eae95f4c` |
| `feature-catalog.json` | `3c2bd96f396386b6961527182dc270be3b040954642bcff51db9e102f5aee238` |
| `ota/generations/txn-e656c1b5120f7cd075b1f0a4/target.manifest` | see `SHA256SUMS` |
| `ota/lidar-lab-v0.2.37.ota.tar` | `746d53641780d055e1df85cbd69fa4b4479e27b41a709290c9d6f17cffd5981b` |
| `build-info.json` | `cc66fdfebb4fed3e087855d98034590187930dbe0424c9b96ab38f2502a4aee3` |
| `SHA256SUMS` (deliverable tree) | `993386be03266891961b4a6d509bd93a6b17015938ab5b1a94ae2daf74fba99f` |

OTA path: `private/artifacts/phase-07/ota-v0.2.37/ota/lidar-lab-v0.2.37.ota.tar`.

`SHA256SUMS` covers `images/*`, the OTA tar and the feature payloads;
`build-info.json` covers the deliverable tree and skips the `src/`,
`components/`, `deps/` and `ramdisk-check/` build inputs.

UI in the image: `source_commit=29a7a0ae…`,
`source_diff_sha256=e3b0c442…b855` (clean tree, empty diff), bundle manifest
`237fa44a4715146c597d2b630672e7b2d96bb0fe85dd8184c63aad6878c92467`.

## Checks (all run, all PASS)

| Check | Command | Result |
|---|---|---|
| Pins | `git -C private/forks/LibreEcho-Platform merge-base --is-ancestor {02ef8ad6a,671a2caf9} 7011650f9` | both exit 0 |
| Kernel input | `sha256sum private/artifacts/phase-07/ota-v0.2.35/kernel/{Image,libreecho-lidar.dtb}` | `272090a9…`, `0e9cc4ff…` |
| DTB contract | `python3 private/forks/LibreEcho-Platform/tools/mt8167-arm64/verify_lidar_dtb.py <dtb>` | `lidar_dtb_contract=PASS compatible=amzn,lidar-pvt …, size=24004` |
| DTB UART | `strings <dtb>` | `board-thermal` and `ti,tmp112` present; **no** `uart-has-rtscts` |
| Image inputs | `jq .inputs images/boot-lidar-v2.manifest.json` | kernel `272090a9…`, DTB `0e9cc4ff…` |
| Recovery contract | `grep -c lidar_recovery_image_contract=PASS images-build.log` | 3 (dev, v1, v2), all `status=PREPARED_NOT_FLASHED` |
| Boot image | size/magic and ramdisk unpack | 16777216 bytes, `ANDROID!`; `target_id=lidar`, lab public key, `lidar_radio_bringup`, wifi-radio and target-identity gates |
| Loudness profile | ramdisk `/etc/libreecho/audio-profile` | `lo_driver_gain=6`, `hp_driver_gain=6`, `speaker_chain=lidar` |
| UI | bundle manifest | `source_commit=29a7a0a…`, `source_diff_sha256=` empty tree, `libreecho-esphomed` matches the bundle (`aa08a214…`) |
| Engine | `unsquashfs -cat <payload> usr/local/sbin/libreecho-audio-engine \| sha256sum` | `951100e8…`, byte-identical to v0.2.36, differs from v0.2.35 |
| Sendspind | `unsquashfs -cat <payload> usr/local/sbin/libreecho-sendspind \| sha256sum` | `36572977…` (unchanged) |
| OTA signature | `qemu-arm-static libreecho-update-verify <lab-public-key> target.manifest target.manifest.sig` | new key verifies; v0.2.33 key rejected |
| Version | `grep ^version= target.manifest` | `0.2.37` (> installed `0.2.36`) |
| Release components | `python3 private/forks/LibreEcho/tools/check-release-components.py --target lidar --artifacts <ota> --artifacts <boot-lidar-v2.img>` | `donor_gate=cleared artifact_count=2`, `component_gate=cleared component_count=21`, no GBL/EFR32 firmware |
| Wakeword | OTA feature manifest and `libreecho-waked` | payload `3d199f8b…`, manifest `9431c19f…`, waked `d11ac4ec…` |
| Tree | `(cd <D> && sha256sum --quiet -c SHA256SUMS)` | match |
| OTA payload | `tar -xOf lidar-lab-v0.2.37.ota.tar boot.img \| sha256sum` | `d834f11b…`, identical to `images/boot-lidar-v2.img` |

Full log: `private/artifacts/phase-07/ota-v0.2.37/verify-v0237.log` (42 PASS,
0 FAIL). Component log: `check-release-components.log`. DTB log:
`verify-lidar-dtb.log`.

## Install steps (unrun, need owner approval)

1. Push the generation and bundle over Wi-Fi adb to the inactive slot, then
   `libreecho-generation verify` and `libreecho-update install` (same sequence
   as the v0.2.36 install; its script is gone). The bundle
   writes the inactive slot and reboots; approval is required per AGENTS.md.
2. After reboot: `libreecho-bootctl status` shows `boot_state=confirmed`,
   `/proc/cmdline` names the other slot.
3. Kernel: `uname -r` is the 47feddd6 build; `ls /sys/class/thermal/` and
   `for z in /sys/class/thermal/thermal_zone*; do echo $(cat $z/type) $(cat $z/temp); done`
   shows `board-thermal` with a non-zero temperature.
4. Loudness: `/etc/libreecho/audio-profile` reads `hp_driver_gain=6` and
   `lo_driver_gain=6`; `tinymix -c 0 contents` LO/HP Driver Gain after playback
   arms the output.
5. Confirm the slot boot image readback equals `d834f11b…`
   (`dd if=/dev/mmcblk0p1x bs=4096 count=4096 | sha256sum`).
