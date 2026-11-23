# Bluetooth phone pairing and A2DP (owner), 2026-11-21

Result: PASS (owner: "Bluetooth works perfectly").

- At first the owner turned Bluetooth on but the phone did not list the unit. btd status then
  showed `discoverable=true`, `bondable=false`, `pairing_mode=false` and the controller default
  name `MTK MT7668 #4` (`owner-try.log`). The LibreEcho name and audio device class are set only
  by Pairing mode (`repos/LibreEcho-UI/src/adapter/btd.c:1936-2037`).
- With Pairing mode on, the phone found `LibreEcho`, paired, and played music.
- Status afterwards (`owner-a2dp-status.log`, addresses cut): `local_name=LibreEcho`,
  `pairing_mode=true`, one known device, A2DP sink and AVRCP registered,
  `last_disconnect_reason=remote-terminated (0x03)`. `last_error` still holds the earlier
  discoverable rejection (the upstream bug in `result.md`).
- AVRCP: PASS (owner). Play/pause and volume from the phone both work. btd logged absolute
  volume changes 30 to 54 (boot 969-984).
- Pairing mode could not be turned off from the web UI. When the owner tried, btd logged
  `SET_DISCOVERABLE rejected (0x0b)` at boot 1131 and 1140: `set_pairing_mode(0)` restores
  discoverable before connectable (`btd.c:2039-2046`), and connectable had been cleared during
  the session. Cleared at runtime with `pairing_off.py` (`pairing-off.log`): pairing mode off,
  connectable on, discoverable off. This is a general bug, recorded as an upstream note.
