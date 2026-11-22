## 1. Kernel overlay files

All overlay files are full upstream v7.3 copies with local edits unless marked new. Almost all were introduced by the initial import **4ac89c8** (“Initial import … Linux v7.3 overlay”); later fixes are named.

| File | Kind / change | Commit |
|---|---|---|
| `drivers/clk/mediatek/clk-mt8516.c` | Upstream copy + reset support: adds `GATE_TOP5` macro and APLL12_DIV0..6 gates (R/lidar-linux/drivers/clk/mediatek/clk-mt8516.c:549,637-645) and an `mtk_clk_rst_desc` for INFRA_RST0 (assert 0x30, deassert 0x34, bit 23 for MSDC2) attached to `infra_desc` (:662-676). | 4ac89c8 |
| `drivers/clk/mediatek/clk-mtk.c` | Upstream copy + sparse-ID fix: `mtk_clk_desc_num_ids()` scans every clock table for the largest `id`, and `num_clks = max(table counts, max ID)` before allocating `clk_data` (R/.../clk-mtk.c:476-487,538-543). Prevents `hws[]` overflow/`-ENOENT` gaps. | 4ac89c8 |
| `drivers/usb/musb/musb_core.h`, `mediatek.c`, `musb_gadget.c` | Upstream copies + MT8516 quirks: isochronous endpoints use PIO instead of Inventra DMA (DMA produced no IN packets; UAC2 mic 0→48 kHz), and isochronous OUT packets with DATAERROR are dropped instead of passed up with garbage lengths; MediaTek quirk wiring. | dbaa2a5, 4c126f1 |
| `drivers/bluetooth/btmtksdio.c` | New/divergent: MT7668 gen4 SDIO Bluetooth ported from Amazon’s GPL release; not the mainline btmtksdio. Boots from linux-firmware `mt7668pr2h.bin` because the vendor BT firmware crashes under mainline. [INFERENCE: source provenance from commit text.] | b8dba12, 4ac89c8 |
| `drivers/leds/leds-is31fl32xx.c` | Upstream copy + IS31FL3236A: accepts the A variant, parses `issi,22khz-pwm`, and writes the PWM-frequency register **after** `init_regs()` reset (previously reset restored 3 kHz). | 4bfc85d, ed5fd61 |
| `drivers/regulator/rt5739.c` | **New** driver (Richtek GPL-2.0, Copyright 2023): RT5733/RT5739, 0.3-1.3 V in 5 mV steps, NSEL0/NSEL1 banks, auto/FPWM, VSEL GPIO, suspend voltage/mode (R/.../rt5739.c:1-51). | 4ac89c8 |
| `drivers/iio/light/tsl2540.c` | **New** minimal IIO driver: visible + IR 16-bit channels, gain 1/2×-128×, integration time, chip ID 0xe4; no interrupt/threshold support (R/.../tsl2540.c:1-48). Later fix: lux-per-count 19.04 (factor 3 had been divided), mark samples stale on reconfig. | 8d362e4, fcaceb0 |
| `sound/soc/codecs/tlv320aic32x4*.c/.h` | Upstream copies + DAC biquad coefficient RAM (page 45, 90 bytes, A-C left/right 24-bit) and “DAC Mono Mix Switch”; codec clocks taken once with `clk_bulk_get()` in component probe (fixes devres leak/refcount 29 and unbind oops); MFP5 mute support. | 31dc01f, f1f9b79, 842/437 |
| `sound/soc/codecs/tlv320adc3xxx.c` | Upstream copy + ADC3101/TDM support: validates TDM slot masks (R/.../tlv320adc3xxx.c:1458), tolerates shared reset line, exposes PGA. | 4ac89c8 |
| `sound/soc/mediatek/mt8516/*` | **New** platform driver (Amazon GPL derived): `mt8516-afe-clk.c`, `mt8516-afe-pcm.c`, common/reg headers; machine driver `mt8516-amazon-lidar.c`. | 4ac89c8 |
| `sound/soc/mediatek/Kconfig`, `Makefile`, `mt8516/Makefile` | Hooks: `SND_SOC_MT8516` (R/.../mediatek/Kconfig:366-375) and `SND_SOC_MT8516_AMAZON_LIDAR` selecting ADC3XXX + AIC32X4_I2C (:377-389); `obj-$(CONFIG_SND_SOC_MT8516) += mt8516/`, machine object. | 4ac89c8 |
| Bindings (`ams,tsl2540.yaml`, `richtek,rt5739.yaml`, `amazon,lidar-sound.yaml`, `mediatek,mt8516-afe-pcm.yaml`, `ti,tlv320adc3xxx.yaml`) | New documentation, not in upstream v7.3. | 4ac89c8 |

## 2. Board DTS and gap table

Reference board nodes (R/.../mt8516-amazon-lidar.dts): aliases serial1/2 = uart1/2, mmc1 = mmc2 (:29-35); `wifi_3v3` fixed regulator on GPIO24 with 500 ms startup and 5 ms off-on delay (:112-126); gpio-keys volume-up GPIO7, volume-down GPIO12, action GPIO42 = `KEY_HELP` 0x8a, mic-mute GPIO108 = `KEY_MICMUTE`, privacy switch GPIO18 = `SW_MUTE_DEVICE` (:136-184); `gpio-line-names` and `board_hog_pins` set EFR32 reset GPIO13 high, EFR32 SWCLK GPIO1 low, privacy-force GPIO107 high (:194-230); LED SDB GPIO4 high (:231-239); uart1 enabled with `uart1_pins` (:405-413), uart2 enabled with RTS/CTS (:416-425); i2c0: TSL2540 @0x39, IS31FL3236A @0x3f, TMP108 @0x48 (:429-491); i2c1: RT5738 @0x57, 1.15-1.3 V, `richtek,vsel-active-high` (:505-518); i2c2: MCP4631 @0x2e, TMP112 @0x48, TMP108 @0x4a (:522-537); MSDC2 pinctrl/vmmc `wifi_3v3` (:557-582); usb0 peripheral (:584-592); cpu0 OPP/cpufreq (:595+).

Audio dtsi (R/.../-audio.dtsi): `sound` card with `audio-gpio-pins`, `mediatek,platform = <&afe>`, `amp-enable-gpios = <&pio 105 …>`, `dac-mux-gpios = <&pio 109 …>` (:16-22); speaker DAI link (:24-29), mic TDM link (:30-36); `&afe` with `audio_pins` (:38-42); DAC @0x18 on i2c2 (:86-105); four ADCs @0x18-0x1b on i2c0 (:44-84); pinctrl groups (:107-125).

Gap vs `libreecho-lidar.dts` (O):

| Item | Reference | Ours |
|---|---|---|
| sound card / amp GPIO105 / dac-mux GPIO109 / AFE | R audio:16-42 | **absent** (no sound node; O:445-543 has only I2C) |
| audio pinmux (I2S/TDM/DMIC) | R audio:107-125 | **absent** |
| DAC AIC32x4 @0x18 i2c2, MFP5 mute | R audio:86-105, MFP5 `0x0d` | present O:525-538, but MFP5 `0x0c` and no sound card |
| 4× ADC3101 @0x18-0x1b i2c0 | R audio:44-84 | present O:469-515; shared reset GPIO2 handled, but all get `CLK_TOP_APLL12_DIV1` mclk; ref gives mclk only to DAC [INFERENCE from node properties] |
| TSL2540 @0x39 | R:429-432 | **absent** (O:445-467) |
| IS31FL3236A @0x3f, `issi,22khz-pwm` | R:434-485 | present O:409-467 but `issi,is31fl3236`, `channel-offset = 3`, `play-boot-animation`; no 22 kHz (O:412-416) |
| TMP108 @0x48 i2c0 | R:487-491 | **absent** |
| RT5738 @0x57 i2c1 | R:505-518 | **absent**; only comment that rail is RT5738 (O:102-103) |
| MCP4631/TMP112/TMP108 i2c2 | R:522-537 | **absent** (O:520-541 only ADCs) |
| uart1 / uart2 (EFR32, PTI) | R:405-425 | **absent/disabled**; aliases only O:35-41 |
| MSDC2 `resets = <&infracfg 23>` | R mt8516.dtsi:514-516 | **absent** O mt8516.dtsi:434-437 |
| `wifi_3v3` + GPIO24 pinctrl | R:112-126,557-582 | **absent** |
| gpio-line-names / board_hog (EFR32, privacy force) | R:194-230 | **absent** |
| pwrap disabled | R commit e850353 | present O:543-546 |
| buttons + privacy + KEY_HELP | R:136-184 | **same** O:151-198 |
| cpufreq/OPP | R:595+ | present O:559+ |

## 3. Kernel config

Reference `lidar.config` enables the full Phase-6 set: `SND_SOC_MT8516`, `SND_SOC_MT8516_AMAZON_LIDAR`, `SND_SOC_TLV320ADC3XXX`, `SND_SOC_TLV320AIC32X4_I2C`, `SND_ALOOP`, `USB_CONFIGFS_F_UAC2`, `IIO`, `TSL2540`, `REGULATOR_RT5739`, `TMP108`, `MCP4531`, `LEDS_CLASS_MULTICOLOR`, `MEDIATEK_CPUFREQ`, `MTK_AUXADC`, `PWM_MEDIATEK`, `RESET_GPIO`, `REGULATOR_GPIO`, `MTK_THERMAL`, `BT_MTKSDIO=m`; dbaa2a5 explicitly added the UAC2 gadget function (R/lidar.config, R/tools/mk-testimg.sh). Our `mt8167_arm64_defconfig` has none of those audio/IIO/LED/multicolor/cpufreq/auxadc/PWM/reset/regulator-GPIO/thermal options; `BT_MTKSDIO` is built in (`=y`) rather than a module. `COMMON_CLK_MT8167` and `PINCTRL_MT8167` come in implicitly through the MT8167 platform, not as explicit defconfig lines. [Absence verified by earlier symbol grep over O/arch/arm64/configs/mt8167_arm64_defconfig.]

## 4. Userspace and UCM

Card name is **`amazonlidar`** (machine driver `.name = "amazon-lidar"`; R/.../mt8516-amazon-lidar.c). UCM: `ucm2/MediaTek/amazon-lidar/amazon-lidar.conf` + `HiFi.conf` (BSD-3-Clause); Speaker = `hw:${CardId},0`, 2 channels, mixer `PCM`; Mic = `hw:${CardId},1`, **8 capture channels** (R/ucm2/.../HiFi.conf). `mk-testimg.sh` runs `alsaucm -c hw:amazonlidar set _boot ''`, which applies the profile’s BootSequence: mic PGA **+35 dB**, output-driver gains as stock, speaker volume **−40 dB** (R/tools/mk-testimg.sh:252-255).

Tools, all `GPL-2.0-only` SPDX except UCM BSD-3-Clause: `lidar-dsp.c` — 48 kHz, 384-frame blocks, 2048-tap FIR zone filters from `EQ_50.cfg`/`EQ_90.cfg`/`EQ_100.cfg`, stock-volume dB table, parametric EQ, MBCL, mono; reads Fire OS coefficient files from `/system/vendor/etc/audio-algorithms` staged to `/run/lidar-dsp`, and uses `snd-aloop pcm_substreams=1 timer_source=amazonlidar.0.0`; only starts when `lidar-feature` enables both `dsp` and `volume` (R/tools/mk-testimg.sh:256-279). `lidar-aec.cc` mixes **6** mics, excluding mic 7 because it picks up interference (R/tools/lidar-aec.cc:35). `lidar-player.c` is the web-UI music daemon (tmpfs library, httpd); `lidar-volume.sh` owns system volume and feeds `lidar-dsp`; `lidar-ring.sh` maps 12 ring LEDs, red=160 when mic muted (`SW_MUTE_DEVICE`), white arc=96, ALS thresholds dark 30 / bright 8000 (R/tools/lidar-ring.sh:106-109). `lidar-feature.sh` gates dsp/volume/ring/wireless/bluetooth/usbaudio/webui/zigbee; `lidar-usbaudio.sh` sets up the UAC2 gadget. `initramfs-modules.txt`: `mt8516-amazon-lidar`, `snd-soc-mt8516-afe`, `snd-soc-tlv320adc3xxx`, `snd-soc-tlv320aic32x4-i2c`, `snd-aloop`, `usb_f_uac2`, `btmtksdio`.

## 5. Fire OS inputs

`mk-testimg.sh` mounts `system_a` read-only and copies:
- Wi-Fi/BT: `/system/vendor/firmware/WIFI_RAM_CODE*MT7668.bin`, `EEPROM_MT7668.bin`, `TxPwrLimit_MT76x8.dat`, `wifi.cfg` (R/tools/mk-testimg.sh:339-344). The same block then `modprobe btmtksdio`; BT uses the linux-firmware ROM patch rather than a Fire OS BT blob (:332-356).
- Speaker tuning: `/system/vendor/etc/audio-algorithms/{AFE.cfg,EQ_*.cfg,ParametricEQ.cfg,MBCL*.cfg}` (R/tools/mk-testimg.sh:263-266).
- Mic calibration is not a file: the UCM BootSequence sets PGA +35 dB (R/tools/mk-testimg.sh:252-255).
- Linux-firmware pin: `mediatek/mt7668pr2h.bin` from tag `20261019`, SHA-256 `465ed634c61b46b34bb21240736f33d3d347fefec7cbfbd1cb6e63334aec4cc9`, symlinked as `mt7668_patch_e2_hdr.bin` (R/tools/mk-testimg.sh:33-42). Reason: mainline `btmtksdio` crashes the vendor Bluetooth firmware; the redistributable linux-firmware patch works for both Wi-Fi and BT (commit b8dba12).

## 6. Hardware facts

- **7 microphones**, captured on four stereo TLV320ADC3101s at i2c0 0x18-0x1b, 8-channel TDM capture; mics 1-6 are mixed by AEC, **mic 7 = capture channel 6** and is excluded (interference tones); **capture channel 7 = line-in**, unverified (R/README.md:645-652, R/tools/lidar-aec.cc:35).
- ADC channel order follows the four ADC nodes (ADC1 ch0-1 … ADC4 ch6-7); no physical geometry is recorded beyond “behind the top cover” for the ALS. [INFERENCE from DTS ordering.]
- Sample rates: speaker playback fixed at 48 kHz; DSP chain 48 kHz/384 frames; AFE platform supports 8-192 kHz. Capture UCM exposes 8 channels; userspace assumes 48 kHz.
- Speaker: stereo DAC, left = **woofer low-pass**, right = **tweeter high-pass**, plus mono mix, from the AIC32x4 line-out drivers; crossover coefficients are written by the machine driver and the route is refused if filters cannot be set (commits 437a3c4, 842/437).
- Amplifier: **GPIO105** enable (`amp-enable-gpios`), **GPIO109** DAC mux; AIC32x4 **MFP5** is the mute line, active per DT; power-down disables amp then mutes, power-up unmutes 500 ms after enable (commits c9804f0, 842/437).
- EFR32: **ttyS2/uart2**, RTS/CTS, `EFR32_RESET_N` = **GPIO13**, SWCLK/bootloader strap = **GPIO1**, PTI frame = GPIO23; privacy force = GPIO107 (active low), latch state = GPIO18, button = GPIO108 (R:194-230).
- MAC address: not in DTS; reference uses the Fire OS Wi-Fi calibration files/nvram (`EEPROM_MT7668.bin`, `wifi.cfg`) [INFERENCE].
- cpufreq: cpu0 OPP table in the board DTS (:595+), using MT8167/MT8516 CPU clocks; reference verified cpufreq on hardware.
- LED ring: 12 RGB LEDs, LED n = channels 3n-2 red, 3n-1 green, 3n blue; IS31FL3236A at 0x3f, 22 kHz PWM (R:434-485).

## 7. Clock gating

Commit **db8242a** (“drop clk_ignore_unused…”) removed the `clk_ignore_unused` kernel argument from the test-image builder because the board now boots with unused-clock gating enabled; the README’s “clock gating test” records that a boot without the flag survives, with the gated clocks listed as NFI, SPI-NOR, BSI, AES, SEJ, RBIST, MSDC1, debug gates, APLL1 dividers, `memslp_dlyer` and `apxgpt`. Our tree still passes `clk_ignore_unused` in its boot flow [INFERENCE from Phase-5 scripts, not re-read here]. Their DTS adds consumers ours lacks: the whole AFE clock tree (top_pdn_audio plus AFE gates), DAC `CLK_TOP_APLL12_DIV1` mclk, uart1/uart2 `rg_uart` gates, i2c1 `ifr_i2c1_sel`, and the MSDC2 `infracfg` reset (not a clock but the same power-domain plumbing). Our MT8167 DTSI overrides topckgen/infracfg with `mediatek,mt8167-*` compatibles (O/arch/arm64/boot/dts/mediatek/mt8167.dtsi:20-34), so copying the MT8516 reset descriptor alone will not bind; the reset/gate work must be replicated in `clk-mt8167.c` (which currently has no `rst_desc`).