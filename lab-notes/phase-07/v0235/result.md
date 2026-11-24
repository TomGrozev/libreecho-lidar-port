# v0.2.35: temperature, light and Sendspin playing state

Owner report on v0.2.34: the web portal shows 0 °C, and Sendspin music does not show as
playing, so the music-reactive LEDs never start.

## Causes

- Temperature and light: v0.2.33 and v0.2.34 booted `artifacts/phase-06/kernel`, whose DTB
  has no `board-thermal` zone and no TSL2540 `als_name`/`boot-on`. The v0.2.34 build set
  `KERNEL` but never exported `KERNEL_DIR`, so the hand image script fell back to its
  default. Details: `../temperature-regression/result.md`.
- Sendspin playing state: the engine stages Sendspin audio outside the producer FIFOs, and
  the status mask and the music analysis tap read only the FIFOs. Fixed in Platform
  `0a4d7a6e0` (`fix/sendspin-media-status`, fast-forwarded into
  `feature/lidar-support-0.14.6`). Details: `../sendspin-playing/result.md`.

## Build (host)

The v0.2.35 hand build script (Platform `0a4d7a6e0`, UI `470eb36`,
kernel `kernel-step36-thermal`, engine compiled from Platform HEAD) has been removed;
`tools/lab-build.py` replaces it. `artifacts/phase-07/v0235/verify-v0235.log`: 17 PASS, 0 FAIL.
Bundle sha256 `fe5eccb0cf0f2bc2df219df6be7cc4528340eb513d1d1c700e0700321b99ae09`.

Workspace-move repairs: a local `/artifacts -> private/artifacts` symlink (excluded in
`.git/info/exclude`) because the phase-05 toolchains embed the old absolute path, and the
lab `qemu-arm-static` on PATH for `verify_recovery_image.py`.

## Install (hardware, owner-approved 2026-11-23)

The hand install script (now removed in favour of `tools/lab-build.py`);
`install/events.log`: verify_rc=0, install_rc=0, signature PASS,
confirmed on slot b with generation `txn-28c496057ce3131e3607916d`. Slot b (mmcblk0p11)
reads back `28c5fad7...` = the built v2 image; the script's WARN line is a parse artifact
(its sed expects lines ending after the hash, `sha256sum -` appends `  -`). Payload
audio-engine on the device: `9334df03...` = the build.

## Device evidence

| Check | Before (`install/before.log`) | After (`install/after.log`) |
|---|---|---|
| `/sys/class/thermal` | empty | `thermal_zone0 board-thermal 25875` |
| TSL2540 | no `als_lux` | `Probe ok.`, `als_lux 423` |
| `/run/libreecho-audio/status.json` while idle | `idle` | `idle` |

Not verified: the portal `/api/status` values (needs owner login; the backend reads the same
sysfs files), and Sendspin `state:"playing"` plus the LED ring during real Sendspin music.
