#!/usr/bin/env python3
"""Enter BROM fastboot with the pinned reference payloads.

Portable form of the 2026-11-15 hardware run. It sets watchdog bit 2 at
0x10007024 and reboots. It does not write eMMC, MISC, BCB, or partitions.
"""

import argparse
import hashlib
import importlib.util
import os
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
KIT = WORKSPACE / "reference" / "echo-plus-2-bootchain-v0.2.1"
MODULES = KIT / "third_party" / "kamakiri" / "modules"

PAYLOADS = (
    (
        "stage1",
        Path("brom-payload/stage1/stage1.bin"),
        624,
        "5e1ffc99355dee201b49dd8c3db090ad51247746005a40729a02e03ff5e4d0ba",
    ),
    (
        "stage2",
        Path("brom-payload/stage2/stage2.bin"),
        15580,
        "8636dcdc0ab2b206284702d8959aff7e9600ee0bab40939d0c4008b013b5df96",
    ),
)


class _AlreadyRemoved:
    """Stand-in for the kit's BROM test-point checkpoint thread.

    The release checkpoint waits for a temporary test point that this unit
    never had, and a non-interactive run has no terminal for input().
    """

    done = True

    def start(self):
        pass


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_payloads():
    problems = []
    for label, relative, expected_size, expected_hash in PAYLOADS:
        path = KIT / relative
        try:
            size = path.stat().st_size
        except OSError as error:
            problems.append(f"{label}: cannot read {path}: {error}")
            continue
        if size != expected_size:
            problems.append(
                f"{label}: {path} is {size} bytes, expected {expected_size}"
            )
            continue
        try:
            actual_hash = sha256_file(path)
        except OSError as error:
            problems.append(f"{label}: cannot hash {path}: {error}")
            continue
        if actual_hash != expected_hash:
            problems.append(
                f"{label}: {path} has sha256 {actual_hash}, "
                f"expected {expected_hash}"
            )
            continue
        print(f"{label}: {path} {size} bytes sha256 {actual_hash}")
    return problems


def enter_fastboot():
    if importlib.util.find_spec("usb") is None:
        print(
            "pyusb is not installed. Run the device command as: "
            f"uv run --with pyusb python {Path(__file__).resolve()}",
            file=sys.stderr,
        )
        return 1

    # load_payload opens ../brom-payload/... and imports its sibling modules
    # by bare name, so the kit's third_party directory must be the cwd.
    os.chdir(KIT / "third_party")
    sys.path.insert(0, str(MODULES))

    from device import Device
    import load_payload

    load_payload.UserInputThread = _AlreadyRemoved

    device = Device().find()
    load_payload.load_payload(device)
    device.set_fastboot_flag()
    device.reboot()
    print("Fastboot WDT flag set; reboot command sent.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Load the pinned Kamakiri payloads and set the fastboot WDT flag."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="check payload presence, size, and SHA-256, then exit without USB access",
    )
    args = parser.parse_args(argv)

    problems = verify_payloads()
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print("Payload verification failed. No device was opened.", file=sys.stderr)
        return 1

    if args.verify_only:
        print("Payload verification passed. No device was opened.")
        return 0

    return enter_fastboot()


if __name__ == "__main__":
    sys.exit(main())
