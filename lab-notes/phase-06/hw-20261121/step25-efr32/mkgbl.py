#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pack a flat EFR32 application image into an unsigned, unencrypted GBL v3
file for the Gecko bootloader on lidar's EFR32MG12 (XMODEM upload, see
tools/lidar-efr32.sh).

Layout, as in the two images Amazon ships for this radio:
  HEADER     version 3.0, type 0 (plain)
  APPLICATION  ApplicationData_t copied from the image's own
               ApplicationProperties_t (pointer at vector table entry 13)
  ERASEPROG  start address + the image
  END        CRC32 (zlib) over everything before the CRC itself

Usage: mkgbl.py <image.bin> <out.gbl> [--base 0x0]
"""
import argparse
import struct
import sys
import zlib

TAG_HEADER = 0x03A617EB
TAG_APPLICATION = 0xF40A0AF4
TAG_ERASEPROG = 0xFD0303FD
TAG_END = 0xFC0404FC
APP_PROPS_MAGIC = bytes.fromhex("13b779fac925ddb7adf3cfe0f1b614b8")
# EFR32MG12 main flash: the application area. USERDATA, the lock bits and
# the bootloader sit from 0x0FE00000 up and must never be written.
FLASH_SIZE = 0x100000


def tag(tag_id: int, body: bytes) -> bytes:
    return struct.pack("<II", tag_id, len(body)) + body


def app_data(image: bytes, base: int) -> bytes:
    """ApplicationData_t (type, version, capabilities, productId[16])."""
    ptr = struct.unpack_from("<I", image, 13 * 4)[0] - base
    if not 0 <= ptr <= len(image) - 56 or image[ptr:ptr + 16] != APP_PROPS_MAGIC:
        sys.exit("no application properties at vector table entry 13")
    return image[ptr + 28:ptr + 56]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0)
    args = ap.parse_args()

    image = open(args.image, "rb").read()
    if len(image) < 56:
        sys.exit("image too short for a vector table")
    if args.base < 0 or args.base + len(image) > FLASH_SIZE:
        sys.exit("image does not fit the application area (main flash)")
    sp, reset = struct.unpack_from("<II", image)
    if not 0x20000000 < sp <= 0x20020000:
        sys.exit(f"initial SP {sp:#x} is outside the EFR32MG12's 128 KB of RAM")
    if not args.base <= reset < args.base + len(image):
        sys.exit(f"reset vector {reset:#x} is outside the image")

    gbl = (tag(TAG_HEADER, struct.pack("<II", 0x03000000, 0))
           + tag(TAG_APPLICATION, app_data(image, args.base))
           + tag(TAG_ERASEPROG, struct.pack("<I", args.base) + image)
           + struct.pack("<II", TAG_END, 4))
    gbl += struct.pack("<I", zlib.crc32(gbl))
    open(args.out, "wb").write(gbl)
    t, v, c = struct.unpack_from("<III", app_data(image, args.base))
    print(f"{args.out}: {len(gbl)} bytes, app type {t:#x} version {v:#x}")


if __name__ == "__main__":
    main()
