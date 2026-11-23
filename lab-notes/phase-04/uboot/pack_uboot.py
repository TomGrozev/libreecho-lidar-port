#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Pack a second-stage U-Boot into an Amazon-LK boot image for "lidar".

The stock LK only boots Android boot images: it gunzips the kernel field to
kernel_addr, backwards-scans the compressed field for an appended DTB and
jumps with x0 = that DTB.  The payload is therefore

    kernel field = MTK "KERNEL" header + gzip(u-boot.bin + u-boot.dtb)
                   + u-boot.dtb          (a second copy for LK to select)

The DTB inside the gzip stream is U-Boot's own control devicetree; the copy
outside is what LK finds, fixes up and hands over.  Keeping both means U-Boot
does not depend on LK's DT selection and LK still finds a matching DTB.

The existing pack_boot.py output is unchanged; this is a sibling script.
"""

import argparse
import gzip
import hashlib
import struct
import sys

ANDROID_MAGIC = b"ANDROID!"
MTK_MAGIC = 0x58881688
MTK_HDR_SIZE = 512
PAGE = 2048
KERNEL_ADDR = 0x40080000
RAMDISK_ADDR = 0x44000000
SECOND_ADDR = 0x40F00000
TAGS_ADDR = 0x4E000000
ATF_BASE = 0x43000000
LK_DTB_MAX = 0x80000
BOOT_PART_SIZE = 16 << 20


def mtk_header(size: int) -> bytes:
    hdr = struct.pack("<II32s", MTK_MAGIC, size, b"KERNEL")
    return hdr + b"\xff" * (MTK_HDR_SIZE - len(hdr))


def pad(data: bytes) -> bytes:
    return data + b"\0" * (-len(data) % PAGE)


def dtb_root_compatible(dtb: bytes) -> list[str]:
    if dtb[:4] != b"\xd0\x0d\xfe\xed":
        raise SystemExit("not a flattened device tree")
    off_struct, off_strings = struct.unpack_from(">II", dtb, 8)
    pos = off_struct
    if struct.unpack_from(">I", dtb, pos)[0] != 1:
        raise SystemExit("FDT does not start with BEGIN_NODE")
    pos += 4
    pos = (dtb.index(b"\0", pos) + 4) & ~3
    while True:
        tag = struct.unpack_from(">I", dtb, pos)[0]
        if tag == 4:
            pos += 4
            continue
        if tag != 3:
            return []
        length, nameoff = struct.unpack_from(">II", dtb, pos + 4)
        name = dtb[off_strings + nameoff:
                   dtb.index(b"\0", off_strings + nameoff)]
        val = dtb[pos + 12:pos + 12 + length]
        if name == b"compatible":
            return [s.decode() for s in val.rstrip(b"\0").split(b"\0")]
        pos = (pos + 12 + length + 3) & ~3


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uboot-bin", required=True,
                    help="u-boot.bin built with LINUX_KERNEL_IMAGE_HEADER")
    ap.add_argument("--uboot-dtb", required=True, help="u-boot.dtb")
    ap.add_argument("--stock", required=True,
                    help="stock boot_a.bin, source of the ramdisk and cmdline")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    uboot = open(args.uboot_bin, "rb").read()
    dtb = open(args.uboot_dtb, "rb").read()
    stock = open(args.stock, "rb").read()

    if stock[:8] != ANDROID_MAGIC:
        raise SystemExit(f"{args.stock}: not an Android boot image")
    (_magic, _ks, _ka, _rs, _ra, _ss, _sa, _ta, stock_page,
     _hv, _osv) = struct.unpack_from("<8s10I", stock, 0)
    stock_cmdline = stock[0x40:0x240].split(b"\0")[0]
    ramdisk_off = stock_page + -(-_ks // stock_page) * stock_page
    ramdisk = stock[ramdisk_off:ramdisk_off + _rs]
    if not ramdisk:
        raise SystemExit("stock image has no ramdisk")

    if uboot[0x38:0x3C] != b"ARM\x64":
        raise SystemExit("u-boot.bin has no arm64 Image header")
    image_size = struct.unpack_from("<Q", uboot, 16)[0]
    # Position-independent U-Boot links .bss at address 0, so the header's
    # "effective size" comes out as __bss_start - _start, i.e. negative.
    # Fall back to the file size plus generous BSS headroom.
    if image_size == 0 or image_size >= 1 << 30:
        image_size = len(uboot) + (8 << 20)
    if KERNEL_ADDR + image_size > ATF_BASE:
        raise SystemExit(
            f"U-Boot image ({image_size:#x} bytes incl. BSS) overlaps BL31")

    if len(dtb) > LK_DTB_MAX:
        raise SystemExit(f"DTB exceeds LK limit {LK_DTB_MAX:#x}")
    compat = dtb_root_compatible(dtb)
    if not compat or not compat[0].startswith("amzn,lidar"):
        raise SystemExit(
            f"first root compatible {compat} is not amzn,lidar-<rev>; "
            "LK will not select this DTB")

    payload = gzip.compress(uboot + dtb, compresslevel=9, mtime=0)
    kernel = mtk_header(len(payload) + len(dtb)) + payload + dtb
    cmdline = stock_cmdline
    if len(cmdline) >= 512:
        raise SystemExit("cmdline too long for the v0 header")

    sha = hashlib.sha1()
    for blob in (kernel, ramdisk, b""):
        sha.update(blob)
        sha.update(struct.pack("<I", len(blob)))

    hdr = struct.pack(
        "<8s10I16s512s32s1024s",
        ANDROID_MAGIC, len(kernel), KERNEL_ADDR, len(ramdisk), RAMDISK_ADDR,
        0, SECOND_ADDR, TAGS_ADDR, PAGE, 0, 0, b"",
        cmdline, sha.digest(), b"")
    out = pad(hdr) + pad(kernel) + pad(ramdisk)
    if len(out) > BOOT_PART_SIZE:
        raise SystemExit(f"image is {len(out)} bytes; boot_a holds "
                         f"{BOOT_PART_SIZE}")
    out += b"\0" * (BOOT_PART_SIZE - len(out))
    open(args.out, "wb").write(out)
    print(f"{args.out}: {len(out)} bytes, kernel {len(kernel)}, "
          f"ramdisk {len(ramdisk)}, dtb {len(dtb)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
