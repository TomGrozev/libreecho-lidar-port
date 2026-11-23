#!/usr/bin/env python3
# CRC-16/X-25 check of captured Spinel HDLC frames.
import sys


def crc(data: bytes) -> int:
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c >> 1) ^ 0x8408) if c & 1 else (c >> 1)
    return c ^ 0xFFFF


for frame in sys.argv[1:]:
    raw = bytes.fromhex(frame)
    print(f"{frame}: crc(over all but last 2)={crc(raw[:-2]):04x} last2={raw[-2:].hex()}")
