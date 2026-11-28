#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Dump the tags of an unsigned GBL v3 file (Amazon's EFR32 images)."""
import struct
import sys
import zlib

TAGS = {
    0x03A617EB: "HEADER",
    0xF40A0AF4: "APPLICATION",
    0xFD0303FD: "ERASEPROG",
    0xFC0404FC: "END",
    0xFE0101FE: "ERASE",
    0xF80A0AF8: "BOOTLOADER",
    0xF90707F9: "LOCKBITS",
}


def main() -> None:
    for path in sys.argv[1:]:
        data = open(path, "rb").read()
        crc, body = struct.unpack("<I", data[-4:])[0], data[:-4]
        print(f"== {path} ({len(data)} bytes, crc32 {'ok' if crc == zlib.crc32(body) else 'BAD'})")
        off = 0
        while off < len(body):
            tag, n = struct.unpack_from("<II", body, off)
            payload = body[off + 8:off + 8 + n]
            name = TAGS.get(tag, hex(tag))
            extra = ""
            if name == "HEADER" and n >= 8:
                ver, typ = struct.unpack_from("<II", payload)
                extra = f" version={ver:#010x} type={typ}"
            elif name == "APPLICATION" and n >= 12:
                typ, ver, cap = struct.unpack_from("<III", payload)
                extra = f" type={typ:#010x} version={ver:#010x} capabilities={cap:#010x}"
            elif name == "ERASEPROG" and n >= 4:
                extra = f" base={struct.unpack_from('<I', payload)[0]:#x} image={n - 4} bytes"
            print(f"  {off:#08x} {name} len={n}{extra}")
            off += 8 + n
        print()


if __name__ == "__main__":
    main()
