#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""spinel-reset: send a Spinel RESET over TCP and print the frames heard.

Usage: spinel-reset.py <host> <port>
Talks to tcp-uart on the device.  Spinel on UART uses HDLC: 0x7e flag, 0x7d
escape, FCS = CRC-16/CCITT (poly 0x1021, init 0xFFFF) sent little-endian.
"""
import socket
import sys
import time


def fcs(data: bytes) -> bytes:
    # HDLC-lite FCS is CRC-16/X-25: reflected poly 0x8408, init/xorout 0xFFFF,
    # sent little-endian (openthread/src/lib/spinel/spinel.c).
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    crc ^= 0xFFFF
    return bytes([crc & 0xFF, crc >> 8])


def hdlc(payload: bytes) -> bytes:
    out = bytearray(b"\x7e")
    for byte in payload + fcs(payload):
        if byte in (0x7E, 0x7D, 0x11, 0x13):
            out += bytes([0x7D, byte ^ 0x20])
        else:
            out.append(byte)
    out += b"\x7e"
    return bytes(out)


def main() -> None:
    host, port = sys.argv[1], int(sys.argv[2])
    s = socket.create_connection((host, port), timeout=5)
    for tid, frame in enumerate(
        (
            bytes([0x81, 0x01]),  # RESET (stack, default)
            bytes([0x82, 0x02, 0x02]),  # GET NCP_VERSION
            bytes([0x83, 0x02, 0x01]),  # GET PROTOCOL_VERSION
            bytes([0x84, 0x02, 0x05]),  # GET CAPS
            bytes([0x85, 0x02, 0x03]),  # GET INTERFACE_TYPE
        )
    ):
        s.sendall(hdlc(frame))
        time.sleep(0.4)
    s.settimeout(1.0)
    buf = b""
    end = time.time() + 5
    while time.time() < end:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
    print(f"{len(buf)} bytes: {buf.hex()}")
    for frame in buf.split(b"\x7e"):
        if frame:
            print(f"  raw {frame.hex()}")


if __name__ == "__main__":
    main()
