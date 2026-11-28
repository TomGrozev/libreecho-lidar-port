# Reference-stage fastboot entry

`experiments/phase-03/enter_fastboot.py` is the portable form of the 2026-11-15 hardware
run. Run the commands from the workspace root.

The script loads the pinned Kamakiri stage 1 and stage 2 images, sets watchdog bit 2 at
`0x10007024`, and reboots. It does not write eMMC, MISC, BCB, or any partition. The
preserved run reached Kaeru fastboot with `unlock_status: true`.

## Approval and power handling

Get explicit approval from Tom before you run the device command.

For a cold BROM entry, remove power and disconnect USB first. Reconnect USB only after the
unit is fully off, then start the device command.

Do not power-cycle the unit during the watchdog warm reboot. A power removal in that window
clears the WDT flag, and the unit will not enter fastboot.

### Physical sequence for a fastboot session

On this unit, a warm reboot from USB alone does not hold the fastboot state: a 2026-11-15
session lost it after a USB-only warm reboot. Reaching Kaeru fastboot required the Action
button held and mains connected before USB, with the listener running before the device was
connected. Plan every fastboot session with that order:

1. Hold the Action button.
2. Connect mains power while the button is held.
3. Connect USB last, with the BROM command or fastboot listener already running.

After a successful warm reboot into Kaeru fastboot, the device stays in fastboot as long as
that sequence was followed; a reboot over USB alone can drop back out of it.

## Host check

```
python3 experiments/phase-03/enter_fastboot.py --verify-only
```

This command checks that `brom-payload/stage1/stage1.bin` and
`brom-payload/stage2/stage2.bin` exist with the expected sizes and SHA-256 digests. It
exits with status 0 on success and 1 on a mismatch. It uses only the standard library, and
it does not import the reference kit or pyusb, open USB, or look for a device.

## Device run

```
uv run --with pyusb python experiments/phase-03/enter_fastboot.py
```

The script verifies the stages before it imports the kit. A missing file or a hash
mismatch stops the run before any USB access. On success the script finds the BROM device,
loads stage 1 and stage 2, sets the fastboot flag, and sends the reboot command.

The kit needs its own `third_party` directory as the current directory and its Kamakiri
modules on `sys.path`; the script sets both. It also replaces the kit's test-point input
wait with an already-removed stand-in, because this unit has no test point. The rest of the
kit sequence is unchanged.

After the warm reboot, fastboot should report `product: LIDAR` and
`unlock_status: true`.

The local host fastboot build is not portable tooling and its specifics are not device
requirements. On my workstation it needs
`LD_LIBRARY_PATH=/tmp/lidar-arm64-tools/root/usr/lib` and does not support
`wait-for-device`, so run commands explicitly once the device is present.

## Pinned stages

```
stage1  5e1ffc99355dee201b49dd8c3db090ad51247746005a40729a02e03ff5e4d0ba
stage2  8636dcdc0ab2b206284702d8959aff7e9600ee0bab40939d0c4008b013b5df96
```

The script resolves the workspace from its own path and reads the stages from
`reference/echo-plus-2-bootchain-v0.2.1`. It contains no absolute workspace path.

## Status

The reference chain is hardware-proven on this unit in Kaeru fastboot with
`unlock_status: true`. The source-built chain is not hardware-proven.
