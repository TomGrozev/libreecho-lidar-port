# Step 33: MT8163 → Lidar feature parity (host-only)

Scope: what an MT8163 LibreEcho image enables that the Lidar image does not. Host-only;
no device access. MT8163 reference = LibreEcho-Linux 6.1 target (its
`arch/arm/configs/mt8163_arm32_defconfig` fragment plus the kernel defaults), Lidar =
`artifacts/phase-06/kernel/config` and the Phase 6 ramdisks/OTA generations.

Note: `repos/LibreEcho-Platform/arch/arm/configs/mt8163_arm32_defconfig` is a different,
legacy 3.18 Android vendor config (CONFIG_ANDROID_BINDER_IPC, CONFIG_ASHMEM, CONFIG_MTK_RTC).
It is not the MT8163 LibreEcho 6.1 image config and was only used as a cross-check.

## Result

| Feature | Result | Evidence | Root cause or fix proposal |
|---|---|---|---|
| Init services/daemons started | PASS (shared graph) | `repos/LibreEcho-Platform/tools/mt8163-arm32/initramfs/libreecho-init:2382-2447` builds one service list for every target; `tools/mt8167-arm64/README.md:5-8` states the userspace/overlay is shared; v2 ramdisk has all 19 init scripts | No target split. Wake word is gated only by `/etc/libreecho/audio-profile` (`libreecho-init:2311-2313, 2430-2443`), which Lidar ships from v0.2.21 |
| Feature payloads (airplay2, tts, wakeword, stt, assistant) | PASS | `artifacts/phase-05/ota/lab-run/feature-catalog.json:3-37` vs `artifacts/phase-06/ota/lab-v2/generations/txn-e0d28e65c8a01411e24b3e26/target.manifest` `feature_ids=`; `jq -r '.files|keys[]'` diff empty for tts/wakeword/stt/assistant; airplay2 member set identical, only `usr/local/sbin/libreecho-audio-engine` hash differs (Lidar rebuild, 90544 vs 79592 bytes) | None. Payload contents are the same five features |
| Target files / image profiles | PASS | `tools/mt8167-arm64/libreecho_platform_targets.py:63-100` (audio `target_id=lidar`, flat codec, 8-ch capture); `artifacts/phase-06/images/boot-lidar-v2.manifest.json` `service_profile=production`, `feature_policy=preserve`, `image_profile=ota`; `image-profile`/`feature-policy` in the v2 ramdisk | None. Dev images are diagnostic/preserve by design; OTA images match the MT8163 production/preserve policy |
| RTC wall clock / timer persistence | FAIL (product gap) | MT8163: `repos/LibreEcho-Linux/arch/arm/configs/mt8163_arm32_defconfig:134-135` `CONFIG_RTC_CLASS=y`, `CONFIG_RTC_DRV_MT6397=y`; Lidar: `artifacts/phase-06/kernel/config:3187` `# CONFIG_RTC_CLASS is not set`; live: `experiments/phase-06/hw-20261121/step29-features/result.md:86,98-99` `rtc_available=0`, `RTC persistence failed` | Hardware N/A for the MT8163 PMIC RTC: `repos/LibreEcho-Linux-618/arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:105,630` says the board has no PMIC, and the Lidar DTS/DTB has no RTC node. Port decision needed: `repos/LibreEcho-UI/src/adapter/timed.c:283-321` should persist the last valid epoch in userdata and treat RTC as optional, so timers survive reboot without WAN |
| USB gadget RNDIS | N/A (no consumer) | MT8163: `mt8163_arm32_defconfig:121` `CONFIG_USB_CONFIGFS_RNDIS=y`; Lidar: `artifacts/phase-06/kernel/config:3063` `# CONFIG_USB_CONFIGFS_RNDIS is not set` | No LibreEcho surface uses RNDIS; the Lidar port is peripheral-only and setup/OTA run over Wi-Fi or adbd (`libreecho-lidar.dts:491-493`). No fix |
| Bluetooth RFCOMM / BNEP / HIDP | N/A (capability only) | MT8163: `mt8163_arm32_defconfig:44-49`; Lidar: `artifacts/phase-06/kernel/config:1043` and neighbours `# CONFIG_BT_RFCOMM/BNEP/HIDP is not set` | `repos/LibreEcho-UI/src/adapter/btd.c:1740` only reports these as capability booleans; no UI/API feature uses them. A2DP/AVRCP are L2CAP and already PASS. Upstream optional, no LTE |
| LED timer/trigger framework | N/A | MT8163: `mt8163_arm32_defconfig:132-133` `CONFIG_LEDS_TRIGGERS=y`, `CONFIG_LEDS_TRIGGER_TIMER=y`; Lidar: `artifacts/phase-06/kernel/config:3179` `# CONFIG_LEDS_TRIGGERS is not set` | `repos/LibreEcho-UI/src/adapter/ledd.c:271-276`: the legacy timer/transient trigger path is disabled and only the v2 director/render path owns LEDs. Night/sleep/idle already PASS (`step29-features/result.md:74`), so no fix |
| LSM6DSX accelerometer | N/A (hardware) | MT8163: `mt8163_arm32_defconfig:141` `CONFIG_IIO_ST_LSM6DSX=y`; Lidar: `artifacts/phase-06/kernel/config:3814` not set | No LibreEcho API or daemon consumes an accelerometer; the only sensor API is `/api/v1/light` (TSL2540). MT8163-only hardware |
| AMS ALS / TSL2584 autozero | N/A (hardware, superseded) | MT8163: `mt8163_arm32_defconfig:143,145` `CONFIG_AMZN_AMS_ALS=y`, `CONFIG_ALS_TSL2584_AUTOZERO=y`; Lidar: `artifacts/phase-06/kernel/config:3887` `CONFIG_SENSORS_TSL2540=y`, AMS/2584 not set | Lidar uses the TSL2540 vendor driver and the `/api/v1/light` consumer PASSes (`step29-features/result.md:89`). Different sensor, no gap |
| TMP103 thermistor / BQ24190 charger | N/A (hardware) | MT8163: `mt8163_arm32_defconfig:91-92`; Lidar config does not set either | Lidar thermal telemetry uses SoC thermal zones; no charger/battery. No LibreEcho feature depends on these drivers by name |
| MT8163 audio codec / SPI audio | N/A (hardware) | MT8163: `mt8163_arm32_defconfig:104-106` `CONFIG_SND_SOC_MT8163`, `SND_SOC_AMZN_MT8163_SPI_AUDIO`; Lidar uses `SND_SOC_MT8516=y`, AIC32x4 (`artifacts/phase-06/kernel/config`, audio PASS step 16) | Different SoC audio path. Playback, mics, cues, AirPlay all PASS on Lidar |
| MUSB PIO-only / UAC2 gadget | N/A (no consumer) | MT8163: `mt8163_arm32_defconfig:115` `CONFIG_MUSB_PIO_ONLY=y`; Lidar: not set; both have `# CONFIG_USB_CONFIGFS_F_UAC2 is not set` (`artifacts/phase-06/kernel/config:3070`) | MT8163 image does not enable UAC2 either; no LibreEcho USB-audio surface exists in `repos/LibreEcho-UI` or the initramfs. Reference UAC2 work is future hardware capability, not a shipped feature |
| IDME identity | PASS (ported) | MT8163: `mt8163_arm32_defconfig:65` `CONFIG_IDME=y`; Lidar has no IDME and uses `/etc/libreecho/target` (`libreecho-init:338-344`) | esphomed MAC fallback to `wlan0` was the port fix, shipped in v0.2.23 (`step29-features/result.md:74` re-sweep, HA PASS) |
| GPT-Live (`libreecho-lived`) | N/A (upstream, both targets) | `repos/LibreEcho-Platform/tools/mt8163-arm32/ui/build_ui_bundle.sh:447-461,503-509` stages daemons but never `libreecho-lived`; Lidar v2 ramdisk `/usr/local/sbin` has no `libreecho-lived` | Not an MT8163 feature. `libreecho-lived` exists in the UI build but no product image ships it. Recorded as an upstream/product gap, not a Lidar gap |
| USB storage (VFAT/FUSE) | N/A (hardware) | MT8163 6.1 fragment sets neither `CONFIG_VFAT_FS` nor `CONFIG_FUSE_FS`; Lidar also clears both (`artifacts/phase-06/kernel/config:4145,4164`) and its port is peripheral-only (`libreecho-lidar.dts:491-493`) | No MT8163-only feature. USB storage is blocked by Lidar hardware, as already recorded in `step29-features/result.md` |
| TSL2540 light sensor consumer | PASS (Lidar-only hardware, has consumer) | `artifacts/phase-06/kernel/config:3887`; `/api/v1/light` (`repos/LibreEcho-UI/src/api.c:2308`) backed by sysfs discovery (`src/backend_linux.c:735-775`); device GET 200 (`step29-features/result.md:89`) | None |
| EFR32 Zigbee/Thread consumer | N/A (no LibreEcho consumer yet) | Only Lidar code is the ttyS2/gpiochip devnode setup (`libreecho-init:639-699`); no `efr32`/`openthread`/`spinel` consumer in `repos/LibreEcho-UI` or `repos/LibreEcho-Platform/tools` | Permanent Thread border-router service is explicitly Phase 7 (`PLAN.md:653-662`). Nothing MT8163 has that Lidar lacks |

## Commands actually run

- Extracted the Lidar dev/v2 ramdisks from `artifacts/phase-06/images/*.ramdisk.cpio.xz` and
  compared `/etc/libreecho` profiles and `/usr/local/sbin`.
- Compared feature manifests with
  `diff <(jq -r '.files|keys[]' MT.json) <(jq -r '.files|keys[]' LIDAR.json)` and
  `diff <(jq -S '.files' ...)` for airplay2/tts/wakeword/stt/assistant.
- Parsed both kernel configs in Python and compared the user-feature option families listed
  above (`RTC`, `USB_CONFIGFS`, `BT_*`, `LEDS_*`, `IIO`, `SND_SOC`, `INPUT`, `FUSE`, `VFAT`).
- Read the MT8167/6.18 RTC driver match table (`drivers/rtc/rtc-mt6397.c` supports
  `mediatek,mt6357-rtc`), but the Lidar DTS has no PMIC/rtc node.

No device commands were issued and no files outside this evidence directory were written.
