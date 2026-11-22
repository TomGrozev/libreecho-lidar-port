#!/usr/bin/env python3
"""Dump LK structure around the Amazon board-compatible table."""
import re, struct, sys

LK = "/workspace/libreecho/dumps/20261110-lidar-readback/lk_a.bin"
d = open(LK, "rb").read()
print("lk size", len(d))

# 1. all printable strings with offsets inside the interesting window
print("\n== strings 0x2c000-0x34000 ==")
for m in re.finditer(rb"[\x20-\x7e]{4,}", d[0x2b000:0x34500]):
    print(hex(0x2b000 + m.start()), m.group().decode())

# 2. hexdump of the table region
print("\n== hexdump 0x32f80-0x33280 ==")
for off in range(0x32f80, 0x33280, 16):
    chunk = d[off:off + 16]
    print(f"{off:08x}  {chunk.hex(' ')}  " + "".join(chr(c) if 32 <= c < 127 else "." for c in chunk))

# 3. find 32-bit little-endian pointers to the compatible strings (try common LK bases)
targets = [0x33031, 0x3305c, 0x33087, 0x330b2, 0x330dd, 0x33108, 0x33133, 0x3315e, 0x33189,
           0x2c8b6, 0x2c90c, 0x2ca69]
bases = [0, 0x41e00000, 0x40000000, 0x4e000000, 0x800, 0x80000000]
for base in bases:
    for t in targets:
        pat = struct.pack("<I", base + t)
        hits = [m.start() for m in re.finditer(re.escape(pat), d)]
        if hits:
            print(f"base {base:#x} target {t:#x} hits", [hex(h) for h in hits[:6]])
