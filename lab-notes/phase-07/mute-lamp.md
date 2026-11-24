# Mute lamp after a software mute

Owner report, 2026-11-24: a microphone mute from Home Assistant turns the ring red, but the
lamp in the mute button stays dark. The first press of the button lights the lamp, and the
ring stays red. The second press unmutes the device and the ring goes back to normal.

## Cause

The lamp in the mute button is wired to the hardware privacy latch. On Lidar, software
cannot drive that lamp:

- The Lidar DTS gives `amz_privacy` only `privacy-state-gpios` (GPIO18). The driver then
  runs in read-only state-input mode, and `mute_lamp_store()` returns `-EOPNOTSUPP`
  (LibreEcho-Linux-618: `arch/arm64/boot/dts/mediatek/libreecho-lidar.dts`,
  `drivers/misc/amz_privacy.c`).
- Every device record of `buttond` reports `lamp_control=0`, for example
  `phase-06/hw-20261121/step18-buttons/buttons.log` and
  `phase-06/hw-20261121/step29-features/20261122/device-details.log`.

A mute from Home Assistant is a software mute. `esphomed` tells `audiod` to switch off
capture, and `buttond` shows the red ring when it sees the muted capture. The web UI mute
(`microphone_muted` on `/audio`) uses the same `audiod` path. The first button press
engages the hardware latch, and the latch lights the lamp. The second press releases the
latch. On that release, `buttond` `sync_privacy_state()` sets the software mute to the
latch state, so the release also clears the Home Assistant mute.

This is the documented contract for a board without the lamp control (LibreEcho-UI
`docs/API.md`, "Buttons": when `lamp_control` is false, a software mute lights the ring
and leaves the lamp dark).

## Option not taken

Stock firmware has a line that lets software turn hardware privacy on. The stock
`gpio-privacy` node has `enable-gpio = <&pio 107 GPIO_ACTIVE_LOW>`
(`phase-06/hw-20261121/step36-thermal-trips/stock-pvt.dts`), and the lidar-mainline
reference README describes GPIO107 the same way. The Lidar DTS holds GPIO107 high, which
releases it. A Home Assistant mute could pull the line low to engage the latch. The lamp
would then light, and one press would unmute the device.

Nobody tested GPIO107 on this unit. [INFERENCE] If the line can only turn privacy on, as
the stock node and the reference describe it, Home Assistant could no longer unmute the
device; only the button could.

## Decision

Owner decision, 2026-11-24: keep the software mute and document that the lamp stays dark.
No GPIO107 test ran on the device, and no code changed.
