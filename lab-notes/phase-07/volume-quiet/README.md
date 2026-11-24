# Lidar maximum loudness: where the level goes

Owner report (2026-11-24): at 100% the Echo Plus 2nd Gen port is clearly quieter than
stock FireOS, for music (Sendspin/HA/Bluetooth) and for assistant speech.

Status: host-side diagnosis only. The device was not reachable (`adb devices` empty,
`adb connect` not attempted without an address confirmed by the owner); every device value
below is from recorded dumps in `private/dumps/` and `private/lab/phase-06/hw-20261121/`.

## Chain and the gap

```
source -> software master gain -> PCM Playback Volume -> DAC biquads -> LO driver -> amp
             (engine taper)          (AIC32x4)          (crossover)    (AIC32x4)   (GPIO on/off)
```

| layer | our value | stock / reference | gap |
|---|---|---|---|
| engine master, 100% | -12.0 dB (`logical_master_raw(100)=103`) | stock FireOS HAL: 0 dB at stream volume 100 (media curve ref) | **-12 dB** |
| PCM Playback Volume | 127 = 0 dB | 127 / reset 0x00 = 0 dB | 0 dB |
| LO Driver Gain | 0 = **-6 dB** (live dump) | 6 = 0 dB (reference UCM; stock mixer path leaves it at the driver default, see caveat) | **-6 dB** |
| HP Driver Gain (jack only) | 6 = 0 dB | 11 = +5 dB | -5 dB on jack |
| crossover biquads | identical to stock ids 0..89 | same | 0 dB (both bands shaped -3.5/-3.4 dB by design) |
| amp enable | GPIO105 on/off, MFP5 mute | same | 0 dB, no gain control |

Sum at 100%: **-18 dB** below digital full scale, vs 0 dB for stock as documented by the
reference project.

## Proven findings

1. **Software master caps at -12 dB.**
   `private/forks/LibreEcho-Platform/tools/mt8163-arm32/airplay/audio_engine.c:2800-2807`
   (`logical_master_raw`) and `:2867-2872` (`logical_master_gain`): full volume maps to raw
   103, i.e. -12.0 dB. This is a deliberate general LibreEcho taper ("full-scale pre-DSP gain
   is no longer reachable", to stop MT8163 speaker distortion). The Lidar render path has no
   DSP, limiter or make-up gain (`:2755-2770`), so the 12 dB is pure loss here.
   `audiod` only drives `PCM Playback Volume`, holding it at raw 127 = 0 dB
   (`LibreEcho-UI/src/adapter/audiod.c:920-940`).

2. **Lidar audio profile sets the analogue driver gain to -6 dB.**
   `private/forks/LibreEcho-Platform/tools/mt8167-arm64/libreecho_platform_targets.py:73-78`
   has `'hp_driver_gain': 0, 'lo_driver_gain': 0` with the comment "no analogue or digital
   gain". In `tlv320aic32x4.c:400-402` and `:423-425` the control's TLV is -6 dB min, 1 dB
   step (`tlv_driver_gain`), so index 0 is **-6 dB**, index 6 is 0 dB. The engine writes it
   unchanged in `arm_output_controls()` (`audio_engine.c:818-822`).
   Observed: `private/dumps/20261122-lidar-announce/sendspin-mixer-live.txt:33`
   `LO Driver Gain Volume 00, 0`; also `step20-engine/silent-cues.log:8`. Before the engine
   profile existed the same image read `06, 6` (`step16-audio/no-sound-diag2.log:17`,
   `step8-audio/capture-test4.log:25`).

3. **Routing is right.** `Output Route Speaker`, `LO DAC Playback on`,
   `LOL/LOR Output Mixer *_DAC on`, `HP DAC off` (sendspin dump), matching the machine
   driver's speaker path (`mt8516-amazon-lidar.c:224-236`) and stock
   `mixer_paths.xml` "normal-playback speaker" (`:173-178`).

4. **Crossover coefficients match stock exactly** for the 90 bytes we program
   (`mt8516-amazon-lidar.c:104-115` vs `stock/mixer_paths.xml:57-147`). The 3.5 dB/3.4 dB
   crossover loss is stock too, not a regression.
   Difference: stock also writes biquad ids 90-116 (an extra pass-through plus
   `07 00 c6` at 114-116). Our `DAC Biquad Coefficients` control is 90 bytes, so those are
   never programmed. Not a loudness cause; verify the intended filter count later.

## Caveat on "stock" values

Stock FireOS's `normal-playback speaker` path never sets `PCM Playback Volume` or
`LO Driver Gain Volume`; its HAL (`stock/hal/libalexaaudiohal.so`) only names `biquad
coefficients`, `LO DAC Playback Switch` and `Ext_Speaker_Amp_Switch`, and applies stream
volume in software (`alexa::out::set_volume`). The 0 dB LO / 0 dB PCM stock figure therefore
comes from the reference project's UCM
(`private/reference/lidar-mainline/ucm2/MediaTek/amazon-lidar/amazon-lidar.conf:31-39`,
"line out 0 dB ... 127 (0 dB) is the speaker's full stock loudness"), not from a register
read of stock FireOS. Treat the stock maximum as 0 dB PCM + 0 dB LO (reference-proven,
not image-proven).

## Fix proposal

Repo: `LibreEcho-Platform`, branch `feature/lidar-support-0.14.6` (no source edits made).

1. Lidar-specific: `tools/mt8167-arm64/libreecho_platform_targets.py`, set
   `'lo_driver_gain': 6` (and `'hp_driver_gain': 11` if the jack should match stock +5 dB).
   This is the +6 dB hardware-path fix and is a Lidar bug: index 0 is not "no gain".
2. Engine: give the Lidar chain the stock ceiling. Either let the profile carry a
   Lidar pre-gain of +12 dB applied only on `lidar_chain` (the loader currently rejects
   `pre_gain_db` for non-biscuit chains, `audio_engine.c:2456-2459`), or make
   `logical_master_raw()` top out at 127 for `lidar_chain`. The general -12 dB taper is
   intentional for MT8163; do not change it there. Raising only the Lidar ceiling is a
   general-engine change gated on `speaker_chain=lidar`, so it belongs in the same Lidar PR.
3. Speaker safety: the resulting maximum equals the reference/stock maximum (0 dB digital,
   0 dB LO); never use PCM index 175 (+24 dB) or LO gain above 6. The Lidar chain has no
   limiter and clips at full scale, so hot 0 dBFS tracks may clip at 100%; add the same
   safety limiter the other chains have, or cap the top a few dB below 0 dB. Do not exceed
   stock until the owner accepts the risk on the tweeter (high-pass is loaded, so full-band
   bass cannot reach it).

## Commands / evidence

- `private/lab/phase-06/adb.sh 12 devices -l` -> empty list (device offline from host).
- Stock extraction (read-only):
  `debugfs -R "dump /system/vendor/etc/mixer_paths.xml private/lab/phase-07/volume-quiet/stock/mixer_paths.xml" private/dumps/20261121-lidar-phase6/system_a.img`
  (same for `audio_policy_volumes.xml`, `audio_device.xml`,
  `/system/vendor/lib/hw/audio.primary.alexa.so`, `/system/vendor/lib/libalexaaudiohal.so`).
- Live values: `sendspin-mixer-live.txt`, `step16-audio/no-sound-diag2.log`,
  `step20-engine/silent-cues.log`.
- Not run: any mixer write, test tone, file push, service restart or OTA. No live A/B.

## Open items

- Confirm stock's actual LO gain register value on FireOS (needs a stock boot or a
  documented read), and whether its HAL/limiter makes up gain in software.
- Check the extra stock biquads 90-116.
- Measure whether HA/esphomed/TTS source levels add their own attenuation; not inspected.
