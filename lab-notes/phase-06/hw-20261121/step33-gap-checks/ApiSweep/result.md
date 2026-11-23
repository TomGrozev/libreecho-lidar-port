# Step 33: device API sweep on Lidar (ApiSweep)

Device <DEVICE_IP_A>, LibreEcho OS 0.14.5, slot a, adb over TCP. Owner-approved
reversible API/config writes only; every mutation was re-read and restored.
Temporary account `le-sweep33` (users file 143 -> 259 -> 143 bytes, sha256
`c0a8c7a8…f45837` before and after, `user_count` back to 1, web daemon
restarted each way). `web-config.json` sha256 stayed
`02f92aff…f1044`; the config export/import test wrote nothing.

## Results

| Feature | Result | Evidence | Root cause or fix proposal |
|---|---|---|---|
| Volume set/get | PASS | `api/ws_volume_set10.json`, `ws_volume_set0.json`, `ws_volume_restore.json`: 50 -> 10 -> 0 -> 10 -> 50 | n/a |
| Test tone endpoint | PASS (audible) | `api/ws_audio_test_tone.json` 200 `{"playing":true}` at volume 10 | n/a |
| Announcement endpoint | N/A (mode) | `api/ws_audio_announce.json` 501 `io_error`; `ps` has no `libreecho-ttsd`; `GET /voice-pipeline` mode `home-assistant` | Expected: HA mode keeps local ttsd stopped; `announce` targets audiod's warm TTS (`backend_linux.c:1390-1401`). A clearer `not_supported` would be better than `io_error` |
| Announce stop | N/A (same) | `api/ws_audio_announce_stop.json` 501 | n/a |
| Mic gain set/get | PASS (PGA-quantized) | `api/ws_micgain_set.json`, `ws_micgain_restore.json`: 65 -> request 67 -> readback 68 -> restore 65 | Gain maps to discrete ADC PGA steps (Lidar 4-PGA path); readback reports the applied step, not the request |
| Mic mute set/get | PASS | `api/ws_micmute_set.json`, `ws_micmute_restore.json`: false -> true -> false | n/a |
| Microphone listing | PASS | `api/get_baby-monitor.json`: `available:true`, 7 channels, 9-lane `pcm_s24_3le` source `0:24`, calibration complete | n/a |
| Beam listing/direction | PASS | `api/get_microphones_beams.json`: `running:true`, 12 beams, hop 8 ms, `doa_deg:306.3` | n/a |
| Baby-monitor stream | **FAIL** | `api/babymonitor-capture.log`: `source=0:1` streams `pcm_s16_le;rate=16000;channels=1;selected-channel=shared-wake` (2 s, rms 8.2, peak 116); `source=0:24` -> 400 "The selected Echo microphone channel is invalid"; `api/babymonitor-0_1.pcm` | `baby_monitor_local_json` advertises micd's `sources[].id` (`0:24`) but `api_baby_monitor_stream_authorize` (`src/api.c:2937`) requires `profile->capture_card/device`, which is `0:1` in `/etc/libreecho/audio-profile`. Fix: advertise `capture_card:capture_device`, or accept a listed source by mapping it to the profile. Same defect exists on MT8163 (two different device numbers) |
| LED profile set/get | PASS | `api/ws_led_profile_set.json`, `ws_led_profile_restore.json`: listening {72,185,255,100} -> {200,100,50,90} -> restored | n/a |
| LED visualizer setting | PASS | `api/ws_led_visualizer_set.json`, `ws_led_visualizer_restore.json`: true -> false -> true | n/a |
| Button mappings | PASS | `api/ws_buttons_set.json`, `ws_buttons_restore.json`: action_brightness 70 -> 71 -> 70, other mappings unchanged | n/a |
| Hostname get/set-restore | PASS | `api/ws_hostname_set.json`, `ws_hostname_restore.json`: echo -> echo-api (kernel `hostname` echoed it) -> echo | n/a |
| Config export | PASS | `api/ws_config_export.json`: schema 1, 49 fields | n/a |
| Config import of same export | **FAIL** | `api/ws_config_import_same.json`: 501 `not_supported` "Configuration restore is unavailable for this backend" | `import_configuration` returns `LE_NOT_SUPPORTED` for every non-mock backend (`src/api.c:1767`). The apply path is implemented; remove the guard or gate it on capability |
| Appearance ui_theme/color_mode | PASS | `api/ws_ui_theme_set.json`, `ws_ui_cmode_set.json`, `ws_ui_restore.json`: classic->setup->classic, ''->light->'' | n/a |
| BT scan list | PASS (empty) | `api/ws_bt_scan_start.json` 200, `ws_bt_after_scan.json` completed with `discovered:[]` | Scan end-to-end works; no device found in this environment, as in step 15. `known_devices` still lists one phone |
| BT scan stop after window | PASS (expected 501) | `api/ws_bt_scan_stop.json` 501 "could not stop" | Inquiry already ended; same as step 15. A 409/no-op would be clearer |
| BT `discoverable:true` | **FAIL** | `api/ws_bt_discoverable.json` 501; capabilities `connectable:false discoverable:false` after | btd's standalone `set_discoverable` (`src/adapter/btd.c:2355-2378`) sends `MGMT_OP_SET_DISCOVERABLE` without first setting connectable; kernel `mgmt.c` rejects it with `MGMT_STATUS_REJECTED`. Pairing mode does it in order (`btd.c:2022-2024`). Fix: in the `set_discoverable` branch, on enable send `MGMT_OP_SET_CONNECTABLE 1` first and restore the previous connectable on disable |
| Wi-Fi scan (read-only) | PASS | `api/ws_wifi_scan.json`: 11 networks, 5 GHz strongest -42 dBm; no connect | n/a |
| HA restart state machine | FAIL (design) + diagnosis | `api/ws_voice_pipeline_final.json`: now `ready`, mode `home-assistant` | See below |

## HA `restart.state: pending` diagnosis (source only; no mode toggled)

`voice_pipeline_restart_reap` (`src/api.c:481-521`) waits non-blocking on one
direct child pid. `pending` is reported while `waitpid` says that child is
alive (`api.c:529-536`). A **failed** forward transition does not end the job:
the reap restores the saved mode and forks a *second* rollback restart
(`api.c:501-519`) that stops esphomed and starts agentd/sttd/ttsd. That rollback
is what step 29 saw for ~40 s: its own log shows ttsd taking 36 s to become
ready (`step29-features/ha-restart-busy.log`). So the state was not leaked; it
was the rollback, and the owner's enable inside that window correctly got 409.
Step 22's later GET shows `ready`, confirming it resolved.

Real defects found in the path:

1. No bound on either child. `voice_pipeline_restart` calls
   `le_service_command`, whose `waitpid(child, &status, 0)` (`src/service_env.c:136-155`)
   has no timeout. One wedged init script keeps `restart.state` at `pending`
   forever, since `pending` is only cleared by a child exit.
2. `pending` conflates "starting the requested mode" with "rolling back after a
   failure". The API returns the same 202/409 and the same state for both; the
   rollback also silently reverts `mode`, which the client never sees as a state.
3. Only an API request reaps (`api.c:2932`, `voice_pipeline_restart_pending`).
   A job that exits between requests is left a zombie until the next request;
   step 29's `[libreecho-web]` entry in `ps` is exactly that. The parent's
   SIGCHLD handler (`http_server.c:87-91`) only tracks registered worker pids,
   not this one.
4. A GET (`voice_pipeline_json` -> reap) can fork the rollback restart: a
   read request with a write side effect.

Proposed fix: give the job a monotonic deadline (e.g. 90 s) and use
`le_service_command_cancellable` with a per-command timeout; add
`restart.phase` = `starting` / `rolling-back` to the GET; reap in the
once-a-second server tick rather than only on requests; on deadline, kill the
child's process group, set `failed` with a timeout error, and expose the
restored mode. Keep the "always attempt the starts" rule in
`voice_pipeline_restart` unchanged.

## Audible checks for the owner

- Test tone `POST /audio/test` at volume 10 (200; should have been a quiet
  beep/cue).
- Announcement `POST /audio/announce` produced no sound: 501, no ttsd in
  home-assistant mode. Nothing to confirm by ear.

## Side effects and cleanup

- Temporary account removed, users file restored byte-for-byte
  (sha256 `c0a8c7a8…f45837`), web daemon restarted, `user_count` 1.
- Volume 50, mic gain 65, mute false, LED colour/brightness, visualizer true,
  button brightness 70/60, hostname `echo`, appearance classic/'' all re-read
  at baseline. `web-config.json` hash unchanged.
- `api/babymonitor.pcm` (empty, failed 0:24 attempt) and the two captures
  remain under `api/`; they contain room audio, stay local.
- No commits.
