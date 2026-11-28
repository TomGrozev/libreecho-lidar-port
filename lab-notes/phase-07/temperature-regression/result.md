# v0.2.35 kernel choice for the temperature regression

Date: 2026-11-23. Host-only analysis; no source, build or device writes.

## Decision

Use **`private/artifacts/phase-06/kernel-step36-thermal`** as `KERNEL=` for v0.2.35:

| file | sha256 | size |
|---|---|---|
| `Image` | `f444f4d0cc63da2a204720dfde560020c9addf3a36910ceb71d29fecf28e3c75` | 13,818,368 |
| `config` | `26ffe02e85fe0f051970103b5a1410ee6e90f8b48a7e325eed8f7f9d1147912f` | 127,782 |
| `libreecho-lidar.dtb` | `a8e1957314334d9a03aa6c96082a6d82a1202ee02729cdc2097d8355d6bd5bc7` | 24,032 |

This is exactly the kernel whose boot image was shipped as v0.2.28
(`private/artifacts/phase-06/images-step37-v0228/boot-lidar-v2.manifest.json`,
`inputs.kernel_image` / `inputs.dtb` / `inputs.kernel_config`). It is built from
`LibreEcho-Linux-618` `fix/lidar-port-identity` HEAD `8cb65710c72f` (the
hardware-booted phase-06 6.18.64 line, not the Phase-7 rebase).

## Evidence per fix

### 1. Thermal zone and trip points: present, hardware-proven

- DTB `a8e1957…` has `/thermal-zones/board-thermal` with `board-hot` 55 C,
  `board-passive0/1/2` 57/58/59 C, `board-critical` 60 C, 500 ms hysteresis,
  polling 1000 ms, `thermal-sensors = <&tmp112>`, and three cpufreq cooling
  maps. Decompile: `private/lab/phase-06/hw-20261121/step36-thermal-trips/built-lidar.dts:1289-1347`.
- `tmp112: temperature-sensor@48` is labelled in the same DTB; LM75 is built in
  (`config:1989 CONFIG_SENSORS_LM75=y`).
- Built by `8cb65710c72f` "feat(lidar): give the board thermal zone stock trip
  points" (`private/lab/phase-06/hw-20261121/step36-thermal-trips/result.md:5-8`).
- Hardware: the v0.2.26 image (same line, thermal zone without trips) read
  `temperature_c=24` on the unit
  (`private/lab/phase-06/hw-20261121/step34-fixes/api-recheck.md:27`, JSON in
  `step34-fixes/ApiRecheck/api/probe_get_status.json`). v0.2.28, built from this
  exact dir, also read 24 (Tom/Main verified; see the v0.2.28 manifest above).

### 2. TSL2540 ALS fix: present

The fix is three commits, all ancestors of `8cb65710`:

- `8985a44` binds the sensor and adds `als_name = "taos_als"` plus the PVT
  calibration (`libreecho-lidar.dts:511-530` at that commit);
- `074992b` fixes `tsl2540_remove()` to unwind probe;
- `b8eaba14` adds `boot-on;` so probe powers the ALS
  (`libreecho-lidar.dts` at `b8eaba14`, hunk around line 519).

The built DTB `a8e1957…` carries both `als_name` and `boot-on` in
`light-sensor@39` (`built-lidar.dts:548-566`), and the same Image build contains
the `remove()` fix. FDT traversal of all four candidates:

```
phase-06/kernel                board-thermal=False trips=[]        als props=[]
kernel-step36-thermal          board-thermal=True  trips=[6 nodes] als props=[als_name, boot-on]
phase-07-prep/kernel           board-thermal=True  trips=[]        als props=[als_name]
phase-07-prep/kernel-als       board-thermal=True  trips=[]        als props=[als_name, boot-on]
```

### 3. cpufreq / latency fix: present

- `77931cc` adds `CONFIG_ARM_MEDIATEK_CPUFREQ=y`
  (`arch/arm64/configs/mt8167_arm64_defconfig`, commit shown in
  `private/lab/phase-06/hw-20261121/step33-latency-fix/CpufreqWake.md`).
- `kernel-step36-thermal/config:575` has `CONFIG_ARM_MEDIATEK_CPUFREQ=y`;
  `:576 CONFIG_ARM_MEDIATEK_CPUFREQ_HW=y`; `:2079 CONFIG_CPU_THERMAL=y`.
- `git merge-base --is-ancestor 77931cc 8cb65710` → true, so the Image built at
  `8cb65710` contains the driver. The Image is not the cpufreq-only
  `8acf87fe…` from `phase-06/kernel`: it was relinked in the ALS tree at
  `b8eaba14`/`8cb65710` (`libreecho@step36 #2 2026-11-22`, `strings Image`), so
  it also carries the MFG power-domain and `tsl2540_remove()` C fixes.

### 4. Other candidate dirs: do not use

| dir | Image | DTB | Missing |
|---|---|---|---|
| `phase-06/kernel` (= v0.2.33/v0.2.34, the v0.2.34 build) | `8acf87…` | `e8727c…` | no thermal zone, no ALS props (DTB built at `3f2711a`, before all three ALS commits and before thermal); `README.md:11` |
| `phase-07-prep/kernel` | `de09ed1…` | `a28044…` | trip points, `boot-on`; built at `77931cc` + uncommitted KernelFixes |
| `phase-07-prep/kernel-als` | `53417fd…` | `fe0fc1…` | trip points; built at `b8eaba14` (09:16), before `8cb65710` (10:04) |
| `phase-06/latency/cpufreq` | `8acf87…` | `e8727c…` | same DTB as `phase-06/kernel`; cpufreq only |

So **no fix is missing from `kernel-step36-thermal`**, and no other artifact has
all of them. Nothing needs to be taken from the 6.18-rebased
`feature/lidar-support`/`feature/lidar-support-6.18` branches; those must not be
used for v0.2.35 (never booted).

Note (not a regression): `4035711` "keep Lidar mono playback on the left DAC
slot" exists only on the Phase-7 rebased branch and is absent from both
`8acf87…` (v0.2.34) and `f444f4…`. The switch does not lose it relative to
v0.2.34.

## Light sensor: same root cause, also regressed

Yes. v0.2.34's DTB `e8727c88…` has `light-sensor@39` with only
`compatible = "amstaos,tsl2540"` and `reg = <0x39>` (source at `3f2711a`; the
DTB is the one rebuilt at that commit, `phase-06/kernel/README.md:11`). It has
neither `als_name` nor `boot-on`.

- `ams_tsl2540.c:648` rejects probe when `pdata->als_name` is NULL
  (`drivers/iio/light/libreecho/ams_tsl2540.c`), so the driver never creates
  `/sys/bus/i2c/devices/0-0039/als_lux`.
- The UI's `read_light_level()` tries `0-0039/als_lux` and `1-0039/als_lux` and
  returns -1 when neither reads (`private/forks/LibreEcho-UI/src/backend_linux.c:751-774`),
  which is `status.light_lux` (`:979`). `GET /light` likewise reports the sensor
  unavailable because `light_sensor_dir()` finds no `als_lux` (`:776-806`).
- So v0.2.34 should show `light_lux=-1` (the pre-ALS value), and the same kernel
  swap fixes it: with `als_name` + `boot-on`, probe succeeds, `als_lux` exists,
  and `boot-on` powers the chip (`ams_tsl2540.c:518,600`).

Historical contrast: v0.2.26 (ALS bound but no `boot-on`) reported `light_lux=0`,
`powered=false`, not -1, and a manual `als_power_state=1` produced lux 1121-1125
(`step34-fixes/api-recheck.md:27` and the light section).

## Device check (not performed)

The unit is not reachable from this host today. `<DEVICE_IP_A>` (last known
Wi-Fi address) does not answer
ICMP, TCP 80/8080/8000/5000/8888 are closed, and the `adb` wrapper is gone from
PATH after the workspace move (HTTP to port 80 returns
`Failed to connect`). Full transcript: `device-probe.log`. No
`/sys/class/thermal` listing or `GET /status` before-evidence could be captured.

## Unverified

- v0.2.35 itself was not built or booted (out of scope).
- The step36 Image + DTB combination booted as v0.2.28, but a post-`boot-on`
  non-zero `light_lux` reading was not captured on hardware in the notes; the
  ALS chain is host-verified only up to DTB/`Image` contents.
- Reading `/sys/class/thermal/thermal_zone*/type` and `/temp` on v0.2.34 was not
  possible because the device is offline.
