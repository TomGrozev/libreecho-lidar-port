# Step 23: recovery entry (Action held at power-on)

Result: PASS on the third attempt. Log: `fastboot.log`. Watcher: `watch.sh` (read-only).

- Attempts 1 and 2: I held Action while plugging in for about 2 s, then about 5 s. Both
  booted LibreEcho normally on slot A (`bootreason=power_key`); fastboot never appeared.
- Attempt 3: the power lead was unplugged for 10 s, Action (the dot) was held before and for
  10 s after plug-in. Kaeru fastboot appeared (`kaeru-version: 2.0.0-g66704e6-dirty`) at
  18:39:43. `getvar current-slot` returned empty, a Kaeru reporting gap.
- `fastboot reboot` → LibreEcho, slot `_a`, `selected_slot=a`, both slots marked successful,
  update state `installed`. No writes.

Working instruction: unplug for 10 s, hold Action, plug in, keep holding for 10 s.
Unverified: whether the short drain or the short hold caused the first two misses.
