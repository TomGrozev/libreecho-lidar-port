# Development updates over Wi-Fi: reachability check, 2026-11-21

`PLAN.md`, Phase 6, "Validate development updates over Wi-Fi". Read-only checks only; nothing
was written to the device.

## On the device (over USB ADB)

The running image is slot B, `libreecho.lab=p6-v2`. Its update channel is `dev`, and
`/etc/libreecho/adb-transport` contains `transport=usb-functionfs-and-tcp`, `tcp_listener=true`
and `tcp_port=5555`. The init log shows `adb-transport-policy-read`, and `netstat -ltn` shows
adbd listening on `0.0.0.0:5555` (the web UI listens on `0.0.0.0:8080`). `wlan0` is UP with a
DHCP address on the test network.

## Between the host and the device: FAIL (network)

The host and the device are on different subnets, and the router does not pass traffic
between them in either direction:

| From | To | Result |
|---|---|---|
| host | device, ICMP | 100% loss |
| host | device, `adb connect <ip>:5555` | `Connection refused` |
| device | host, ICMP | 100% loss |
| device | host, TCP 22 | closed |
| device | its own gateway, ICMP | replies |

Before the Wi-Fi update test can run, the network has to change: either allow host-to-device
TCP 5555, or put the host and the device on the same network.

Update: I added a router rule for TCP 5555, and `adb connect <ip>:5555` then worked.

# Wi-Fi update test, run 1, 2026-11-21

Script: `wifi_ota.sh` (every device command goes to `adb -s <ip>:5555`). Bundles are in
`artifacts/phase-06/ota-wifi/`, built with `experiments/phase-05/ota/make_lab_ota.py` from
`artifacts/phase-06/images-cue/`, with the lab key and the `features-airplay2-drain` catalog:

| Bundle | Boot image | Transaction | sha256 |
|---|---|---|---|
| `good/lidar-lab-v0.2.18.ota.tar` | `boot-lidar-v2.img` `12f31aed…` (OTA profile) | `txn-8c5e49157168a61621c8c587` | `eeb0aa24…` |
| `rollback/lidar-lab-v0.2.19.ota.tar` | `boot-lidar-dev.img` `e0698350…` (development profile) | `txn-60c86390c5d1d1b63bd1affb` | `db3d07d0…` |

USB was not on the bus for either part: `adb devices -l` lists only the TCP transport in
`run1-good/devices.log` and `run1-rollback/devices.log`, and `lsusb` showed no Echo at 19:12.
So the USB safety net that `PLAN.md` asks for was not in place during this run.

## (a) Normal update: PASS

`run1-good/`. The unit started on slot A (v0.2.17). The push went over Wi-Fi (16.8 MB in
10 s), then `verify_rc=0`, `ota_manifest_signature=PASS`, `UPDATE_READY slot=b`,
`install_rc=0`. After the reboot, ADB over Wi-Fi was back on the second try (31 s), and the
unit reached the terminal confirmed state at 18:59:40: slot B, `state=installed`, and
`generation=` and `current=` both `txn-8c5e…`, with `slot_b_success=1` and no pending
transaction (`polls.log`, `state-after.log`).

## (b) Forced rollback: FAIL (test design), unit stranded on slot A

`run1-rollback/`. From confirmed slot B, the v0.2.19 bundle installed into slot A
(`UPDATE_READY slot=a`, `install_rc=0`), and the unit rebooted at 19:03:35. It never came
back: no TCP 5555 or 8080 answer and no USB device for about 9 minutes. The run was then
cancelled.

Cause: the development image's `/etc/libreecho/service-profile` is `diagnostic`, and
`libreecho-init:1784-1785` then skips the automatic Wi-Fi activation
(`wifi-network-policy-manual-single-shot`). That image therefore cannot come back on Wi-Fi.
It does not run the OTA confirm either, so nothing reboots it, and LK's tries are never used
up. The script checked that the image contains Wi-Fi tools, but not that it starts Wi-Fi.
This image has never been booted on hardware before.

Expected device state (not observed): slot A running the development image, A tries 2 left,
B confirmed (`txn-8c5e…`, v0.2.18). Recovery needs me: plug in USB so that
`adb reboot` can run until LK falls back to B, or power-cycle until it does (Step 4 needed
4 boots).

Next design for (b): use an OTA-profile image whose health confirm fails. That image keeps
Wi-Fi, and its init reboots on its own (`ota-health-confirm-failed-rebooting`), which
matches the real failure path.

## Recovery without USB: PASS (I power-cycle it)

USB stayed disconnected. I power-cycled the unit, and at 19:19:56 ADB over Wi-Fi was
back (`run1-recovery/state.log`, captured at 14 s uptime). The unit was on slot B
(`libreecho.lab=p6-v2`) with `slot_b_success=1`. Slot A was `0/0/0`: LK had used up its tries
and marked it unbootable. `libreecho-update status` showed `state=rolled-back` and
`ota_transaction_rollback=1`, and `generation=` and `current=` were both `txn-8c5e…`
(v0.2.18). `boot-health` still read `state=pending` with `pending_slot=a` that early in the
boot; this capture does not show its final value.

# Wi-Fi update test, run 2, 2026-11-21: (b) forced rollback PASS

run 2 (rollback), `wifi_ota.sh rollback`. USB was disconnected for the whole run; every
command went over Wi-Fi.

Bundle `artifacts/phase-06/ota-wifi/rbtest/lidar-lab-v0.2.20.ota.tar` (`91f935f4…`),
`txn-a952d12f57426d8bf6e7527c`. Its image `boot-lidar-rbtest.img` (`31c8ab5d…`) is the
images-cue v2 image with two test-only changes: in the ramdisk, the `status` action of
`etc/init.d/libreecho-web.init` always exits 1, and the cmdline tag is
`libreecho.lab=p6-rbtest`. The boot header id was recomputed. The kernel is unchanged. The
image keeps the OTA profile, so Wi-Fi and the health worker run normally, and only the
`web-status` probe fails. That image is a test fixture; it must never be shipped.

| Time | Event |
|---|---|
| 19:25:11 | Install from confirmed slot B: `verify_rc=0`, signature PASS, `UPDATE_READY slot=a`, `install_rc=0`. One host reboot, the only one in the run. |
| 19:26:13 | Boot 1: slot A, `p6-rbtest`, A tries 2. Reachable over Wi-Fi. |
| 19:30:51 | Boot 2: slot A, A tries 1. The unit rebooted itself. |
| 19:35:50 | Boot 3: slot A, A tries 0. The unit rebooted itself. |
| 19:40:49 | Boot 4: slot B, `p6-v2`. LK fell back. Reachable over Wi-Fi. |

On every candidate boot, the init log shows `ota-health-probe-failed:1..6:web-status` and
then the reboot (`polls.log`). The final state (`state-after.log`) is `state=rolled-back`,
with `restart_record` `reason=ota-health-confirm-failed`, `last_check=web-status` and
`pending_slot=a`. `generation=` and `current=` are both `txn-8c5e…` (v0.2.18), and B is
confirmed. `boot-health` still read `state=pending pending_slot=a` at capture time, which
matches the early-boot read after run 1's recovery.

Result: with (a) from run 1, both parts of the `PLAN.md` test passed over Wi-Fi, and nobody
touched the unit after the one host reboot. One deviation from the plan: USB was not
connected as a safety net. I chose to run without it after USB was lost during
run 1.
