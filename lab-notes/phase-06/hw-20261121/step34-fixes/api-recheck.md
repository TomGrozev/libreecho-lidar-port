# Step 34: API recheck on Lidar (ApiRecheck)

Device <DEVICE_IP_A>, slot a, LibreEcho OS 0.14.5, kernel 6.18.64+, generation
`txn-47f1e4ac45f4d1d18417b8c8` (state `confirmed`). Recheck of the five items
fixed for the step 33 gaps. Only reversible writes were used: config import of
the same export, and BT discoverable on then off. No flash, no voice-pipeline
mode change.

The temporary account was `le-recheck34` (users file 143 -> 259 -> 143 bytes,
sha256 `c0a8c7a8…f45837` before and after). `web-config.json` sha256 stayed
`02f92aff…f1044`.

## Results

| # | Check | Result | Evidence | Detail |
|---|---|---|---|---|
| 1a | Baby monitor: listed source is `0:1` | PASS | `api/get_baby-monitor.json` | `sources[0].id = "0:1"`, 9-lane `pcm_s24_3le` source, 7 usable channels, calibration complete |
| 1b | Baby monitor: stream of the listed source returns PCM (non-silent) | PASS (quiet room) | `api/babymonitor-0_1.pcm`, `api/babymonitor-headers.txt` | `GET /baby-monitor/stream?source=0:1&channel=0` -> 200, 192512 bytes in 6 s, `pcm_s16_le;rate=16000;channels=1;selected-channel=shared-wake;calibration=applied`, rms 2.55, peak 20. No longer the step 33 400 "invalid channel". The room was quiet: rms 2.55 is below the step 33 heuristic (rms 8, peak 50), so a deliberate sound is still needed to call the level normal |
| 2a | Config export | PASS | `api/config_export.json` | 200, schema 1, 49 top-level keys |
| 2b | Import of that same export | PASS | `api/config_import_same.json` | 200, `error: null` (step 33 returned 501 `not_supported`) |
| 2c | `web-config.json` unchanged in meaning | PASS | `api/config-field-diff.json`, `api/web-config.before.json`, `api/web-config.after.json` | sha256 `02f92afff2d7…f1044` before and after, bytes identical; parsed config equal, re-export equal, 0 fields differ |
| 3a | BT discoverable on | PASS | `api/bt_discoverable_on.json`, `api/bt_after_on.json` | `PUT {"discoverable":true}` -> 200, discoverable=true, connectable=true |
| 3b | BT discoverable off | PASS | `api/bt_discoverable_off.json`, `api/bt_after_off.json` | `PUT {"discoverable":false}` -> 200, discoverable=false |
| 3c | BT connectable restored | PASS | `api/bt_before.json`, `api/bt_after_off.json` | connectable false (prior) -> true (while discoverable) -> false (restored) |
| 4 | Voice pipeline `restart.phase` present and idle | PASS | `api/voice_pipeline.json` | mode `home-assistant`, `restart.state=ready`, `restart.phase=""`, `error=""`; state not `pending` |
| 5a | `GET /light` returns a lux value | FAIL | `api/probe_get_light.json` (default state at the start of the recheck) | default: `lux=0`, `powered=false`, `visible=0`, `infrared=0`, `calibrated_lux=-1`. The endpoint and driver work (a reversible `als_power_state=1` produced lux 1121-1125), but the chip powers up off and nothing sets `als_power_state`, so the default reading is 0 |
| 5b | `/status` temperature and light | PASS | `api/probe_get_status.json` | `temperature_c=24` (nonzero), `light_lux=0` (`!= -1`); the 0 follows from 5a |

## Light sensor: why the default lux is 0, and the driver remove() defect

- The chip powers up off. `tsl2540_setup()` (`ams_tsl2540.c:593-603`) enables ALS
  only when `pdata->boot_on` is set; the Lidar DT node does not set it. With
  `als_power_state=0` the ADC channels read 0 and `als_lux` is 0. No daemon or
  init script writes `als_power_state`; `libreecho-web` only reads it
  (`src/backend_linux.c:821-828`). So `GET /light` is structurally correct but
  reports no measurement until something enables the sensor.
- The vendor driver cannot be unbound/re-bound safely. `tsl2540_remove()`
  (`ams_tsl2540.c:924-937`) unregisters only `p_idev` and frees the chip, but
  leaves the `tsl2540_attr_group`/`tsl2540_als_attr_group` sysfs files and the
  `a_idev` input device registered. A read after unbind dereferences the freed
  chip (`tsl2540_als_enable_show`, two oops traces), and a rebind fails
  `sysfs_create_group` with `-EEXIST` (`tsl2540_probe+0x524`).

## Reboot recovery attempt (owner-approved plain reboot)

The recheck tried to restore the chip with a plain `reboot` (no flash, slot a).
`reboot`, `reboot -f` and a further `reboot` all hung in `device_shutdown`
(three tasks in D state; load average rose above 11), and the boot id stayed
`edd0812d…3f84`. `/proc/sysrq-trigger` does not exist on this image;
`/dev/watchdog` (misc 10:130, 31 s) is held and fed by `libreecho-watchdogd`,
so it cannot force a reset. The boot id and generation never changed, so the
reboot did **not** happen. A physical power cycle is required.

After that, `/data` writes also stopped landing: `adb push` of `users.orig`
reported success but the file stayed 261 bytes, and a later push plus shell
read hung until timeout. The kernel is in `device_shutdown` with block I/O
stuck (`submit_bio_wait`, `folio_wait_bit_common` in D). Do not retry writes
over adb; power-cycle the device.

Until that power cycle the tsl2540 sysfs state is partial (`als_lux` and
`als_power_state` absent, `als_ch0`/`als_ch1` present) and `GET /light` cannot
produce a reading. This is confined to the ALS: the web API, config, BT,
voice-pipeline, audio and mic paths stayed healthy (`api/config_export.json`
after the incident already shows 200). The default `/light` and `/status`
values above were captured before the unbind/bind attempt, with no ALS writes.

## Commands

```
cd experiments/phase-06/hw-20261121/step34-fixes/ApiRecheck
adb -s <DEVICE_IP_A>:5555 forward tcp:18090 tcp:8080
python3 setup_account.py
SKIP_LIGHT=1 python3 recheck.py      # checks 1-4
python3 restore_account.py           # users file back to 143 bytes
```

## Pending after power cycle

No device commands may run until the owner power-cycles the unit. `api/.cred`
(mode 600) must stay until step 3 completes and must not be committed.

1. Reconnect and confirm the recovered boot. Expected: slot a, generation
   `txn-47f1e4ac45f4d1d18417b8c8`, `state=confirmed`, and a new
   `tsl2540 ... Probe ok.` line.

   ```
   cd experiments/phase-06/hw-20261121
   export PATH=$PWD/bin:$PATH
   adb connect <DEVICE_IP_A>:5555
   adb -s <DEVICE_IP_A>:5555 shell 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"; cat /data/libreecho/update/current /data/libreecho/update/boot-health; dmesg | grep -i tsl2540 | tail -n 10'
   ```

2. Record the default `/light` and `/status` with no ALS writes and no
   unbind/bind. Expected: `powered=false`, `lux=0`, `calibrated_lux=-1`,
   nonzero `temperature_c`, `light_lux=0` (`!= -1`). `light_check.py` writes
   `api/light.json` and `api/status.json`; point the 5a/5b rows of the table at
   those two files.

   ```
   adb -s <DEVICE_IP_A>:5555 forward tcp:18090 tcp:8080
   cd experiments/phase-06/hw-20261121/step34-fixes/ApiRecheck
   python3 light_check.py
   ```

3. Restore the users file byte-for-byte and restart the web daemon. Expected:
   143 bytes, sha256
   `c0a8c7a8113f096e3931cdd7607098e25fad9205e62a087e1835548147f45837`.

   ```
   adb -s <DEVICE_IP_A>:5555 push users.orig /data/libreecho/config/users
   adb -s <DEVICE_IP_A>:5555 shell 'chmod 600 /data/libreecho/config/users; wc -c /data/libreecho/config/users; sha256sum /data/libreecho/config/users; rm -f /data/libreecho/config/users.new143'
   adb -s <DEVICE_IP_A>:5555 shell '/etc/init.d/libreecho-web.init restart'
   rm -f api/.cred
   ```

## Cleanup status

- Temporary account still present: `users` is 261 bytes, sha256
  `d7641f6f…b602`, containing `le-recheck34`. The restore push reported
  success but did not land (see above); redo it with step 3 above.
- `web-config.json` unchanged at `02f92aff…f1044`; `web-config.json.bak`
  changed from `14dc981b…b1df` to `02f92aff…f1044` (the import backed up the
  current file before applying the identical export).
- BT left with discoverable=false, connectable=false (the values it started
  with).
- No voice-pipeline mode change, no flash, no successful reboot.
- Device is left needing a physical power cycle to restore the tsl2540 and to
  clear the wedged `/data` I/O; the web API still answered when last probed.
