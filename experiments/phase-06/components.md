# Phase 6 components and images

Host builds, 2026-11-21. Paths are relative to the workspace root. Kernel inputs are Main's
`artifacts/phase-06/kernel/` outputs.

## Components

`experiments/phase-06/build_components.sh <target>` rebuilds only the component whose source
changed and asserts the hashes of the phase-05 components it reuses. Logs are in
`artifacts/phase-06/components/logs/`.

| Target | Output | sha256 |
|---|---|---|
| `ui` | `artifacts/phase-06/components/ui-bundle/bundle/share/libreecho/ui-manifest.txt` | `72095d61ddafe0373abb9b8f394e2438e50dd6ac8767246ac88d256229ffc2a4` |
| `reuse-check` | phase-05 `musl/ld-musl-armhf.so.1`, `busybox/busybox`, `adbd/adbd`, `ota-control/*`, `mdns-runtime` | match the phase-05 pins |

UI pins: commit `c09551f3618bc59401a71c9052f7845384ba9b40` (`btd: use the mainline
btmtksdio controller on Lidar`), source diff identity
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (clean checkout), built
from `repos/LibreEcho-UI` instead of the phase-05 source copy. The OTA helpers were rebuilt
from current `feature/lidar-support` and reproduced the phase-05 hashes, so the phase-05
copies are reused.

Wi-Fi firmware staged from the host packages:
`artifacts/phase-06/firmware/mt7668pr2h.bin`
(`465ed634c61b46b34bb21240736f33d3d347fefec7cbfbd1cb6e63334aec4cc9`, 170,990 bytes) and
`artifacts/phase-06/firmware/LICENCE.mediatek`
(`a90d3f66704d85889945fec5525ea77622549da83aced1aac99828383f8f1805`, 561 bytes).

Kernel: `artifacts/phase-06/kernel/Image`
(`7ee8b41b2a1297181ea9b1b1c525766973291ccec57fa68156ce6d6c21ca60e6`) and `config`
(`ee759d7a5d437c9042a0ab1cc90279997bb701b7777da042a010d1db4a66c4d1`), built from
`repos/LibreEcho-Linux-618` `fix/lidar-port-identity` `3f2711ac4690` (renames the privacy
node to `amz_privacy` so every reader uses
`/sys/devices/platform/amz_privacy/privacy_state`; earlier builds were from
`feature/lidar-6.18` `d70e787ff949`: real MUSB rx_kick, `REGCACHE_MAPLE` for the AIC32x4
page selector). `libreecho-lidar.dtb`
(`e8727c88e2240dc77a6b247f54775d1de88acb80707e02c3ba97866337d47029`, 22,788 bytes) is the
rebuilt DTB with the `amz_privacy` rename.
The gzip kernel is 5,824,148 bytes and the 19 stock DTBs plus the Lidar DTB take 1,027,848.

## Images

`experiments/phase-06/build_images.sh` builds and verifies three images in
`artifacts/phase-06/images/` from the stock `boot_a` readback
(`dumps/20261110-lidar-readback/boot_a.bin`), the Phase 6 kernel, the new UI bundle and the
staged Wi-Fi firmware. Each carries `libreecho.lab=p6-<name>` on its command line.

| Image | Profiles | sha256 | xz ramdisk | Margin to 16 MiB |
|---|---|---|---|---|
| `boot-lidar-dev.img` | development, diagnostic, UI | `90ff0c352c2f99f430557c92a3683db0b5b5cfbda7e4a3155568929c5aa58b4d` | 3,275,208 | 6,645,760 |
| `boot-lidar-v1.img` | ota, production, UI, mDNS | `5ededc7be2ac55c027ca7fdb318643c329eae17034b4bbe0d1e4ae6b659f02af` | 5,761,592 | 4,159,488 |
| `boot-lidar-v2.img` | ota, production, UI, mDNS | `43e2de611766ef2fe90f45be1770c87640d84960bb09f242ce264870f68f9c56` | 5,761,592 | 4,159,488 |

The 2026-11-21 rebuild carries the WLAN fix above plus the MT8163 pinned tinyalsa
tools (`tinyplay` `e31e4979…`, `tinycap` `eabe84ef…`, `tinymix` `7310a2f7…`, from
`tools/mt8163-arm32/audio-tools/build_audio_tools.sh`) staged at `/sbin`, because
`libreecho-micd` runs `--capture-bin /sbin/tinycap`. The verifier pins each with
`--expected-tiny*-sha256`.

The 2026-11-21 rebuild adds the static ARM32 `wpa_supplicant` 2.10
(`artifacts/phase-06/components/wpa-supplicant/wpa_supplicant`, sha256
`43b2933a79dfdf0a000a21c4ccafc7333676e94b85e58033fdf33848146d8d30`, built by
`tools/mt8163-arm32/wpa-supplicant/build_wpa_supplicant.sh` from the pinned wpa and libnl
archives). The builder stages it at `/sbin/wpa_supplicant` and the verifier pins it with
`--expected-wpa-supplicant-sha256`; `udhcpc` is the BusyBox applet.

The UI bundle in all three images carries LibreEcho-UI `c09551f3618b`: `btd` selects the
mainline `btmtksdio` transport from the image target file (`target_id=lidar`) instead of the
`/dev/stpwmt` WMT node that `libreecho-init` creates on every target, so Lidar powers
`hci0` directly and MT8163 keeps its WMT path.

## Current pins (updated 2026-11-22)

The pins above record the session's first builds. Later lab OTAs rebuilt from newer branch
heads:

| Component | Branch / source | Pin |
|---|---|---|
| LibreEcho-UI | `repos/LibreEcho-UI` `fix/lidar-port-identity` | `e564bf569775` (`fix(esphomed): keep a full period queued and clear the wake ring`, on top of `a9cea2e` streaming playback, `4b3c17d` two waked threads and `371950a` micd PGA) |
| Kernel | `repos/LibreEcho-Linux-618` `fix/lidar-port-identity` | `77931cc96944` (`Image` `8acf87fe…`, config `0ade3894…`, DTB `e8727c88…`; `CONFIG_ARM_MEDIATEK_CPUFREQ=y`) |
| Platform (EFR32 nodes) | `repos/LibreEcho-Platform` `fix/lidar-efr32-nodes` | `bf073fb39` (`fix(lidar): create ttyS2 and gpiochip nodes at boot`) |

All three are 16 MiB, use the dev update channel, the `preserve` feature policy and the lab
OTA key. The Lidar verifier printed `lidar_recovery_image_contract=PASS` for each, and the
manifest carries the rendered Lidar audio profile, the MT7668 patch and its licence.

## OTA bundles

Built with `experiments/phase-05/ota/make_lab_ota.py` via `experiments/phase-06/ota/build_ota.sh`
(release `lidar-lab-v0.2.N`, version `0.2.N`, dev channel, production, lab key, catalog
`artifacts/phase-05/ota/lab-run/feature-catalog.json`):

| Bundle | Boot image | Transaction | sha256 |
|---|---|---|---|
| `artifacts/phase-06/ota/lab-v1/lidar-lab-v0.2.13.ota.tar` | v1 | `txn-2c8008b7d20091a1908cc7c9` | `146ea38684780c3a77c2abdb3a847c2316a2aa1f09e8dce5af4d49aadd16024c` |
| `artifacts/phase-06/ota/lab-v2/lidar-lab-v0.2.14.ota.tar` | v2 | `txn-e0d28e65c8a01411e24b3e26` | `2413ea85638d14dc76a3d2d7eacaf2e4fa5453d198a11981bcbfa2bfdf57504a` |
| `artifacts/phase-06/ota-step31-mic/lidar-lab-v0.2.24.ota.tar` | v0.2.24 (micd PGA fix) | `txn-dee60c3fa20042fc6d595775` | `2a05b2fa544382cf7be11c38206a780537db9b5d2f5ee2054c73626216896425` |
| `artifacts/phase-06/ota-step33-latency/lidar-lab-v0.2.25.ota.tar` | v0.2.25 (cpufreq kernel, two wake threads, held audio output) | `txn-92d3a65dbbc8ff12b9a722f5` | `1ea37bbddf52aa29665777fbc636e460fc0899dceb3afe0d3cb2f7feeb8f1a7c` |
| `artifacts/phase-06/ota-step33-followup/lidar-lab-v0.2.26.ota.tar` | v0.2.26 (esphomed full-period queue and wake-ring clear, v0.2.25 kernel and airplay2 payload) | `txn-bad7b618061367f54b2daf6d` | `7d28f40b9141b5a2c4955977a81262a65ad9b4dfe7e216e72549e5c9b6bc26c3` |

The 0.2.13 and 0.2.14 bundles are 16,793,600 bytes; each has its generation tree next to it.
Not yet run on hardware.

The v0.2.24 bundle above is the last of the session's later lab OTAs (v0.2.23 came from
`artifacts/phase-06/ota-step30-identity/`). v0.2.24 was installed and confirmed on the
device on 2026-11-22, slot a, `txn-dee60c3fa20042fc6d595775`
(`experiments/phase-06/hw-20261121/step31-mic/events.log`); the "not yet run" note covers
only the two 0.2.13/0.2.14 rows above it.

v0.2.25 was installed and confirmed on the device on 2026-11-22, slot b,
`txn-92d3a65dbbc8ff12b9a722f5` (`experiments/phase-06/hw-20261121/step33-latency-fix/events.log`).

v0.2.26 was built on 2026-11-22 from the same kernel and airplay2 payload with the
`e564bf5` UI bundle and was not installed
(`experiments/phase-06/hw-20261121/step33-latency-fix/followup.md`).
