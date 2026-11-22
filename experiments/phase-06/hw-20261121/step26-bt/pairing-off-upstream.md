# Step 26: pairing mode cannot be left after controller drift (upstream note)

Observed on the Lidar image (`lidar-lab-v0.2.21`, slot A) on 2026-11-21. This is
a general LibreEcho bug in the target-independent btd userspace, so it is
recorded here as an upstream note plus `btd-pairing-off-order.patch`; the Lidar
port does not carry it.

## Symptom and observed sequence

Owner enabled Pairing mode while `connectable=true, discoverable=true` (saved
at enable time). Later the kernel reported `connectable=false,
discoverable=false`; the trigger is unknown, but the btd log shows a rejected
`SET_DISCOVERABLE` at boot 953 and the owner may have switched "Accept incoming
connections" off. From that state every request to leave pairing mode failed.

`pairing-off.log` (btd adapter socket over Wi-Fi, no install):

```
before {"pairing_mode": true, "last_error": "MGMT opcode 0x0006 status 0x0b (rejected)", "connectable": false, "discoverable": false, "bondable": true}
set_connectable {"ok":true}
pairing_mode_off {"ok":true}      <- only after connectable was restored
set_discoverable_off {"ok":true}
after {"pairing_mode": false, "connectable": true, "discoverable": false}
```

The workaround confirms the ordering rule: `connectable true` must be sent
before the mode can be left, because the disable path tried the reverse.

## Root cause

`src/adapter/btd.c` at `abe8d9111cbc67f0221b404c51c4d9bd1cc9ce73`:

- `set_pairing_mode()` disable path, `src/adapter/btd.c:2039-2051`: restores
  `DISCOVERABLE(saved)` first, then `CONNECTABLE(saved)`.
- The kernel rejects `MGMT_OP_SET_DISCOVERABLE` with `MGMT_STATUS_REJECTED`
  (0x0b) while `HCI_CONNECTABLE` is clear, for either value of the request:
  `net/bluetooth/mgmt.c:1618` (6.18.64), `:1598` (6.1.178), `:1597` (3.18.19).
- Because the first restore fails, the `if (!result)` gate at
  `src/adapter/btd.c:2047-2051` skips clearing `pairing_mode` and the LED, so
  the mode stays on with no way out from the UI.
- The same out-of-order rollback exists on enable failure,
  `src/adapter/btd.c:2025-2032`, and can leave the adapter discoverable.
- `set_enabled(0)` at `src/adapter/btd.c:2092-2093` ignores the result of
  `set_pairing_mode(0)`. That was only safe because power-off follows; with the
  old latch it still left `pairing_mode` on when the restore failed.

## Fix (`btd-pairing-off-order.patch`)

Base: `abe8d9111cbc67f0221b404c51c4d9bd1cc9ce73` in `repos/LibreEcho-UI`.

- New `restore_pairing_settings()` restores the cached settings in a
  kernel-valid order:
  - saved connectable = 1: `SET_CONNECTABLE 1` then `SET_DISCOVERABLE(saved)`;
  - saved connectable = 0: `SET_DISCOVERABLE 0` then `SET_CONNECTABLE 0`
    (clearing visibility while page scan is still on). A refused visibility
    clear there is deliberately not reported: the subsequent
    `SET_CONNECTABLE 0` leaves the adapter not discoverable anyway.
  - `SET_BONDABLE(saved)` is independent of the rule and is always attempted;
    it can still fail the call.
- Both the disable path and the failed-enable rollback use the helper.
- Leaving pairing mode is now unconditional: `pairing_mode = 0` and the LED
  stop happen even when a restore fails. Decision: **clear the mode and LED,
  still return an error**. Pairing mode is userspace state whose stuck-on form
  is the unrecoverable failure (LED pulsing, toggle cannot be left); a refused
  visibility flag is a separate condition that must stay visible to the owner.
  The handler answers an error, `last_error` keeps the MGMT status, and the next
  `GET /api/v1/bluetooth` already reports `pairing_mode:false`, so the UI
  refresh shows the mode off while the failed flag remains visible.
- `set_pairing_mode(0)` while power is already off now clears the mode and LED
  and returns success instead of `-1`, so the ignored call at
  `src/adapter/btd.c:2092` cannot latch either.
- Deliberately not done: re-reading the live kernel settings on disable. The
  drift trigger is unknown, so the patch restores the owner's captured intent
  and does not pretend to repair state it cannot observe. That keeps the change
  small and reviewable.
- `tests/test_bluetooth_pairing_off_contract.sh` (registered in
  `tests/run_tests.sh`): source-level contract for the restore order, the
  unconditional clear, and the power-off path.
- `docs/API.md`: states the ordering rule and the error/still-leaves behavior.

This patch is independent of `btd-discoverable-connectable.patch` (the
standalone visibility toggle fix): their hunks in `btd.c` (1974/2036/2090 vs
2354) and `docs/API.md` (2215 vs 2202) are disjoint, and the two
`tests/run_tests.sh` insertions are five registry lines apart. Verified in both
application orders.

## Verification (host only, no device, no install)

Scratch worktree of `abe8d911`, `git apply --check`:

```
alone on abe8d911                     -> OK
after btd-discoverable-connectable    -> OK
discoverable patch after this one     -> OK
```

`make build/libreecho-btd`:

```
this patch alone                      -> exit 0
this patch + discoverable patch       -> exit 0
```

(warnings only: the pre-existing SBC/SIMD unused-parameter ones)

```
$ sh tests/test_bluetooth_pairing_off_contract.sh
bluetooth pairing-off contract: ok
$ sh tests/test_bluetooth_io_capability_contract.sh
bluetooth IO capability contract: ok
$ sh tests/test_bluetooth_discoverable_contract.sh   # together with the other patch
bluetooth discoverable contract: ok
```

Device behavior of the patched binary is unverified until an image with both
patches is built and installed.
