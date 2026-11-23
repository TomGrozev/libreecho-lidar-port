# Step 33 gap fixes: kernel/DT (KernelFixes)

Repo: `repos/LibreEcho-Linux-618`, branch `fix/lidar-port-identity`.
Base commit before edits: `77931cc969448da586fd09f38bf61c1fd3b4938e`.
Host-only; nothing was built into or run on a device.

## Changes

### 1. TSL2540 probes (`arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:509-532`)

The vendor driver rejects the client when `pdata->als_name` is NULL
(`ams_tsl2540.c:648`), and `tsl2540_init_dt()` only fills platform data from DT
properties, so the driver's built-in defaults are unreachable whenever the node
exists without properties (all coefficients stay 0 and lux would read 0).

Added `als_name = "taos_als"` plus the stock PVT calibration block (`persist`,
`als_gain`, `als_gain_factor`, `als_deltap`, `als_time`, `d_factor`,
`ch0_coef0`, `ch1_coef0`, `ch0_coef1`, `ch1_coef1`, `az_iterations`,
`als_can_wake`), taken from the decompiled stock PVT DTB
(`experiments/phase-01/dtb/dtb_04_000523472.dtb`, node `tsl2540@39`). No
interrupt is wired, as the vendor driver tolerates `client->irq == 0` and does
not request an IRQ.

### 2. MT8167 MFG power domains (`drivers/pmdomain/mediatek/mt8167-pm-domains.h:54-93`)

`MFG_ASYNC`, `MFG_2D` and `MFG` get `MTK_SCPD_KEEP_DEFAULT_OFF`. The GPU
domains never raise PWR_ACK on this SoC/firmware (`0x60c` reports them on,
`0x610` stays clear, see step33 `sysfs-state.log`), so the probe's power-on loop
times out (-110) and aborts the whole `mtk-power-controller` probe, losing every
other domain. Defaulting them off skips the power-on at probe while the genpd
framework still powers a domain on demand if a consumer appears. `mt8163-*`
tables are untouched; the only other MT8167 board (`mt8167-pumpkin.dts`) shares
the table and gains the same fix, with no behaviour change unless a GPU driver
is enabled.

### 3. tmp112 binding (`arch/arm64/configs/mt8167_arm64_defconfig:44`)

`ti,tmp112` is already handled by `drivers/hwmon/lm75.c:965` (register
compatible, 16-bit config); the kernel simply lacked the driver
(`CONFIG_SENSORS_LM75` was not set in this config). Added
`CONFIG_SENSORS_LM75=y` instead of adding a wrong OF entry to `tmp108.c`, which
only implements the TMP108/TMP1085 register map.

### 4. Thermal zone (`arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:635,648-661`)

`drivers/thermal/mediatek/auxadc_thermal.c` has no MT8167 compatible (the
stock `mediatek,mt8167-thermal` node at `0x1100d000` is a vendor driver), so
the fallback applies: a `thermal-zones/board-thermal` zone over the tmp112
thermistor, labelled `tmp112`. `drivers/hwmon/hwmon.c` (`hwmon_thermal_add_sensor`)
registers the zone from the phandle, so no driver change is needed.
`CONFIG_THERMAL`, `CONFIG_THERMAL_OF`, `CONFIG_CPU_THERMAL` were already set.

## Verification

```
cd repos/LibreEcho-Linux-618
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=phase6 \
  KBUILD_BUILD_TIMESTAMP="2026-11-21 00:00:00 UTC"
make -s O=/tmp/lidar-618 ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make -s O=/tmp/lidar-618 ARCH=arm64 LLVM=1 -j16 Image mediatek/libreecho-lidar.dtb
```

Exit 0 (build log `/tmp/phase7-build.log`; no warning mentions
`libreecho-lidar.dts`, `mt8167-pm-domains.h`, `lm75.c` or `tmp108.c`).

- `Image` 13,818,368 bytes; `libreecho-lidar.dtb` 23,306 bytes.
- `dtc -I dtb -O dts` round trip of the built DTB: exit 0, no warnings.
- Built DTB contains `als_name = "taos_als"`, the calibration properties, the
  labelled `ti,tmp112` node and `thermal-zones/board-thermal` with
  `thermal-sensors` pointing at that node.
- `.config`: `CONFIG_SENSORS_LM75=y`, `CONFIG_HWMON=y`, `CONFIG_THERMAL=y`,
  `CONFIG_THERMAL_OF=y`; `drivers/hwmon/lm75.o` built.
- `dtbs_check` not run: the host has no `dtschema` Python module (`make
  dtbs_check` would fail for that reason alone).

Artifacts: `artifacts/phase-07-prep/kernel/{Image,libreecho-lidar.dtb,config,SHA256SUMS}`

```
de09ed1d9b3a9485d92eedf11a3a9fd303b6e16376c3e074ee73a3428ea5ba7a  Image
a28044aa03ce6742511516ea389b0323c868c58e3fdcc60e390bb03d9bbf16a0  libreecho-lidar.dtb
26ffe02e85fe0f051970103b5a1410ee6e90f8b48a7e325eed8f7f9d1147912f  config
```

Not verified on hardware: TSL2540 probe/`als_lux`, `mtk-power-controller`
completing, tmp112 binding, and `/status.temperature_c`.
