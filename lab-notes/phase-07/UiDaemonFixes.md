# UiDaemonFixes: btd discoverable order and timed epoch persistence

Base commit (recorded before editing): `a9cea2ea5a0b605d574e1fb2ce9e407262c7fde3`
Branch: `fix/lidar-port-identity` (not committed; Main commits).

## Changes

### `repos/LibreEcho-UI/src/adapter/btd.c`

- `struct bt_context` (~line 271): added `discoverable_auto_connectable` so a
  standalone discoverable enable remembers that it turned connectable on
  implicitly and can undo that on disable.
- `handle_request`, `set_connectable` / `set_discoverable` branch
  (~2355-2415): switched from raw `controller_command` to
  `set_controller_setting` (same payload the pairing path uses) and ordered
  the requests the way `net/bluetooth/mgmt.c` requires:
  - enable: `SET_CONNECTABLE 1` (when not connectable) then
    `SET_DISCOVERABLE 1`;
  - disable: `SET_DISCOVERABLE 0` first, then `SET_CONNECTABLE 0` when this
    daemon had enabled it (or when it had to enable it just to satisfy the
    kernel).
  - standalone `set_connectable 0` now also clears the discoverable bit in
    `current_settings`, matching the kernel which clears it.
  Root cause: the kernel rejects `MGMT_OP_SET_DISCOVERABLE` with
  `MGMT_STATUS_REJECTED` while `HCI_CONNECTABLE` is clear, including for the
  disable request (kernel 6.18 `mgmt.c:1621-1625`). This is the 501 seen in
  `step33-gap-checks/ApiSweep`.

### `repos/LibreEcho-UI/src/adapter/timed.c`

- New option `--epoch-file PATH` (default `/data/libreecho/config/time-epoch`,
  env `LIBREECHO_TIME_EPOCH`).
- `read_epoch_file`, `persist_epoch`, `restore_persisted_clock` (after
  `ensure_rtc_node`): strict one-line parse, rejects epochs before
  `VALID_CLOCK_EPOCH`, atomic write via temp + `rename`.
- `sync_hook`: always persists the synchronized epoch; when no RTC exists it
  reports `rtc_persisted=0`, leaves `last_error` empty, logs "not available"
  and returns success instead of setting `RTC persistence failed`. RTC boards
  keep the previous hwclock result and return code.
- `main`: when no RTC and the clock is invalid at startup, restores the
  persisted epoch with `clock_settime` and records `source=persisted` and
  `last_sync_epoch`; later status writes reuse that source. MT8163 keeps
  `source=rtc`/`unset` exactly as before.

### Tests

- `tests/test_timed_epoch.c` (new): persist/read round-trip including atomic
  rewrite, rejection of short, non-numeric, trailing-garbage and pre-2020
  values; pre-2020 epochs are not written.
- `tests/test_timed.sh`: runs under a temp epoch path; new no-RTC run asserts
  `state=synchronized`, `rtc_available=0`, `rtc_persisted=0`,
  `last_error=` empty, and a persisted epoch file.
- `tests/test_bluetooth_discoverable_order.c` (new): compiles `btd.c`, fakes
  the management channel with a socketpair and asserts the exact opcode order
  `0007 1 / 0006 1 / 0006 0 / 0007 0` for a non-connectable controller and
  `0006 1 / 0006 0` for an already-connectable one.
- `tests/run_tests.sh`: builds and runs both new tests.

## Verification (host, run at the end)

```
make -B build/log.o build/libreecho-timed build/libreecho-btd   # ok
cc ... tests/test_timed_epoch.c src/log.c -o build/test-timed-epoch
./build/test-timed-epoch            # timed epoch persistence: ok
sh tests/test_timed.sh              # ok (incl. no-RTC case)
sh tests/test_timed_timeout.sh      # ok
cc ... tests/test_bluetooth_discoverable_order.c ... -o ...
./build/test-bluetooth-discoverable-order  # ok
./build/test-bluetooth-status-capacity     # ok
./build/test-bluetooth-bond-persistence    # ok
sh tests/test_bluetooth_*_contract.sh ...  # pairing, io capability, mgmt
                                           # observability, profile, profile
                                           # service, device metadata, factory
                                           # reset: all ok
```

Note: `build/log.o` was a stale ARM object in the shared tree; rebuilt with
`make -B build/log.o` (host x86-64). Not committed.
