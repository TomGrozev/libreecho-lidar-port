# Step 29: LibreEcho feature sweep on Lidar

Device <DEVICE_IP_A>, Image "LibreEcho OS 0.14.5", kernel 6.18.64+.
Owner was using the web UI during this step, so API writes stopped after the HA
check. Read-only device inspection continued.

## Results

| Feature | Result | Evidence | Fix class |
|---|---|---|---|
| Inventory of documented features | PASS | `inventory.md` from README table, ARCHITECTURE, API and OpenAPI | n/a |
| Web daemon, config, users auth | PASS | login 200, `user_count: 1` restored, API reachable on 8080 | n/a |
| Home Assistant mode: esphomed installed and started on enable | PASS (corrected 2026-11-22) | `ha-result.md` owner enable via runtime shim; v0.2.23 `esphomed-checks.log`: `ready:true connected:true`, port 6053; owner confirmed voice commands work | n/a |
| ESPHome Noise handshake from host | PASS (owner HA session) | `step30-identity/esphomed-checks.log`; owner's Home Assistant is the peer (`GET /voice-pipeline`: `home_assistant.connected:true ready:true`) | n/a |
| TCP 6053 through the router | no (closed before and after) | python connect_ex 111 from host | Port |
| HA restart state machine resolves | FAIL | GET stayed `restart.state: pending` for 40 s after the child failed | Upstream plus port |
| Bluetooth page toggles | PASS (source) | `web/js/bluetooth.js:77` connectable, `:78` discoverable, `:79` `/bluetooth/pairing-mode` | n/a |
| Pairing mode publishes LibreEcho name, audio-sink UUID, device class | PASS (source), device unverified | `src/adapter/btd.c:1936` `set_pairing_identity`, MGMT_OP_SET_LOCAL_NAME, ADD_UUID, SET_DEV_CLASS | BT transport |
| Bluetooth controller on target | PASS (corrected 2026-11-22) | owner: phone pairing, A2DP and AVRCP work; `libreecho-btd` running, `/run/libreecho/bluetooth-ready` present; coexistence step 10/15 | n/a |
| LED API and test | PASS (prior run) | step13 `api-test.log`: GET/PUT/test 200, `ledd` running | n/a |
| Timers and alarms create/delete | not run | `timerd` running, `/run/libreecho/timer.sock` present; API write needs owner session | n/a |
| Internet radio | partial | `radiod` running, radio socket present; station file 48 bytes (empty list); streams need internet | blocked-internet |
| AirPlay receiver process | PASS | `shairport-sync` pid 11289, TCP 7000, `/run/libreecho/airplay.sock` | n/a |
| AirPlay or ESPHome mDNS advertisement from host | blocked | host avahi daemon stopped; raw mDNS query got no answers for `_airplay`, `_raop`, `_esphomelib` (`mdns-probe.log`) | needs host mDNS |
| Sendspin | PASS | `libreecho-airplayd.log`: Noise transport active, connection admitted | n/a |
| Spotify status | not run | needs authenticated GET | n/a |
| Privacy hardware input | PASS (corrected 2026-11-22, v0.2.23) | `step30-identity/privacy-checks.log`: `/sys/devices/platform/amz_privacy/privacy_state` reads 0; `buttond-status` reports `privacy_state=0`; esphomed connected | n/a |
| USB storage | FAIL (no mount) | `/storage/usb` absent, no USB mass-storage mount | Port |
| Update helpers | PASS (presence) | `libreecho-bootctl`, `libreecho-update`, `libreecho-update-fetch` in `/usr/local/sbin`; API status not queried | n/a |
| Logs and diagnostics | partial | `/var/log/libreecho/system.log` active, `libreecho-logd` socket present; API not queried | n/a |
| Wake word daemon and model | PASS (process) | `libreecho-waked` with `openwakeword` payload; API not queried | n/a |
| Night mode, sleep light, idle mode | not run | needs authenticated PUTs | n/a |

## Root causes found

1. HA satellite MAC. `esphomed` takes the device MAC from config `wifi_mac` or
   idme fields `mac_addr`, `macaddr`, `wifi_mac`, `wifi_mac_addr`, `mac`
   (`src/adapter/esphomed.c:278`). This Lidar's idme values are all the two-byte
   string `0`; every mac field is empty. `wlan0` does have a factory unicast
   MAC. Two port fixes: persist `wifi_mac` in `web-config.json` during
   provisioning, or add a `/sys/class/net/wlan0/address` fallback. A live MAC
   fallback should be documented as less stable.
2. HA restart pending. `voice_pipeline_restart_reap` (`src/api.c:481`) left
   `restart.state` at `pending` after the child failed; the child had no visible
   process. Main is investigating.
3. Privacy node name. Lidar uses `amz-privacy` (hyphen), the daemon default is
   `amz_privacy` (underscore). Fix the init default or add a DT alias; check
   every daemon that reads the privacy node, not just esphomed.

## Side effects and cleanup

- A temporary API account (`phase6-sweep`) was added to exercise the API. The
  users file was restored byte-for-byte, the daemon restarted, and `user_count`
  is 1 with the owner line intact. A copy of the restored file remains at device
  `/tmp/le-users.step29bak` because host `rm` was approval-blocked.
- The HA enable rolled itself back to `local`; `voice_pipeline_mode: local`,
  `integrations: 92`.
- The failed esphomed start generated and persisted `esphome_noise_key` in
  `web-config.json` (absent before). The key was never printed.
- No Bluetooth writes were made.

## Re-sweep 2026-11-22 (OTA v0.2.23, slot b, txn-4f85bab71d5fe826cd0b0a1c)

Image `0.2.23`, kernel 6.18.64+, slot b confirmed. The stale rows above are corrected in
place: Bluetooth controller, Home Assistant mode/Noise, and the privacy node all pass now.
Evidence for this pass is in `20261122/` (`device-state.log`, `mdns-browse-types.log`,
`timer-socket*.log`, `api/*.json`, `api/sweep-summary.log`). Every write below was reverted
and re-read; the timers never reached zero.

| Feature | Result | Evidence | Class |
|---|---|---|---|
| Timers and alarms create/delete | PASS | `timer-socket.log`, `timer-socket-delete.log`: countdown id 1 and alarm id 2 created, listed pending, cancelled, list empty; API `timer_create` 201 and `timer_delete` 200 (`api/*.json`) | n/a |
| Night mode round-trip | PASS | `api/night_get.json` `enabled:true` then `api/night_get_restored.json` `enabled:false` (baseline) | n/a |
| Sleep light round-trip | PASS | `sleep_get.json` `mode:pulse active:true`; restored `mode:off` in `sleep_get_restored.json` | n/a |
| Idle mode round-trip | PASS | `idle_get.json` `idle_mode:always`; restored `indicator` in `idle_get_restored.json` | n/a |
| Wake word settings | PASS | `wakeword_set` 200, `wakeword_get_changed` sensitivity 71, restored 68; model `Alexa`, `inference_active:true`, 9488 frames | n/a |
| Logs and diagnostics endpoints | PASS | `get_diagnostics` 200, `get_diagnostics_kernel` 200, `get_events` 200, `logd` running with `/run/libreecho/log.sock`; note `/logs?limit=40` was rejected 404, plain `/logs` not re-queried | n/a |
| Updates page/API (read-only) | PASS | `get_system_update.json`: `installed_version 0.2.23`, channel stable, authority provenance lists all five feature manifests; `/system/boot` 200; no apply/check-install issued | n/a |
| Privacy and mute state | PASS | `amz_privacy/privacy_state` = 0, `buttond-status` `privacy_state=0 microphone_mute=1`; `GET /privacy` 200 (retention `none`, diagnostics off) | n/a |
| mDNS advertisements | PASS | On-device `avahi-browse --resolve` (`mdns-browse-types.log`): `_airplay._tcp` echo:7000, `_raop._tcp` <MAC_WLAN_A_COMPACT>@echo:7000, `_esphomelib._tcp` echo:6053 with `mac=<MAC_WLAN_A>`, `_sendspin._tcp` echo:8928. Host is <LAN_HOST_B_1>/26 behind <LAN_GATEWAY_B> while the device is <DEVICE_IP_A>/24, so the query ran on the device inside `/usr/local/lib/libreecho-mdns/root` | n/a |
| Spotify Connect | FAIL | `get_spotify.json`: `installed:false status:unavailable`; no `libreecho-spotifyd` in `/usr/local/sbin`; no `_spotify-connect._tcp` answer; `/run/libreecho` has no spotify socket | image payload (daemon not packaged) |
| Sendspin (Music Assistant) | PASS | `get_sendspin.json`: `installed:true running:true state:connected server:"Music Assistant (…)" time_synced:true`; pid 9237 listens on 8928; `_sendspin._tcp` advertised | n/a |
| USB storage | N/A | Lidar exposes only the micro-USB service/OTG port; our DTS pins it peripheral: `repos/LibreEcho-Linux-618/arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:491-493` (`dr_mode = "peripheral"`). API correctly reports `present:false` with "The OTG port must be in host mode" | n/a (hardware) |
| Internet radio | blocked-internet | `radiod` running with `radio.sock`; `radio-stations.json` `station_count:0`; no WAN | blocked-internet |
| LibreEcho News | blocked-internet | `GET /news` 200; feed refresh needs the blocked WAN | blocked-internet |
| Timezone / NTP | blocked-internet (partial) | `time.status`: `state=retrying synchronized=0 source=rtc`, servers list present; also `last_error=RTC persistence failed rtc_available=0` | blocked-internet; RTC note below |
| GPT-Live (`lived`) | N/A | not shipped in this image: no `libreecho-lived` binary and no `/run/libreecho/live.sock`; README says disarmed by default | n/a |
| Local assistant (`agentd`) | not run (HA owns voice) | `get_voice-pipeline.json` `mode:home-assistant`, `GET /assistant` 503 `not_supported`, `agentd` not in `ps`; features `assistant/stt/tts` are `effective:present`. This is the PLAN:607 item, untested here | needs-owner (PLAN:607) |
| Baby monitor, mic beams, playback, network, Bluetooth, light, preferences, provenance, status | PASS (read) | all `GET` 200 in `api/sweep-summary.log`; hardware behavior covered by earlier steps | n/a |

### Lidar-specific gaps

1. **Spotify Connect is not in the image.** `repos/LibreEcho-UI/src/backend_linux.c:2568`
   probes `/usr/local/sbin/libreecho-spotifyd`; the OTA's feature catalog carries only
   airplay2, tts, wakeword, stt and assistant. Proposed fix (not built): add the Spotify
   daemon to the audio/airplay feature payload, or declare the integration absent in the
   Lidar catalog so the API and UI stop offering it. No port code change is needed.
2. **RTC persistence fails on this board** (`time.status` `rtc_available=0`,
   `last_error=RTC persistence failed`). With no WAN, `timed` has no valid wall-clock source,
   so timers/alarms that persist across reboot depend on it. Proposed: treat MT8167 as
   NTP-only and keep the last valid epoch in userdata, or bind an RTC driver if one exists.
   Not proven to break the live timer path (timers worked in-session).

### Audible or physical checks still needed (owner)

- Local wake word: say "Alexa" in `local` mode and confirm a full turn (PLAN:607); not
  exercised because HA owns voice now.
- Timer ring and dismiss: let a short countdown reach zero, say stop, confirm silence.
- Internet radio: play one real station once a WAN exists.
- Spotify Connect: requires an account, internet, and the missing daemon.
- Night/sleep/idle LEDs: visual confirmation of the dim schedule and sleep pulse.

### Side effects and cleanup (2026-11-22)

- Temporary account `le-sweep22` was appended, the web daemon restarted, and the original
  users file pushed back byte-for-byte: sha256
  `c0a8c7a8113f096e3931cdd7607098e25fad9205e62a087e1835548147f45837` before and after
  (the owner's single account, 143 bytes), web `status` running. No credential was printed.
- All LED, sleep, idle and wake-word values re-read at their pre-test values; the LED colour
  and brightness were never changed.
- Device `/tmp/le-users.step29bak` and `/tmp/le_sock_cmd` remain: device-side `rm` was
  approval-blocked. Both are under `/tmp` and vanish on reboot.
- Test helper: `20261122/le_sock_cmd.c` (static ARMv7) used only against `timer.sock`; the
  socket is stream-based and no shell client for it exists in the image.

### Spotify classification (Main, 2026-11-22)

Not a Lidar port failure. No repository here builds `libreecho-spotifyd` or librespot
(searched `repos/LibreEcho-Platform`, `repos/LibreEcho-UI/Makefile`,
`experiments/phase-06/build_components.sh`), so MT8163 images lack it too. The API already
reports the missing daemon (`src/backend_linux.c:2575-2589`). Recorded as N/A for this port and
as a LibreEcho gap upstream.
