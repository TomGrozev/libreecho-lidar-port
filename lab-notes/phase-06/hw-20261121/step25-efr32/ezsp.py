#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Minimal ASH/EZSP frame builder for probing the EmberZNet NCP.

Follows zigpy/bellows bellows/ash.py: CRC is binascii.crc_hqx(.., 0xFFFF)
sent big-endian, and a DATA frame's EZSP payload is XOR-randomized with the
fixed ASH pseudo-random sequence.
"""
import binascii
import sys


def rnd_seq(n=256):
    out = bytearray()
    r = 0x42
    for _ in range(n):
        out.append(r)
        r = ((r >> 1) ^ 0xB8) if r & 1 else (r >> 1)
    return bytes(out)


SEQ = rnd_seq()


def randomize(data: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, SEQ))


def crc(data: bytes) -> bytes:
    return binascii.crc_hqx(data, 0xFFFF).to_bytes(2, "big")


def frame(ezsp: bytes, frm=0, ack=0, re_tx=0) -> bytes:
    control = ((frm & 7) << 4) | ((re_tx & 1) << 3) | (ack & 7)
    body = bytes([control]) + randomize(ezsp)
    return bytes([0x1A]) + body + crc(body) + bytes([0x7E])


def octal(b: bytes) -> str:
    return "".join(f"\\{x:03o}" for x in b)


def main() -> None:
    # self-check against the captured RSTACK 1a c1 02 0b 0a 52 7e
    assert crc(bytes([0xC1, 0x02, 0x0B])).hex() == "0a52"
    if len(sys.argv) < 2:
        return
    if sys.argv[1] == "parse":
        raw = bytes.fromhex(sys.argv[2])
        for part in raw.split(b"\x7e"):
            if len(part) < 3:
                continue
            control, body = part[0], part[1:-2]
            print(f"control={control:#04x} frm={(control>>4)&7} re_tx={(control>>3)&1} "
                  f"ack={control&7} crc_ok={crc(part[:-2]) == part[-2:]}")
            print("  ezsp:", randomize(body).hex(" "))
        return
    if sys.argv[1] == "version":
        # EZSP v4: frameControl(1), frameId, commandId=version, protocolVersion, protocol
        print("v4:", octal(frame(bytes([0x00, 0x00, 0x00, 0x04, 0x02]))))
        # EZSP v5+: frameControl(2, little-endian 0x0000), frameId, commandId, ...
        print("v5:", octal(frame(bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x02]))))


if __name__ == "__main__":
    main()
