# Step 26: btd `discoverable` returns 501 on Lidar: root cause and fix

Read-only device work. No reboot, no install, no pairing, no audible output.
Bluetooth settings were toggled through btd's own adapter socket over Wi-Fi and
restored to the exact pre-test values.

## Symptom

`PUT /api/v1/bluetooth {"discoverable":true}` returns HTTP 501 on the Lidar
image (`experiments/phase-06/hw-20261121/README.md`, Step 15). The same call
with `discoverable:false` also fails.

## Reproduction (Wi-Fi, real btd socket)

`adb forward tcp:19999 localfilesystem:/run/libreecho/bluetooth.sock` exposes
the adapter socket the web backend calls (`src/backend_linux.c:2240-2242` builds
exactly `{"enabled":true}` for command `set_discoverable`).
`repro_btd_discoverable.py` → `repro.log`:

```
set_discoverable true  -> ok:false "Bluetooth controller setting failed"
status                 -> last_error "MGMT opcode 0x0006 status 0x0b (rejected)"
set_discoverable false -> ok:false
set_connectable true   -> ok:true
set_discoverable true  -> ok:true
status                  -> connectable:true discoverable:true
restore                 -> connectable:false discoverable:false (baseline)
```

`0x0006` is `MGMT_OP_SET_DISCOVERABLE`, `0x0b` is `MGMT_STATUS_REJECTED`.
After a failed request btd surfaces the kernel status in `last_error`; the web
backend collapses `ok:false` to `LE_IO` (`src/backend_linux.c:466-473`) and the
API maps any non-`LE_INVALID` result to 501 (`src/api.c:2303`, the
`/api/v1/bluetooth` PUT branch), which is the reported symptom.

## Root cause

The kernel refuses `SET_DISCOVERABLE`, for both `val=0` and `val=1`, while
`HCI_CONNECTABLE` is clear:

- Lidar running kernel 6.18.64: `repos/LibreEcho-Linux-618/net/bluetooth/mgmt.c:1618`
- MT8163 6.1.178 kernel: `repos/LibreEcho-Linux/net/bluetooth/mgmt.c:1598`
- older 3.18.19 tree: `repos/LibreEcho-Platform/net/bluetooth/mgmt.c:1597`

btd powers the controller itself and never sets page scan, so `CONNECTABLE` is
false (`hci_update_passive_scan_state`, `net/bluetooth/hci_core.c:651`). Its
standalone `set_discoverable` handler sent `MGMT_OP_SET_DISCOVERABLE` directly
without enabling connectable first:

- `repos/LibreEcho-UI/src/adapter/btd.c:2355-2391` (base `abe8d91`), the
  `set_connectable`/`set_discoverable` branch.
- The pairing-mode path already does it correctly in order
  (bondable → connectable → discoverable), `src/adapter/btd.c:2018-2032`, which
  is why pairing mode works.

The mock backend accepted `discoverable` unconditionally
(`src/backend_mock.c:121`), so `tests/test_api.sh` never saw the kernel rule;
the btd source path had no contract test.

## Classification: general LibreEcho bug, not a Lidar port issue

The failing code is target-independent userspace (`src/adapter/btd.c`), the same
request is rejected by all three kernel trees this project ships, and the
handler has no `mainline_hci_target()`/WMT branch. MT8163 would hit it too the
moment anyone sets "Visible to nearby devices" without first setting "Accept
incoming connections"; it is latent there because that toggle was evidently
never exercised alone. Lidar only made it visible because its mainline
`btmtksdio` transport is the first path where btd brings `hci0` up itself and
the Step 15 test drove the standalone toggle. The kernel check itself is
upstream mainline semantics, not Lidar hardware or driver behaviour.

## Fix

`btd-discoverable-connectable.patch` (applies to `repos/LibreEcho-UI` at
`abe8d9111cbc67f0221b404c51c4d9bd1cc9ce73`, `git apply --check` passes):

- `src/adapter/btd.c`: in the combined handler, when the request is
  `set_discoverable` and the controller is not connectable, first issue
  `MGMT_OP_SET_CONNECTABLE 1` (BlueZ's "discoverable" mode also enables page
  scan). A disable request in that state is already satisfied and answers
  `{"changed":false}` without a controller command. Both final settings go
  through `set_controller_setting`, so btd's cached state updates at once
  instead of waiting for the MGMT settings event.
- `src/backend_mock.c`: mirror the kernel rule (enable implies connectable,
  disabling connectable clears discoverable) so API tests model reality.
- `tests/test_bluetooth_discoverable_contract.sh` (registered in
  `tests/run_tests.sh`): source-level regression contract for the ordering.
- `docs/API.md`: document the implication.

Host verification in a scratch worktree of `abe8d91`:
`make build/libreecho-btd` succeeded (warnings only, pre-existing SBC ones) and
`sh tests/test_bluetooth_discoverable_contract.sh` printed
`bluetooth discoverable contract: ok`. The image was not rebuilt or installed;
device verification of the patched binary is unverified until Main integrates
and an OTA lands.

## Tom steps: phone A2DP test (remaining Step 15 item)

Run later, when sound is allowed. One phone, low volume.

1. Confirm the device is on a confirmed slot with Bluetooth up:
   `adb -s <ip>:5555 shell 'cat /run/libreecho/bluetooth-ready'` and in the web
   UI Bluetooth shows state `up`, HCI `hci0`.
2. On the device UI: Bluetooth → **Pairing mode** on (yellow breathing LED
   starts). With the patch applied, turning on "Visible to nearby devices"
   alone is equivalent; leave "Accept incoming connections" on.
3. On the phone: Settings → Bluetooth → pair a new device → choose
   `LibreEcho` (`local_name` shown in pairing mode). If a numeric code appears
   on either side, confirm it on both.
4. Set the phone's media volume to its lowest non-zero step, then play a track.
   Raise the phone volume gradually to a comfortable level. Audio should come
   from the Echo speaker; the device UI should show the phone connected and
   streaming.
5. Press play/pause and next on the device UI (AVRCP) and confirm the phone
   follows.
6. Leave pairing mode off when done; the phone stays bonded. Record: phone
   model and OS, pairing result, whether audio was heard, AVRCP result, and a
   `GET /api/v1/bluetooth` snapshot (connected device, not the full address in
   commits). If no audio: note whether the UI shows `streaming`, and keep the
   btd log.

## Final device state

Unchanged from before the test: slot B, `6.18.64+`, `target_id=lidar`, btd
`state=up enabled=true hci0`, connectable/discoverable/bondable all false,
`last_error` empty. The `adb forward` tunnel was added on the host only.
