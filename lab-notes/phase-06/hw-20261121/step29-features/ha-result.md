# Home Assistant ESPHome satellite on Lidar, 2026-11-21

## First attempt: FAIL (Lidar-specific)
`PUT /api/v1/voice-pipeline {"mode":"home-assistant"}` returned 202. `libreecho-esphomed` then
exited with `invalid config or missing stable MAC` (`/var/log/libreecho-esphomed.log`) and the
API rolled the mode back to local; the rollback restart took about 40 s (`ha-check.log`). The
owner's own enable landed inside that window and got 409 "restart already in progress".

Cause: esphomed takes its identity MAC from config `wifi_mac` or idme
(`src/adapter/esphomed.c:278`). On this unit idme `mac_addr/value` is "0" and the other idme MAC
fields don't exist. wlan0 has a universally administered, unicast factory MAC, and the same value
appears in five earlier step logs.

## Runtime shim (lost on reboot)
`/etc/default/libreecho-esphomed` sets `IDME_ROOT=/run/libreecho/idme-lidar` (holding
`mac_addr/value` copied from wlan0) and `PRIVACY_STATE=/sys/devices/platform/amz-privacy/privacy_state`
(`ha-runtime-shim.log`).

## Owner enable with the shim: connected
`ha-owner-enable.log`: esphomed is running with the shim args, and its status shows `ready=true`,
`connected=true` and `last_result=success`. TCP 6053 has an ESTABLISHED connection from the
owner's Home Assistant host on the device network. A voice turn through Home Assistant has not
been confirmed by the owner yet.

## Permanent port fix (built, not installed)
OTA v0.2.23 `artifacts/phase-06/ota-step30-identity/lidar-lab-v0.2.23.ota.tar`. It adds the
esphomed wlan0 MAC fallback (UI `a7edb1d3`) and renames the DTS node to `amz_privacy` (kernel
`3f2711ac4690`). Host esphomed runtime tests not run (no host mbedTLS); hardware check in
`step30-identity/install.sh`.
