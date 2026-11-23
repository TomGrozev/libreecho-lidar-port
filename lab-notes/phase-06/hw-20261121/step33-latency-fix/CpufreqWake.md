# CPU frequency scaling and waked thread count for Lidar

Slice `CpufreqWake`, 2026-11-22. Motivation: `step32-ha-latency/result.md` measured the wake
worker at 99.4 % of one core with the CPU fixed at `armpll` 1001 MHz.

## Base commits

| Repo | Branch | Base |
|---|---|---|
| `repos/LibreEcho-Linux-618` | `fix/lidar-port-identity` | `3f2711ac4690` |
| `repos/LibreEcho-UI` | `fix/lidar-port-identity` | `371950abb70d` |

## Commits

- Linux `77931cc96944`: `fix(lidar): enable mediatek-cpufreq so the OPP table reaches 1.3 GHz`
  - `arch/arm64/configs/mt8167_arm64_defconfig:14-16`: `CONFIG_ARM_MEDIATEK_CPUFREQ=y`.
- UI `4b3c17d`: `fix(waked): run two ONNX intra-op threads on Lidar`
  - `init/libreecho-waked.init:53-62`: `TARGET_FILE`/`WAKE_THREADS` default, lidar -> 2.
  - `init/libreecho-waked.init:245`: `--wake-threads $WAKE_THREADS`.
  - `tests/test_waked_init_model.sh`: `TARGET_FILE` in the harness, `wait_args` (the fake
    `start-stop-daemon` backgrounds the daemon, so reading its argv raced it), three
    thread-count cases.

## Why this and not cpufreq-dt

`CONFIG_CPUFREQ_DT=y` was already set, but `cpufreq-dt-platdev` has no MT8167 machine entry,
so nothing bound and `/sys/devices/system/cpu/cpu0/cpufreq` never appeared. 6.18's
`mediatek-cpufreq` already carries `{ .compatible = "mediatek,mt8167" }` with the mt8516
platform data (`proc_max_volt` 1310000), and it is the driver that drives the
`intermediate` clock, reparents the CPU mux, sets the PLL, then the proc rail
(`drivers/cpufreq/mediatek-cpufreq.c:737-760`, `:199-330`). Reference
`reference/lidar-mainline` reports the same driver scaling 598 MHz to 1.3 GHz on this board
(`README.md:642-648`); its `clk-mt8516-apmixedsys.c` PLL table for `armpll` is byte-identical
to our `clk-mt8167-apmixedsys.c:59-61` (0x0100/0x0110, pcwbits 21, pcw 0x0104), and its
`clk-mt8516.c` CPU mux is unchanged from ours, so no clock or driver code had to be copied.

## DTS and regulator sanity

- OPP table `cluster0_opp` in `mt8516.dtsi:21-44` (included by `mt8167.dtsi:15`):
  598/747.5/1040/1196/1300 MHz at 1.15/1.15/1.20/1.25/1.30 V. All four CPUs carry
  `operating-points-v2`, `clocks = <&infracfg CLK_IFR_MUX1_SEL>, <&topckgen CLK_TOP_MAINPLL_D2>`
  and `clock-names = "cpu", "intermediate"` (`mt8516.dtsi:46-105`).
- `proc-supply = <&vproc>` on every CPU (`libreecho-lidar.dts:646-664`).
- `vproc` is the RT5738 at i2c1 0x57, `regulator-min-microvolt = <1150000>`,
  `regulator-max-microvolt = <1300000>`, `richtek,vsel-active-high`
  (`libreecho-lidar.dts:593-602`). The driver's RT5739 table is 300-1300 mV in 5 mV steps
  (`drivers/regulator/rt5739.c:41-45`), so 1.3 V is vsel 0xc8 - the value the reference
  measured at 1.3 GHz. The lowest OPP (1.15 V) equals the DT minimum, so no consumer
  constraint clips an OPP. The driver's `proc_max_volt` 1310000 V is above the regulator
  maximum; the core clamps the request to 1300000, which is the datasheet maximum.
- The intermediate clock is `mainpll_d2`. On the unit `mainpll` reads 1501500000, so the
  driver's `dev_pm_opp_find_freq_ceil(inter_clk)` resolves to 1196 MHz (1.25 V), not the
  failure case where the intermediate rate exceeds the top OPP.
- No DTS change was needed.

## Governor

`schedutil` (already the Kconfig default on SMP and `CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL=y`
in the built config). `performance` would pin the rail at 1.3 V/1.3 GHz permanently on an
always-on speaker, and the wake path is a bursty 80 ms-block load that schedutil ramps
within a block. `CONFIG_CPU_FREQ_GOV_PERFORMANCE` stays available for a one-line `echo
performance > scaling_governor` test.

## Verification

Host, run once: `sh tests/test_waked_init_model.sh` in `repos/LibreEcho-UI` - all 9 cases
pass, including "lidar asks for two wake threads", "other targets keep one wake thread" and
"a missing target file keeps one wake thread".

Device, read-only over Wi-Fi adb (`<DEVICE_IP_A>:5555`, v0.2.24 on slot a):
`/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq` does not exist (as reported),
`cpu0` `clock-names` is `cpu intermediate`, `mainpll` 1501500000.

## Build

```
cd repos/LibreEcho-Linux-618
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=phase6 \
  KBUILD_BUILD_TIMESTAMP="2026-11-21 00:00:00 UTC"
make -s O=/tmp/lidar-618-cpufreq ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make -s O=/tmp/lidar-618-cpufreq ARCH=arm64 LLVM=1 -j$(nproc) Image mediatek/libreecho-lidar.dtb
```

Artifact status: built at `77931cc96944`, exit 0 (227 s, 16 jobs; only the imported MT7668
code warns). `artifacts/phase-06/latency/cpufreq/`:

| File | sha256 |
|---|---|
| `Image` | `8acf87fe028b1372b921a9522d3c4a9d3e6f578541e0dc59113e98860032d9fd` |
| `libreecho-lidar.dtb` | `e8727c88e2240dc77a6b247f54775d1de88acb80707e02c3ba97866337d47029` (unchanged: no DTS edit) |
| `config` | `0ade38941adcf9907988cfce1114010bd36fb4bde1a285eba710788f3b407f4a` |

`config` has `CONFIG_ARM_MEDIATEK_CPUFREQ=y`, `CONFIG_CPUFREQ_DT=y`,
`CONFIG_CPU_FREQ_DEFAULT_GOV_SCHEDUTIL=y`. The boot image was not built here: with the UI
tree dirty, `build_images.sh` fails its `--expected-ui-commit`/`--expected-ui-diff-sha256`
check, and the component at `artifacts/phase-06/components/ui-bundle` is still the old one
(so an image built now would ship `--wake-threads 1`). The two steps below produce it.

## What the integrator needs

1. Kernel: replace `artifacts/phase-06/kernel/{Image,config,libreecho-lidar.dtb}` with the
   three files above (or rebuild from `77931cc96944`), then run
   `experiments/phase-06/build_images.sh --output-dir <dir>` for the boot image(s).
2. UI: rebuild the bundle (`experiments/phase-06/build_components.sh ui`) at UI `4b3c17d`,
   then bump `UI_COMMIT`/`UI_DIFF_SHA256` in `build_images.sh` (both the builder call and
   `verify()`) before building images; with the old pins the builder rejects the dirty UI
   tree and the stale bundle would still ship `--wake-threads 1`.
3. `/etc/libreecho/target` already carries `target_id=lidar` in every Lidar image
   (`libreecho_platform_targets.py:83-90`), which is what the init script reads.
4. The Platform fixture `tools/mt8163-arm32/ota/fixtures/companion-init/libreecho-waked.init`
   (and its SHA256SUMS) is a copy of the old init; it is not used on hardware and was left
   alone.

## Expected device check after the OTA

```
ls /sys/devices/system/cpu/cpu0/cpufreq/            # governor, scaling_cur_freq, ...
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
#   598000 747500 1040000 1196000 1300000
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor    # schedutil
# under load (e.g. `yes >/dev/null` x4, or a real wake turn):
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq    # 1300000 at the top OPP
dmesg | grep -i mtk-cpufreq                                  # no probe failure
# waked CPU share: pidstat/task ticks per thread should now show the work spread
# over two ONNX intra-op threads; wake latency is retested in the HA latency run.
```

Checks not run: no reboot, OTA install or service restart was performed from this slice; the
kernel artifact was not booted, so 1300000 and the two-thread waked behaviour are unverified
on hardware.
