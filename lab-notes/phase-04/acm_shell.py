#!/usr/bin/env python3
"""Run commands over the Lidar USB CDC ACM shell from the host.

The test initramfs spawns a root shell on /dev/ttyGS0, which the host sees as
a /dev/ttyACM* node.  This helper waits for that node, opens it raw (the CDC
data rate is fixed by the gadget, so the host baud setting is irrelevant), and
runs one command at a time.  Each command is followed by a printed end marker
so the helper can tell the output from the next command; everything read is
appended to the log file.

Standard library only: pyserial is not installed on this workstation.  With
--usbfs the helper drives the gadget's ACM data interface through raw usbfs
ioctls instead, for hosts where cdc_acm cannot load; the user then needs
read/write access to the /dev/bus/usb node (a udev rule).
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fcntl
import glob
import os
import select
import struct
import sys
import termios
import time
import tty

GADGET_ID = ("1d6b", "0104")

# linux/usbdevice_fs.h, 64-bit layouts.
USBDEVFS_CONTROL = 0xC0185500
USBDEVFS_BULK = 0xC0185502
USBDEVFS_CLAIMINTERFACE = 0x8004550F
USBDEVFS_RELEASEINTERFACE = 0x80045510
# _IOWR('U', 26, struct usbdevfs_disconnect_claim): struct is two u32 plus a
# 257-byte driver name, padded to 268 bytes.  Used only when cdc_acm already
# owns the interface, which makes a plain CLAIMINTERFACE return EBUSY.
USBDEVFS_DISCONNECT_CLAIM = 0x8108551B
USBDEVFS_DISCONNECT_CLAIM_IF_DRIVER = 1


class _CtrlTransfer(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8),
                ("wValue", ctypes.c_uint16), ("wIndex", ctypes.c_uint16),
                ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


class _BulkTransfer(ctypes.Structure):
    _fields_ = [("ep", ctypes.c_uint), ("len", ctypes.c_uint),
                ("timeout", ctypes.c_uint), ("data", ctypes.c_void_p)]


DEFAULT_COMMANDS = [
    "uname -a",
    "cat /proc/cmdline",
    "cat /proc/cpuinfo",
    "dmesg",
    "ls /pstore-prev /sys/fs/pstore",
    "cat /pstore-prev/*",
]


def find_device(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    # by-id is preferred: it keeps the name stable across replug order.
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*"):
        for path in sorted(glob.glob(pattern)):
            return path
    return None


def wait_for_device(explicit: str | None, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while True:
        path = find_device(explicit)
        if path:
            return path
        if time.monotonic() >= deadline:
            raise TimeoutError("no /dev/ttyACM* node appeared")
        time.sleep(0.25)


def _sysfs(path: str) -> str:
    with open(path) as f:
        return f.read().strip()


def find_usbfs_gadget() -> str | None:
    """Return the sysfs dir of the Lidar gadget, or None."""
    for dev in glob.glob("/sys/bus/usb/devices/*"):
        try:
            if (_sysfs(f"{dev}/idVendor"), _sysfs(f"{dev}/idProduct")) == GADGET_ID:
                return dev
        except OSError:
            continue
    return None


class UsbfsAcm:
    """CDC ACM over usbfs: claim the ACM control+data interfaces, bulk I/O."""

    def __init__(self, sysdev: str) -> None:
        bus, dev = int(_sysfs(f"{sysdev}/busnum")), int(_sysfs(f"{sysdev}/devnum"))
        self.path = f"/dev/bus/usb/{bus:03d}/{dev:03d}"
        name = os.path.basename(sysdev)
        comm = data = None
        for intf in sorted(glob.glob(f"{sysdev}/{name}:*")):
            if (_sysfs(f"{intf}/bInterfaceClass"), _sysfs(f"{intf}/bInterfaceSubClass")) == ("02", "02"):
                comm = int(_sysfs(f"{intf}/bInterfaceNumber"), 16)
                # The ACM function's data interface directly follows its
                # control interface (f_acm allocates them as a pair).
                data_dir = f"{sysdev}/{name}:1.{comm + 1}"
                eps = glob.glob(f"{data_dir}/ep_*")
                ins = [int(os.path.basename(e)[3:], 16) for e in eps
                       if _sysfs(f"{e}/type") == "Bulk" and _sysfs(f"{e}/direction") == "in"]
                outs = [int(os.path.basename(e)[3:], 16) for e in eps
                        if _sysfs(f"{e}/type") == "Bulk" and _sysfs(f"{e}/direction") == "out"]
                if ins and outs:
                    data = comm + 1
                    self.ep_in, self.ep_out = ins[0], outs[0]
                break
        if comm is None or data is None:
            raise OSError(f"no ACM interface pair on {sysdev}")
        self.fd = os.open(self.path, os.O_RDWR)
        self.ifaces = (comm, data)
        for i in self.ifaces:
            try:
                fcntl.ioctl(self.fd, USBDEVFS_CLAIMINTERFACE, ctypes.c_uint(i))
            except OSError as exc:
                if exc.errno != errno.EBUSY:
                    raise
                # cdc_acm is bound on this workstation; detach it and claim in
                # one ioctl so the tty node stays but the raw endpoints are ours.
                claim = ctypes.create_string_buffer(264)
                struct.pack_into("<II", claim, 0, i, USBDEVFS_DISCONNECT_CLAIM_IF_DRIVER)
                claim[8:8 + len(b"cdc_acm")] = b"cdc_acm"
                fcntl.ioctl(self.fd, USBDEVFS_DISCONNECT_CLAIM, claim)
        # SET_CONTROL_LINE_STATE, DTR|RTS: what cdc_acm sends on open.
        ctrl = _CtrlTransfer(0x21, 0x22, 0x3, comm, 0, 1000, None)
        fcntl.ioctl(self.fd, USBDEVFS_CONTROL, ctrl)
        self._buf = ctypes.create_string_buffer(4096)

    def write(self, payload: bytes) -> None:
        buf = ctypes.create_string_buffer(payload, len(payload))
        xfer = _BulkTransfer(self.ep_out, len(payload), 2000, ctypes.addressof(buf))
        fcntl.ioctl(self.fd, USBDEVFS_BULK, xfer)

    def read(self, timeout: float) -> bytes:
        xfer = _BulkTransfer(self.ep_in, len(self._buf), max(1, int(timeout * 1000)),
                             ctypes.addressof(self._buf))
        try:
            n = fcntl.ioctl(self.fd, USBDEVFS_BULK, xfer)
        except OSError as exc:
            if exc.errno == errno.ETIMEDOUT:
                return b""
            raise
        return self._buf.raw[:n]

    def close(self) -> None:
        for i in self.ifaces:
            try:
                fcntl.ioctl(self.fd, USBDEVFS_RELEASEINTERFACE, ctypes.c_uint(i))
            except OSError:
                pass
        os.close(self.fd)


def wait_for_usbfs(timeout: float) -> UsbfsAcm:
    deadline = time.monotonic() + timeout
    while True:
        sysdev = find_usbfs_gadget()
        if sysdev:
            try:
                return UsbfsAcm(sysdev)
            except OSError:
                # Interfaces or the udev permission may lag enumeration.
                pass
        if time.monotonic() >= deadline:
            raise TimeoutError("no accessible 1d6b:0104 gadget appeared")
        time.sleep(0.25)


def open_raw(path: str) -> int:
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    # Raw mode: no line discipline rewriting of ^C, CR/LF or flow control.
    # Raw mode also disables echo locally, but the gadget side may still echo
    # the command line, which is why the end marker is matched twice below.
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    # Speed only; the cflag keeps the raw CS8|CREAD|CLOCAL set above.  A CDC
    # ACM link ignores the number, but the line discipline still wants one.
    attrs[4] = attrs[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


class TtyAcm:
    def __init__(self, path: str) -> None:
        self.path = path
        self.fd = open_raw(path)

    def write(self, payload: bytes) -> None:
        os.write(self.fd, payload)

    def read(self, timeout: float) -> bytes:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return b""
        try:
            return os.read(self.fd, 4096)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EIO):
                return b""
            raise

    def close(self) -> None:
        os.close(self.fd)


class Session:
    def __init__(self, link: TtyAcm | UsbfsAcm, log_path: str) -> None:
        self.link = link
        self.log = open(log_path, "ab", buffering=0)
        self.seq = 0

    def run(self, command: str, timeout: float) -> bytes:
        self.seq += 1
        marker = f"__ACM_END_{self.seq}__"
        # One line: the command, then the marker, so a shell that mangles the
        # line ending cannot swallow the marker.
        line = f"{command}; echo {marker}\n"
        self.link.write(line.encode())
        self.log.write(b"\n$ " + command.encode() + b"\n")

        collected = b""
        deadline = time.monotonic() + timeout
        seen = 0
        last_data = time.monotonic()
        while time.monotonic() < deadline:
            chunk = self.link.read(0.2)
            if chunk:
                collected += chunk
                self.log.write(chunk)
                last_data = time.monotonic()
                seen = collected.count(marker.encode())
                if seen >= 2:
                    break
            elif seen == 1 and time.monotonic() - last_data > 2.0:
                # Echo is off on the gadget side: the marker was printed once
                # and nothing followed, so the command is done.
                break
        if not collected:
            self.log.write(b"<no output>\n")
        return collected

    def close(self) -> None:
        self.log.close()
        self.link.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", help="tty path; default: first /dev/ttyACM*")
    parser.add_argument("--usbfs", action="store_true",
                        help="talk to the 1d6b:0104 gadget through usbfs, not a tty")
    parser.add_argument("--log", default="acm-shell.log", help="output log file")
    parser.add_argument("--wait", type=float, default=120.0,
                        help="seconds to wait for the tty node or gadget")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="seconds allowed per command")
    parser.add_argument("commands", nargs="*", help="commands; default: diagnostics")
    args = parser.parse_args(argv)

    commands = args.commands or DEFAULT_COMMANDS
    try:
        link = (wait_for_usbfs(args.wait) if args.usbfs
                else TtyAcm(wait_for_device(args.device, args.wait)))
    except (TimeoutError, OSError) as exc:
        print(f"acm_shell: {exc}", file=sys.stderr)
        return 1

    print(f"acm_shell: {link.path} -> {args.log}", file=sys.stderr)
    session = Session(link, args.log)
    try:
        for command in commands:
            out = session.run(command, args.timeout)
            sys.stdout.write(out.decode("utf-8", "replace"))
            sys.stdout.flush()
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
