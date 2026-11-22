# Board thermal trips on the tmp112 (Lidar)

Date: 2026-11-22. Kernel repo `repos/LibreEcho-Linux-618`, branch
`fix/lidar-port-identity`. Base/HEAD before the change: `b8eaba14e3f1`.
Commit: `8cb65710c72f6438cd237f9fa0fbaf4c5b49cb04`
(`feat(lidar): give the board thermal zone stock trip points`).

## Inputs and what exists in our DT

- Board DTS: `arch/arm64/boot/dts/mediatek/libreecho-lidar.dts`
  - `tmp112` on i2c2 (0x48): line 558 (`tmp112: temperature-sensor@48`), used by
    `board-thermal` at line 674.
  - `tmp108` on i2c0 (0x48): line 633; `tmp108` on i2c2 (0x4a): line 563.
    Neither is referenced by any zone.
  - `board-thermal` was trip-less before this change (old lines 656-663).
  - `&cpu0` override: lines 745-749; `#cooling-cells = <2>` added at line 748.
- SoC thermal: the production DTB has `thermal@1100d000` /
  `mediatek,mt8167-thermal` (stock PVT decompile line 1527), but `mt8167.dtsi`
  does not describe it and mainline 6.18 has no MT8167 backend:
  `drivers/thermal/mediatek/auxadc_thermal.c` has no `mt8167` compatible, and
  the built config has `CONFIG_MTK_SOC_THERMAL` unset
  (`artifacts/phase-07-prep/kernel/config:2088`). So the tmp112 remains the
  only usable zone sensor.
- CPU cooling: `cpu0` inherits `operating-points-v2 = <&cluster0_opp>` from
  `mt8516.dtsi:60` (5 OPPs, 598 MHz-1.3 GHz) but had no `#cooling-cells`.
  `drivers/cpufreq/cpufreq.c:1625` registers the cpufreq cooling device only
  when the policy node has that property
  (`drivers/thermal/cpufreq_cooling.c:660`), so `&cpu0` now provides it.

## Chosen values and their evidence

All values are copied from the production stock DTB for `amzn,lidar-pvt`
(extracted `dumps/stock/boot_a.bin` appended FDT index 4, sha256
`b5302d9e...`, decompiled to `stock-pvt.dts` in this directory):

- `stock-pvt.dts:2630-2686`: `skin_virtual` and `case_virtual` zones:
  `trip-point@0..3` passive at 0xd6d8/0xdea8/0xe290/0xe678 =
  **55/57/58/59 C**, hysteresis 0x1f4 = **500 ms**, `trip-point@4` critical at
  0xea60 = **60 C**. Same thresholds in both zones.
- `stock-pvt.dts:2681-2703`, cooling maps: the 55 C trip permits cpufreq
  cooling state 0..0 (no frequency reduction), then 0..1, 1..2, 2..3 for
  57/58/59 C. The 55 C step is therefore implemented as `type = "hot"`
  (notification only, `thermal_core.c:463-482`), and the three real throttle
  steps are passive with the same state ranges.
- `stock-pvt.dts:2835-2853`: stock exposes the raw thermistors as trip-less
  zones (`tmp108_i2c0_48_s`, `tmp108_i2c2_4a_s`, `tmp112_i2c2_48_s`).
- `stock-nn_tempdevices-default.txt` / `-high-cpu.txt` /
  `-speaker.txt` (extracted from `dumps/20261121-lidar-phase6/system_a.img`,
  `/system/etc/ambienttempd/*/nn_tempdevices.txt`): the tmp112 is one of the
  two sensors feeding stock's high-CPU detector and the first sensor in the
  ambient model, i.e. the board-relevant sensor for these limits.
- `stock-ambient_temp_config.json`: high-CPU detector treats 55.0 C as the
  active-SoC threshold, corroborating 55 C as the first notification step.

The two tmp108s are left unattached to a zone: stock gives them no trip
limits (only trip-less zones for its userspace daemon), so attaching them
with invented limits is not evidence-based.

Not used: the earlier stock `tweeter_virtual` critical of 0xfa0 (4.0 C), which
is an under-temperature tweeter guard, not a board limit.

## Change

`arch/arm64/boot/dts/mediatek/libreecho-lidar.dts`:

- lines 656-726: `board-thermal` gains `polling-delay-passive = <1000>`,
  `board-hot` 55 C, `board-passive0/1/2` 57/58/59 C (500 ms hysteresis each),
  `board-critical` 60 C, and three cooling maps to `<&cpu0 0 1>`,
  `<&cpu0 1 2>`, `<&cpu0 2 3>`.
- line 748: `#cooling-cells = <2>;` on `&cpu0`.

## Build

Incremental build in the existing O= tree (no C changes, so only the DTB and
the unchanged Image were emitted). Commands from
`repos/LibreEcho-Linux-618`:

```
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=step36 \
  KBUILD_BUILD_TIMESTAMP="2026-11-22 00:00:00 UTC"
make -s O=/tmp/lidar-618-als ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make -s O=/tmp/lidar-618-als ARCH=arm64 LLVM=1 -j$(nproc) \
  Image mediatek/libreecho-lidar.dtb
```

Exit 0; `build.log` in this directory has no warnings. `dtc` reports nothing
(`dtc-built.err` is empty). Outputs:

`artifacts/phase-06/kernel-step36-thermal/`

| file | sha256 |
|---|---|
| `Image` (13,818,368 B) | `f444f4d0cc63da2a204720dfde560020c9addf3a36910ceb71d29fecf28e3c75` |
| `config` | `26ffe02e85fe0f051970103b5a1410ee6e90f8b48a7e325eed8f7f9d1147912f` |
| `libreecho-lidar.dtb` | `a8e1957314334d9a03aa6c96082a6d82a1202ee02729cdc2097d8355d6bd5bc7` |

## Built DTB decompile (trips present)

`dtc -I dtb -O dts` of the built DTB, `built-lidar.dts:1291-1347`:

```
board-thermal {
    polling-delay = <0x3e8>;
    polling-delay-passive = <0x3e8>;
    thermal-sensors = <0x06>;

    trips {
        board-hot {
            temperature = <0xd6d8>;      /* 55 C */
            hysteresis = <0x1f4>;
            type = "hot";
        };
        board-passive0 {
            temperature = <0xdea8>;      /* 57 C */
            hysteresis = <0x1f4>;
            type = "passive";
        };
        board-passive1 {
            temperature = <0xe290>;      /* 58 C */
            ...
        };
        board-passive2 {
            temperature = <0xe678>;      /* 59 C */
            ...
        };
        board-critical {
            temperature = <0xea60>;      /* 60 C */
            hysteresis = <0x1f4>;
            type = "critical";
        };
    };

    cooling-maps {
        map0 { trip = <...>; cooling-device = <0x07 0x00 0x01>; };
        map1 { trip = <...>; cooling-device = <0x07 0x01 0x02>; };
        map2 { trip = <...>; cooling-device = <0x07 0x02 0x03>; };
    };
};
```

(phandle 0x06 is the tmp112; 0x07 is cpu0, which now carries
`#cooling-cells = <0x02>`.)

## What to verify on the device after install

1. `dmesg | grep -i thermal`: no `No trip points found for
   temperature-sensor id=0`; expect the `board-thermal` zone to register and
   a cpufreq cooling device to appear.
2. `for z in /sys/class/thermal/thermal_zone*; do echo $z $(cat $z/type)
   $(cat $z/temp); done`: `board-thermal` temp should track the tmp112
   (hwmon `tmp112` on i2c2, ~25-30 C idle).
3. `ls /sys/class/thermal/thermal_zone*/trip_point_*`: five trips per zone:
   `trip_point_0_type=hot` 55000, `_1..3_type=passive` 57000/58000/59000,
   `_4_type=critical` 60000 (mC, hysteresis 500).
4. `cat /sys/class/thermal/cooling_device*/type`: `cpufreq` present;
   `cat .../max_state` should be 4 (5 OPPs).
5. Force a passive trip only if the owner permits a write test (e.g.
   `thermal_zone*/emul_temp` is not enabled, so a real load test is needed);
   otherwise just confirm the trip files and absence of the kernel warning.
   Do not trigger the critical trip on a live unit: it calls
   `orderly_poweroff` (`thermal_core.c:384-393`).

## Caveats

- Sensors: stock's 55-60 C values apply to its virtual skin/case sensors
  built from the auxadc thermistors; the tmp112 tracks the board, not the
  outer skin, so its absolute temperature will read somewhat lower than the
  skin. The thresholds are therefore conservative (they trip earlier than
  stock skin would).
- The tmp108s stay outside the thermal core. If speaker/amp protection is
  wanted later, the stock NN models name them but supply no limits.
