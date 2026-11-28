# Step 19: mute/LED/capture fixes on hardware

Image `artifacts/phase-06/images-mute/boot-lidar-v2.img` (UI 68264d26c4), sha256 `67e9efc7…6a81`,
flashed to boot_b by `step19-flash.sh`; readback matched (`events.log`). Booted slot B, 6.18.64+.

- ledd: `using IS31FL3236 LED backend`, boot-animation handover complete (`after2.log`).
- Tom: LED test lit the whole ring and changed colours. PASS.
- Tom: mute gives a steady red ring; it clears on release. PASS. Log: `mute indicator on`
  then `mute indicator off`, no inverted state (`mute-retest.log`).
- Capture with micd/waked stopped (`mic-priv2.wav`): all 7 lanes at matching level before mute,
  exactly 0 during latch (60-67 s), all 7 back after release. All four `ADCn PGA Capture Switch` On
  at the end. PASS.
- Tom: volume keys move the ring (meter). PASS.
- Tom: two LEDs stay dim green at idle. ledd status `idle_mode=indicator`; frame shows two
  pixels at 0x29. This is ledd's idle indicator, not a fault.
- Speaker: LOL/LOR switches On, `LO DAC Playback Switch` Off, audiod logs
  `Lidar Output Route=Speaker refused`. Product-path sound not yet checked.
