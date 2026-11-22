#!/usr/bin/env python3
"""Build and verify a development MTK/Android v0 boot image for the Lidar target.

The stock image is opened read-only. The tool never writes to the stock path.

The output mirrors the stock envelope:
  * 16 MiB image, 2048 byte pages
  * Android v0 header with the stock load addresses
  * 512 byte MTK KERNEL header (0x58881688)
  * deterministic gzip kernel, then the appended FDT collection
  * the stock ARM32 gzip ramdisk
  * trailing bytes zeroed, so no stock signature is retained

The opt-in --ramdisk FILE mode uses FILE as the ramdisk instead of the stock
one. FILE must be one complete gzip stream holding a newc archive with an
executable regular-file `init`. Without the option the stock ramdisk bytes are
copied unchanged.

The opt-in --cmdline-append TEXT mode keeps the stock command line and appends
TEXT once, separated by a single space. The v0 header stores one command line
across cmdline and extra_cmdline exactly as mkbootimg does, so the bootloader
joins the two fields back into the same string. Without the option the header
cmdline fields stay byte-identical to stock.

The replacement DTB also gets /chosen linux,initrd-start and linux,initrd-end
derived from the header ramdisk_addr and the actual ramdisk size. LK copies
the ramdisk to that address on every boot but writes those properties only
for IDME bootmode 2/0x61, so a normal slot boot otherwise hands the kernel no
initrd. The stock appended DTBs are carried unchanged; only the replacement
DTB, which LK selects for this board by compatible, is edited.

Building and --verify both reject an effective command line that does not open
with the LK 64-bit handover prefix, a DTB over the LK copy limit, or a new DTB
whose first root compatible is not a Lidar board string. --verify also rejects
a /chosen initrd range that is missing or differs from the header.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

PAGE_SIZE = 2048
IMAGE_SIZE = 16 * 1024 * 1024
BOOT_HEADER_SIZE = 1632
ANDROID_MAGIC = b"ANDROID!"
# The v0 header splits one NUL-terminated command line across two fields.
CMDLINE_OFFSET = 64
CMDLINE_SIZE = 512
EXTRA_CMDLINE_OFFSET = 608
EXTRA_CMDLINE_SIZE = BOOT_HEADER_SIZE - EXTRA_CMDLINE_OFFSET
# mkbootimg keeps a terminator in cmdline and continues in extra_cmdline.
MAX_CMDLINE_TEXT = CMDLINE_SIZE - 1 + EXTRA_CMDLINE_SIZE - 1
MTK_MAGIC = 0x58881688
MTK_HEADER_SIZE = 512
MTK_NAME = b"KERNEL\x00\x00"
MTK_FILLER_OFFSET = 0x28
FDT_MAGIC = 0xD00DFEED
ARM64_IMAGE_MAGIC = 0x644D5241  # b"ARMd" at Image + 0x38
ARM64_MAGIC_OFFSET = 0x38

KERNEL_ADDR = 0x40080000
RAMDISK_ADDR = 0x44000000
SECOND_ADDR = 0x40F00000
TAGS_ADDR = 0x4E000000
OS_VERSION = 0x0E04119C

STOCK_DTB_COUNT = 19
STOCK_DTB_INDEX = 4
STOCK_PVT_SHA256 = (
    "b5302d9e4a672e7c2d06624d712746fe61fa30ed59183d85f253cec2775a730f"
)
LIDAR_PVT_COMPATIBLE = "amzn,lidar-pvt"
LIDAR_COMPATIBLE_PREFIX = "amzn,lidar-"
# LK picks the AArch64 handover only when the command line opens with this.
BOOTOPT_PREFIX = b"bootopt=64S3,32N2,64N2"
# LK copies the selected appended DTB to TAGS_ADDR and fails beyond this size.
MAX_DTB_SIZE = 0x80000

CPIO_HEADER_SIZE = 110
CPIO_MAGIC = (b"070701", b"070702")
CPIO_TRAILER = b"TRAILER!!!\x00"
REGULAR_FILE_MODE = 0o100000

HEADER_FIELDS = (
    "kernel_size",
    "kernel_addr",
    "ramdisk_size",
    "ramdisk_addr",
    "second_size",
    "second_addr",
    "tags_addr",
    "page_size",
    "header_version",
    "os_version",
)


class PackError(Exception):
    """A layout or input violates the expected stock envelope."""


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(path: str) -> bytes:
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise PackError(f"cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class AndroidHeader:
    raw: bytes
    kernel_size: int
    kernel_addr: int
    ramdisk_size: int
    ramdisk_addr: int
    second_size: int
    second_addr: int
    tags_addr: int
    page_size: int
    header_version: int
    os_version: int
    name: bytes
    cmdline: bytes
    android_id: bytes
    extra_cmdline: bytes


def parse_android_header(data: bytes) -> AndroidHeader:
    if len(data) < BOOT_HEADER_SIZE:
        raise PackError("image is shorter than the v0 boot header")
    if data[:8] != ANDROID_MAGIC:
        raise PackError("missing ANDROID! magic")
    values = dict(zip(HEADER_FIELDS, struct.unpack_from("<10I", data, 8)))
    return AndroidHeader(
        raw=data[:BOOT_HEADER_SIZE],
        name=data[48:64],
        cmdline=data[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE],
        android_id=data[576:596],
        extra_cmdline=data[
            EXTRA_CMDLINE_OFFSET:EXTRA_CMDLINE_OFFSET + EXTRA_CMDLINE_SIZE
        ],
        **values,
    )


def validate_stock_header(header: AndroidHeader) -> None:
    checks = (
        ("page_size", header.page_size, PAGE_SIZE),
        ("kernel_addr", header.kernel_addr, KERNEL_ADDR),
        ("ramdisk_addr", header.ramdisk_addr, RAMDISK_ADDR),
        ("second_addr", header.second_addr, SECOND_ADDR),
        ("tags_addr", header.tags_addr, TAGS_ADDR),
        ("header_version", header.header_version, 0),
        ("second_size", header.second_size, 0),
    )
    for name, actual, expected in checks:
        if actual != expected:
            raise PackError(
                f"unexpected {name}: {actual:#x} (expected {expected:#x})"
            )
    if header.os_version != OS_VERSION:
        raise PackError(
            f"unexpected os_version: {header.os_version:#x}"
        )
    if header.kernel_size <= MTK_HEADER_SIZE:
        raise PackError("kernel_size does not cover the MTK header")


def encode_cmdline_append(suffix: str) -> bytes:
    """Validate and encode the --cmdline-append value."""
    if not suffix:
        raise PackError("cmdline append suffix is empty")
    encoded = suffix.encode("utf-8")
    if b"\x00" in encoded:
        raise PackError("cmdline append suffix contains a NUL byte")
    return encoded


def _header_cmdline_text(field: bytes, label: str) -> bytes:
    text, terminator, remainder = field.partition(b"\x00")
    if not terminator:
        raise PackError(f"stock boot header {label} is not NUL-terminated")
    if any(remainder):
        raise PackError(
            f"stock boot header {label} has bytes after its NUL terminator"
        )
    return text


def append_cmdline(header: AndroidHeader, suffix: bytes) -> tuple[bytes, bytes]:
    """Return cmdline/extra_cmdline fields carrying stock + " " + suffix.

    A v0 header holds one command line split across two NUL-terminated fields.
    mkbootimg breaks it at CMDLINE_SIZE - 1 without adding or dropping a
    separator, so a bootloader that joins the fields sees the exact string.
    """
    if not suffix:
        raise PackError("cmdline append suffix is empty")
    if b"\x00" in suffix:
        raise PackError("cmdline append suffix contains a NUL byte")
    combined = (
        _header_cmdline_text(header.cmdline, "cmdline")
        + _header_cmdline_text(header.extra_cmdline, "extra_cmdline")
        + b" "
        + suffix
    )
    if len(combined) > MAX_CMDLINE_TEXT:
        raise PackError(
            "cmdline append overflows the boot header: "
            f"{len(combined)} > {MAX_CMDLINE_TEXT} bytes"
        )
    cmdline = combined[:CMDLINE_SIZE - 1].ljust(CMDLINE_SIZE, b"\x00")
    extra_cmdline = (combined[CMDLINE_SIZE - 1:] + b"\x00").ljust(
        EXTRA_CMDLINE_SIZE, b"\x00"
    )
    return cmdline, extra_cmdline


def effective_cmdline(cmdline: bytes, extra_cmdline: bytes) -> bytes:
    """Join the two NUL-terminated v0 fields into the string LK sees."""
    return cmdline.split(b"\x00", 1)[0] + extra_cmdline.split(b"\x00", 1)[0]


def validate_bootopt(cmdline: bytes, extra_cmdline: bytes) -> None:
    """Reject a command line that does not select the LK 64-bit handover."""
    combined = effective_cmdline(cmdline, extra_cmdline)
    if not combined.startswith(BOOTOPT_PREFIX):
        raise PackError(
            "kernel command line must open with "
            f"{BOOTOPT_PREFIX.decode('ascii')}, got {combined[:32]!r}; "
            "LK needs that prefix to pick the AArch64 handover"
        )


def android_id(kernel: bytes, ramdisk: bytes) -> bytes:
    digest = hashlib.sha1()
    digest.update(kernel)
    digest.update(struct.pack("<I", len(kernel)))
    digest.update(ramdisk)
    digest.update(struct.pack("<I", len(ramdisk)))
    digest.update(struct.pack("<I", 0))
    return digest.digest()


def validate_mtk_header(header: bytes, kernel_size: int) -> None:
    if len(header) != MTK_HEADER_SIZE:
        raise PackError("MTK header is not 512 bytes")
    magic, size = struct.unpack_from("<II", header, 0)
    if magic != MTK_MAGIC:
        raise PackError(f"unexpected MTK magic: {magic:#x}")
    if size != kernel_size - MTK_HEADER_SIZE:
        raise PackError(
            f"MTK size {size:#x} does not match kernel_size {kernel_size:#x}"
        )
    if header[8:16] != MTK_NAME:
        raise PackError("unexpected MTK kernel name")
    if any(header[16:MTK_FILLER_OFFSET]):
        raise PackError("unexpected bytes in the MTK header name area")
    if header[MTK_FILLER_OFFSET:] != b"\xff" * (MTK_HEADER_SIZE - MTK_FILLER_OFFSET):
        raise PackError("unexpected MTK header filler")


def decompress_first_gzip(payload: bytes, label: str) -> tuple[bytes, int]:
    try:
        inflater = zlib.decompressobj(31)
        result = inflater.decompress(payload)
        result += inflater.flush()
    except zlib.error as exc:
        raise PackError(f"{label} gzip stream is invalid: {exc}") from exc
    if not inflater.eof:
        raise PackError(f"{label} gzip stream is truncated")
    consumed = len(payload) - len(inflater.unused_data)
    if consumed <= 0:
        raise PackError(f"{label} gzip stream consumed no bytes")
    return result, consumed


def gzip_deterministic(data: bytes) -> bytes:
    """Return a gzip stream with a fixed header and no metadata.

    Deflate output depends on the local zlib build. Identical inputs and the
    same Python stay byte-identical.
    """
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15, 9, zlib.Z_DEFAULT_STRATEGY)
    body = deflater.compress(data) + deflater.flush()
    header = b"\x1f\x8b\x08\x00" + struct.pack("<I", 0) + b"\x02\xff"
    trailer = struct.pack("<II", zlib.crc32(data) & 0xFFFFFFFF, len(data) & 0xFFFFFFFF)
    return header + body + trailer


@dataclass(frozen=True)
class CpioEntry:
    """One newc cpio entry, retaining the stock header and padding bytes."""

    header: bytes
    name: bytes
    data: bytes
    padding: bytes

    @property
    def mode(self) -> int:
        return int(self.header[14:22], 16)

    @property
    def name_padding(self) -> bytes:
        return b"\x00" * (-(CPIO_HEADER_SIZE + len(self.name)) % 4)

    @property
    def text_name(self) -> str:
        return self.name[:-1].decode("ascii", "replace")


@dataclass(frozen=True)
class CpioArchive:
    entries: tuple[CpioEntry, ...]
    tail: bytes


def parse_cpio(data: bytes, label: str) -> CpioArchive:
    """Parse a newc archive up to and including its TRAILER!!! entry."""
    entries: list[CpioEntry] = []
    pos = 0
    while True:
        header = data[pos:pos + CPIO_HEADER_SIZE]
        if len(header) != CPIO_HEADER_SIZE:
            raise PackError(f"{label} cpio archive has no TRAILER!!! entry")
        if header[:6] not in CPIO_MAGIC:
            raise PackError(f"{label} cpio entry at {pos:#x} has bad magic")
        try:
            filesize = int(header[54:62], 16)
            namesize = int(header[94:102], 16)
        except ValueError as exc:
            raise PackError(
                f"{label} cpio entry at {pos:#x} has a bad size field"
            ) from exc
        if namesize < 2 or namesize > 256:
            raise PackError(f"{label} cpio entry at {pos:#x} has a bad name size")
        name_start = pos + CPIO_HEADER_SIZE
        name = data[name_start:name_start + namesize]
        if len(name) != namesize or not name.endswith(b"\x00"):
            raise PackError(f"{label} cpio entry at {pos:#x} has a truncated name")
        data_start = name_start + namesize
        aligned_data_start = data_start + (-(data_start % 4) % 4)
        name_padding = data[data_start:aligned_data_start]
        if len(name_padding) != aligned_data_start - data_start or any(name_padding):
            raise PackError(f"{label} cpio entry at {pos:#x} has nonzero name padding")
        data_end = aligned_data_start + filesize
        pad_end = data_end + (-filesize % 4)
        if pad_end > len(data):
            raise PackError(f"{label} cpio entry at {pos:#x} exceeds the archive")
        padding = data[data_end:pad_end]
        if any(padding):
            raise PackError(f"{label} cpio entry at {pos:#x} has nonzero padding")
        entries.append(CpioEntry(header, name, data[aligned_data_start:data_end], padding))
        pos = pad_end
        if name == CPIO_TRAILER:
            break
    tail = data[pos:]
    if any(tail):
        raise PackError(f"{label} cpio tail padding is not zero")
    return CpioArchive(entries=tuple(entries), tail=tail)


def serialize_cpio(archive: CpioArchive) -> bytes:
    return b"".join(
        entry.header + entry.name + entry.name_padding + entry.data + entry.padding
        for entry in archive.entries
    ) + archive.tail


def validate_ramdisk(ramdisk: bytes, label: str) -> None:
    """Require one complete gzip stream holding a newc archive with init.

    LK hands the ramdisk to a kernel that execs `init` directly, so a missing
    or non-executable init fails only on the device.
    """
    decompressed, consumed = decompress_first_gzip(ramdisk, label)
    if consumed != len(ramdisk):
        raise PackError(f"{label} has trailing bytes after its gzip stream")
    archive = parse_cpio(decompressed, label)
    entries = [entry for entry in archive.entries if entry.name == b"init\x00"]
    if not entries:
        raise PackError(f"{label} has no init entry")
    if len(entries) > 1:
        raise PackError(f"{label} has {len(entries)} init entries")
    mode = entries[0].mode
    if (mode & 0o170000) != REGULAR_FILE_MODE:
        raise PackError(f"{label} init is not a regular file")
    if not mode & 0o111:
        raise PackError(f"{label} init is not executable")


def validate_arm64_image(data: bytes, label: str) -> None:
    if len(data) < ARM64_MAGIC_OFFSET + 4:
        raise PackError(f"{label} is too small to be an ARM64 Image")
    magic = struct.unpack_from("<I", data, ARM64_MAGIC_OFFSET)[0]
    if magic != ARM64_IMAGE_MAGIC:
        raise PackError(f"{label} has no ARM64 Image magic at +0x38")


@dataclass
class FdtProperty:
    name: bytes
    value: bytes


@dataclass
class FdtNode:
    name: bytes
    properties: list[FdtProperty]
    children: list["FdtNode"]


@dataclass(frozen=True)
class FlatFdt:
    """A parsed flat device tree that can be edited and serialized again."""

    root: FdtNode
    reserve_map: bytes
    version: int
    last_comp_version: int
    boot_cpuid: int
    strings: bytes
    string_offsets: dict[bytes, int]


def parse_fdt(blob: bytes, label: str) -> FlatFdt:
    """Validate one flattened device tree and return its nodes in order."""
    if len(blob) < 40:
        raise PackError(f"{label} is shorter than an FDT header")
    (
        magic,
        totalsize,
        off_struct,
        off_strings,
        off_rsvmap,
        version,
        last_comp_version,
        boot_cpuid,
        size_strings,
        size_struct,
    ) = struct.unpack_from(">10I", blob, 0)
    if magic != FDT_MAGIC:
        raise PackError(f"{label} has no FDT magic")
    if totalsize != len(blob):
        raise PackError(
            f"{label} totalsize {totalsize} does not match {len(blob)} bytes"
        )
    if version < 16:
        raise PackError(f"{label} has unsupported FDT version {version}")
    if off_struct < 40 or off_strings < 40:
        raise PackError(f"{label} has an FDT block inside the header")
    if off_rsvmap < 40 or off_rsvmap + 16 > totalsize:
        raise PackError(f"{label} has an out-of-range memory reservation map")
    if off_struct % 4 or size_struct == 0 or size_struct % 4:
        raise PackError(f"{label} has an invalid structure block")
    if off_struct + size_struct > totalsize:
        raise PackError(f"{label} structure block exceeds totalsize")
    if off_strings + size_strings > totalsize:
        raise PackError(f"{label} strings block exceeds totalsize")

    pos = off_rsvmap
    while True:
        if pos + 16 > totalsize:
            raise PackError(f"{label} has an unterminated memory reservation map")
        address, size = struct.unpack_from(">QQ", blob, pos)
        pos += 16
        if address == 0 and size == 0:
            break
    reserve_map = blob[off_rsvmap:pos]

    pos = off_struct
    end = off_struct + size_struct
    root: FdtNode | None = None
    stack: list[FdtNode] = []
    string_offsets: dict[bytes, int] = {}
    saw_end = False
    while pos < end:
        token = struct.unpack_from(">I", blob, pos)[0]
        pos += 4
        if token == 1:  # FDT_BEGIN_NODE
            name_end = blob.find(b"\x00", pos, end)
            if name_end < 0:
                raise PackError(f"{label} has an unterminated node name")
            node = FdtNode(blob[pos:name_end], [], [])
            if stack:
                stack[-1].children.append(node)
            elif root is None:
                root = node
            else:
                raise PackError(f"{label} has more than one root node")
            stack.append(node)
            pos = align_up(name_end + 1, 4)
        elif token == 2:  # FDT_END_NODE
            if not stack:
                raise PackError(f"{label} has an unbalanced node end")
            stack.pop()
        elif token == 3:  # FDT_PROP
            if not stack or pos + 8 > end:
                raise PackError(f"{label} has a property outside a node")
            length, name_offset = struct.unpack_from(">II", blob, pos)
            pos += 8
            if name_offset >= size_strings:
                raise PackError(f"{label} has a property name outside the strings block")
            if pos + length > end:
                raise PackError(f"{label} has a property value outside the structure block")
            strings_start = off_strings + name_offset
            strings_end = off_strings + size_strings
            name_end = blob.find(b"\x00", strings_start, strings_end)
            if name_end < 0:
                raise PackError(f"{label} has an unterminated property name")
            name = blob[strings_start:name_end]
            string_offsets.setdefault(name, name_offset)
            stack[-1].properties.append(FdtProperty(name, blob[pos:pos + length]))
            pos = align_up(pos + length, 4)
        elif token == 4:  # FDT_NOP
            continue
        elif token == 9:  # FDT_END
            if stack:
                raise PackError(f"{label} ends inside a node")
            saw_end = True
            break
        else:
            raise PackError(f"{label} has unknown FDT token {token:#x}")
    if not saw_end:
        raise PackError(f"{label} has no FDT_END token")
    if any(blob[pos:end]):
        raise PackError(f"{label} has nonzero padding after FDT_END")
    if root is None:
        raise PackError(f"{label} has no root node")

    return FlatFdt(
        root=root,
        reserve_map=reserve_map,
        version=version,
        last_comp_version=last_comp_version,
        boot_cpuid=boot_cpuid,
        strings=blob[off_strings:off_strings + size_strings],
        string_offsets=string_offsets,
    )


def serialize_fdt(tree: FlatFdt) -> bytes:
    """Write a parsed tree back as a flat device tree.

    The original strings block is kept (new names are appended), so existing
    property name offsets and every untouched block stay meaningful.
    """
    strings = bytearray(tree.strings)
    offsets = dict(tree.string_offsets)

    def name_offset(name: bytes) -> int:
        offset = offsets.get(name)
        if offset is None:
            offset = len(strings)
            offsets[name] = offset
            strings.extend(name + b"\x00")
        return offset

    def emit_node(node: FdtNode) -> bytes:
        out = bytearray(struct.pack(">I", 1))
        out += node.name + b"\x00"
        out += b"\x00" * (-len(out) % 4)
        for prop in node.properties:
            out += struct.pack(">III", 3, len(prop.value), name_offset(prop.name))
            out += prop.value
            out += b"\x00" * (-len(prop.value) % 4)
        for child in node.children:
            out += emit_node(child)
        out += struct.pack(">I", 2)  # FDT_END_NODE
        return bytes(out)

    struct_block = emit_node(tree.root) + struct.pack(">I", 9)  # FDT_END
    off_struct = 40 + len(tree.reserve_map)
    off_strings = off_struct + len(struct_block)
    totalsize = off_strings + len(strings)
    if totalsize > 0xFFFFFFFF:
        raise PackError("rewritten FDT exceeds the 32-bit totalsize field")
    header = struct.pack(
        ">10I",
        FDT_MAGIC,
        totalsize,
        off_struct,
        off_strings,
        40,
        tree.version,
        tree.last_comp_version,
        tree.boot_cpuid,
        len(strings),
        len(struct_block),
    )
    return header + tree.reserve_map + struct_block + bytes(strings)


def validate_fdt(blob: bytes, label: str) -> dict[bytes, bytes]:
    """Validate one flattened device tree and return its root properties."""
    tree = parse_fdt(blob, label)
    return {prop.name: prop.value for prop in tree.root.properties}


def fdt_compatible(blob: bytes, label: str) -> list[str]:
    root = validate_fdt(blob, label)
    value = root.get(b"compatible")
    if value is None:
        raise PackError(f"{label} has no root compatible property")
    try:
        return [item.decode("ascii") for item in value.split(b"\x00") if item]
    except UnicodeDecodeError as exc:
        raise PackError(f"{label} has a non-ASCII compatible string") from exc


def validate_board_compatible(dtb: bytes, label: str) -> list[str]:
    """Return the root compatible list after checking the board match string.

    LK selects the appended DTB whose first root compatible names the board,
    so a tree that matches later in the list is never chosen.
    """
    compatible = fdt_compatible(dtb, label)
    first = compatible[0] if compatible else ""
    if not first.startswith(LIDAR_COMPATIBLE_PREFIX):
        raise PackError(
            f"{label} first root compatible {first!r} does not start with "
            f"{LIDAR_COMPATIBLE_PREFIX!r}; LK selects the appended DTB by it"
        )
    return compatible


def _fdt_child(node: FdtNode, name: bytes) -> FdtNode | None:
    for child in node.children:
        if child.name == name:
            return child
    return None


def _set_fdt_property(node: FdtNode, name: bytes, value: bytes) -> None:
    for prop in node.properties:
        if prop.name == name:
            prop.value = value
            return
    node.properties.append(FdtProperty(name, value))


def chosen_initrd_properties(
    ramdisk_addr: int, ramdisk_size: int
) -> tuple[tuple[bytes, bytes], tuple[bytes, bytes]]:
    """Return the /chosen properties that hand the ramdisk to the kernel.

    LK copies the ramdisk to the header ramdisk_addr on every boot but writes
    linux,initrd-* only for IDME bootmode 2/0x61, so the boot image has to
    publish the range itself.  The kernel reads the conventional two-cell
    64-bit pair; a single big-endian 8-byte value is that same tree data.
    """
    start = struct.pack(">Q", ramdisk_addr)
    end = struct.pack(">Q", ramdisk_addr + ramdisk_size)
    return (b"linux,initrd-start", start), (b"linux,initrd-end", end)


def set_chosen_initrd(
    dtb: bytes, ramdisk_addr: int, ramdisk_size: int, label: str
) -> bytes:
    """Return dtb with /chosen describing the ramdisk range from the header.

    A tree that already carries the exact values is returned unchanged, so a
    DTB built with the properties and one packed by this tool compare equal.
    """
    properties = chosen_initrd_properties(ramdisk_addr, ramdisk_size)
    tree = parse_fdt(dtb, label)
    chosen = _fdt_child(tree.root, b"chosen")
    if chosen is not None:
        current = {prop.name: prop.value for prop in chosen.properties}
        if all(current.get(name) == value for name, value in properties):
            return dtb
    else:
        chosen = FdtNode(b"chosen", [], [])
        tree.root.children.append(chosen)
    for name, value in properties:
        _set_fdt_property(chosen, name, value)
    return serialize_fdt(tree)


def validate_chosen_initrd(
    dtb: bytes, ramdisk_addr: int, ramdisk_size: int, label: str
) -> None:
    """Require /chosen to publish the ramdisk range from the boot header."""
    tree = parse_fdt(dtb, label)
    chosen = _fdt_child(tree.root, b"chosen")
    if chosen is None:
        raise PackError(f"{label} has no /chosen node for the initrd properties")
    current = {prop.name: prop.value for prop in chosen.properties}
    for name, expected in chosen_initrd_properties(ramdisk_addr, ramdisk_size):
        text = name.decode("ascii")
        value = current.get(name)
        if value is None:
            raise PackError(f"{label} /chosen is missing {text}")
        if len(value) != 8:
            raise PackError(
                f"{label} /chosen {text} is {len(value)} bytes, expected the "
                "two-cell 64-bit form"
            )
        actual = struct.unpack(">Q", value)[0]
        wanted = struct.unpack(">Q", expected)[0]
        if actual != wanted:
            raise PackError(
                f"{label} /chosen {text} is {actual:#x}, expected {wanted:#x} "
                "from ramdisk_addr and the ramdisk size"
            )


def validate_dtb_sizes(dtbs: Sequence[bytes], label: str) -> None:
    """Reject a DTB LK cannot copy to its fixed 0x80000 byte window."""
    for index, blob in enumerate(dtbs):
        if len(blob) > MAX_DTB_SIZE:
            raise PackError(
                f"{label} DTB {index} is {len(blob)} bytes, over the "
                f"{MAX_DTB_SIZE:#x} byte limit LK copies to {TAGS_ADDR:#x}"
            )


def split_dtbs(region: bytes) -> list[bytes]:
    dtbs: list[bytes] = []
    pos = 0
    while pos < len(region):
        if len(region) - pos < 40:
            raise PackError("trailing bytes after the last appended DTB")
        totalsize = struct.unpack_from(">I", region, pos + 4)[0]
        if totalsize < 40 or pos + totalsize > len(region):
            raise PackError(f"appended DTB at {pos:#x} has an invalid totalsize")
        blob = region[pos:pos + totalsize]
        validate_fdt(blob, f"appended DTB {len(dtbs)}")
        dtbs.append(blob)
        pos += totalsize
    return dtbs


def parse_trailer(region: bytes) -> bytes | None:
    """Return the optional DER blob and reject any other trailer content."""
    if not region:
        return None
    if region[0] != 0x30:
        if any(region):
            raise PackError("stock trailer is neither zero nor a DER certificate")
        return None
    if len(region) < 4 or region[1] != 0x82:
        raise PackError("stock trailer starts with an unsupported DER header")
    length = 4 + struct.unpack_from(">H", region, 2)[0]
    if length > len(region):
        raise PackError("stock trailer DER length exceeds the image")
    if any(region[length:]):
        raise PackError("unexpected nonzero bytes after the stock certificate")
    return region[:length]


@dataclass(frozen=True)
class StockImage:
    data: bytes
    header: AndroidHeader
    mtk_header: bytes
    kernel_image: bytes
    dtbs: tuple[bytes, ...]
    ramdisk: bytes
    ramdisk_offset: int
    trailer_offset: int
    certificate: bytes | None
    pvt_sha256: str


def parse_stock(path: str, expected_pvt_sha256: str) -> StockImage:
    data = read_file(path)
    if len(data) != IMAGE_SIZE:
        raise PackError(
            f"stock image is {len(data)} bytes, expected {IMAGE_SIZE}"
        )
    header = parse_android_header(data)
    validate_stock_header(header)

    kernel_end = PAGE_SIZE + header.kernel_size
    if kernel_end > IMAGE_SIZE:
        raise PackError("kernel section exceeds the 16 MiB envelope")
    kernel_section = data[PAGE_SIZE:kernel_end]
    validate_mtk_header(kernel_section[:MTK_HEADER_SIZE], header.kernel_size)
    payload = kernel_section[MTK_HEADER_SIZE:]

    kernel_image, gzip_size = decompress_first_gzip(payload, "stock kernel")
    validate_arm64_image(kernel_image, "stock kernel payload")

    dtb_region = payload[gzip_size:]
    dtbs = split_dtbs(dtb_region)
    if len(dtbs) != STOCK_DTB_COUNT:
        raise PackError(
            f"stock image has {len(dtbs)} appended DTBs, expected {STOCK_DTB_COUNT}"
        )

    pvt_digest = sha256_hex(dtbs[STOCK_DTB_INDEX])
    if pvt_digest != expected_pvt_sha256:
        raise PackError(
            "stock appended DTB index 4 is not the expected PVT blob: "
            f"{pvt_digest}"
        )
    if LIDAR_PVT_COMPATIBLE not in fdt_compatible(
        dtbs[STOCK_DTB_INDEX], "stock PVT DTB"
    ):
        raise PackError("stock appended DTB index 4 is not a Lidar PVT tree")

    ramdisk_offset = PAGE_SIZE + align_up(header.kernel_size, PAGE_SIZE)
    ramdisk_end = ramdisk_offset + header.ramdisk_size
    if ramdisk_offset < kernel_end or ramdisk_end > IMAGE_SIZE:
        raise PackError("stock ramdisk section is out of range")
    ramdisk = data[ramdisk_offset:ramdisk_end]
    decompressed, consumed = decompress_first_gzip(ramdisk, "stock ramdisk")
    if consumed != len(ramdisk):
        raise PackError("stock ramdisk section has trailing bytes")
    if not decompressed:
        raise PackError("stock ramdisk decompresses to nothing")

    trailer_offset = ramdisk_offset + align_up(header.ramdisk_size, PAGE_SIZE)
    if trailer_offset < ramdisk_end or trailer_offset > IMAGE_SIZE:
        raise PackError("stock trailer offset is out of range")
    if any(data[ramdisk_end:trailer_offset]):
        raise PackError("stock page padding after the ramdisk is not zero")
    certificate = parse_trailer(data[trailer_offset:])

    if android_id(kernel_section, ramdisk) != header.android_id:
        raise PackError("stock Android id does not match the stock sections")

    return StockImage(
        data=data,
        header=header,
        mtk_header=kernel_section[:MTK_HEADER_SIZE],
        kernel_image=kernel_image,
        dtbs=tuple(dtbs),
        ramdisk=ramdisk,
        ramdisk_offset=ramdisk_offset,
        trailer_offset=trailer_offset,
        certificate=certificate,
        pvt_sha256=expected_pvt_sha256,
    )


@dataclass(frozen=True)
class BuildResult:
    image: bytes
    kernel_size: int
    gzip_size: int
    dtb_size: int
    ramdisk_offset: int
    trailer_offset: int


def build_image(
    stock: StockImage,
    kernel_image: bytes,
    dtb: bytes,
    ramdisk: bytes | None = None,
    cmdline_append: str | None = None,
) -> BuildResult:
    validate_arm64_image(kernel_image, "kernel")
    compatible = validate_board_compatible(dtb, "new DTB")
    if LIDAR_PVT_COMPATIBLE not in compatible:
        raise PackError(
            f"new DTB lacks the {LIDAR_PVT_COMPATIBLE!r} compatible string"
        )

    gzip_kernel = gzip_deterministic(kernel_image)
    if ramdisk is None:
        ramdisk = stock.ramdisk
    else:
        validate_ramdisk(ramdisk, "new ramdisk")
    # The stock appended DTBs stay byte-identical; only the replacement DTB,
    # which is the one LK can select for this board, gets the ramdisk range.
    if ramdisk:
        dtb = set_chosen_initrd(
            dtb, stock.header.ramdisk_addr, len(ramdisk), "new DTB"
        )
    dtbs = list(stock.dtbs)
    dtbs[STOCK_DTB_INDEX] = dtb
    validate_dtb_sizes(dtbs, "appended")
    dtb_collection = b"".join(dtbs)
    if not dtb_collection:
        raise PackError("appended DTB collection is empty")

    cmdline = stock.header.cmdline
    extra_cmdline = stock.header.extra_cmdline
    if cmdline_append is not None:
        cmdline, extra_cmdline = append_cmdline(
            stock.header, encode_cmdline_append(cmdline_append)
        )
    validate_bootopt(cmdline, extra_cmdline)

    kernel_size = MTK_HEADER_SIZE + len(gzip_kernel) + len(dtb_collection)
    if kernel_size > 0xFFFFFFFF:
        raise PackError("kernel section does not fit the Android v0 size field")
    if PAGE_SIZE + kernel_size > IMAGE_SIZE:
        raise PackError("kernel section exceeds the 16 MiB envelope")

    ramdisk_offset = PAGE_SIZE + align_up(kernel_size, PAGE_SIZE)
    ramdisk_end = ramdisk_offset + len(ramdisk)
    if ramdisk_end > IMAGE_SIZE:
        raise PackError(
            "kernel and ramdisk exceed the 16 MiB envelope: "
            f"{ramdisk_end} > {IMAGE_SIZE}"
        )

    kernel_section = bytearray(stock.mtk_header)
    struct.pack_into("<I", kernel_section, 4, len(gzip_kernel) + len(dtb_collection))
    kernel_section += gzip_kernel + dtb_collection
    if len(kernel_section) != kernel_size:
        raise PackError("internal kernel section size mismatch")

    out = bytearray(IMAGE_SIZE)
    out[:BOOT_HEADER_SIZE] = stock.header.raw
    out[CMDLINE_OFFSET:CMDLINE_OFFSET + CMDLINE_SIZE] = cmdline
    out[
        EXTRA_CMDLINE_OFFSET:EXTRA_CMDLINE_OFFSET + EXTRA_CMDLINE_SIZE
    ] = extra_cmdline
    struct.pack_into("<I", out, 8, kernel_size)
    struct.pack_into("<I", out, 16, len(ramdisk))
    out[576:596] = android_id(bytes(kernel_section), ramdisk)
    out[PAGE_SIZE:PAGE_SIZE + kernel_size] = kernel_section
    out[ramdisk_offset:ramdisk_end] = ramdisk
    # The trailer stays zero: the stock certificate is not carried over, and
    # this tool emits no signature.

    trailer_offset = ramdisk_offset + align_up(len(ramdisk), PAGE_SIZE)
    return BuildResult(
        image=bytes(out),
        kernel_size=kernel_size,
        gzip_size=len(gzip_kernel),
        dtb_size=len(dtb_collection),
        ramdisk_offset=ramdisk_offset,
        trailer_offset=trailer_offset,
    )


def verify_image(
    output_path: str,
    stock: StockImage,
    kernel_image: bytes,
    dtb: bytes,
    ramdisk: bytes | None = None,
    cmdline_append: str | None = None,
) -> BuildResult:
    if ramdisk is not None:
        validate_ramdisk(ramdisk, "new ramdisk")
    data = read_file(output_path)
    if len(data) != IMAGE_SIZE:
        raise PackError(
            f"output image is {len(data)} bytes, expected {IMAGE_SIZE}"
        )
    header = parse_android_header(data)
    validate_stock_header(header)

    if header.name != stock.header.name:
        raise PackError("output header name differs from stock")
    expected_cmdline = stock.header.cmdline
    expected_extra_cmdline = stock.header.extra_cmdline
    if cmdline_append is not None:
        expected_cmdline, expected_extra_cmdline = append_cmdline(
            stock.header, encode_cmdline_append(cmdline_append)
        )
        source = "stock plus --cmdline-append"
    else:
        source = "stock"
    if header.cmdline != expected_cmdline:
        raise PackError(f"output header cmdline differs from {source}")
    if header.extra_cmdline != expected_extra_cmdline:
        raise PackError(f"output header extra cmdline differs from {source}")
    validate_bootopt(header.cmdline, header.extra_cmdline)

    expected_ramdisk = stock.ramdisk if ramdisk is None else ramdisk
    if header.ramdisk_size != len(expected_ramdisk):
        raise PackError(
            "output ramdisk size differs from "
            + ("stock" if ramdisk is None else "--ramdisk FILE")
        )

    kernel_end = PAGE_SIZE + header.kernel_size
    if kernel_end > IMAGE_SIZE:
        raise PackError("output kernel section exceeds the envelope")
    kernel_section = data[PAGE_SIZE:kernel_end]
    validate_mtk_header(kernel_section[:MTK_HEADER_SIZE], header.kernel_size)
    payload = kernel_section[MTK_HEADER_SIZE:]

    payload_image, gzip_size = decompress_first_gzip(payload, "output kernel")
    if payload_image != kernel_image:
        raise PackError("output kernel payload does not match the supplied Image")

    dtbs = split_dtbs(payload[gzip_size:])
    if len(dtbs) != len(stock.dtbs):
        raise PackError(
            f"output has {len(dtbs)} appended DTBs, expected {len(stock.dtbs)}"
        )
    validate_dtb_sizes(dtbs, "output")
    expected_dtb = dtb
    if header.ramdisk_size:
        expected_dtb = set_chosen_initrd(
            dtb, header.ramdisk_addr, header.ramdisk_size, "new DTB"
        )
    for index, (actual, expected) in enumerate(zip(dtbs, stock.dtbs)):
        if index == STOCK_DTB_INDEX:
            if header.ramdisk_size:
                validate_chosen_initrd(
                    actual,
                    header.ramdisk_addr,
                    header.ramdisk_size,
                    "output DTB index 4",
                )
            if actual != expected_dtb:
                raise PackError(
                    "output DTB index 4 does not match the new DTB plus the "
                    "header initrd properties"
                )
        elif actual != expected:
            raise PackError(f"output DTB index {index} changed from stock")
    output_compatible = validate_board_compatible(
        dtbs[STOCK_DTB_INDEX], "output DTB index 4"
    )
    if LIDAR_PVT_COMPATIBLE not in output_compatible:
        raise PackError("output DTB index 4 is not a Lidar PVT tree")
    if sha256_hex(stock.dtbs[STOCK_DTB_INDEX]) != stock.pvt_sha256:
        raise PackError("stock PVT DTB hash changed")

    ramdisk_offset = PAGE_SIZE + align_up(header.kernel_size, PAGE_SIZE)
    ramdisk_end = ramdisk_offset + header.ramdisk_size
    if ramdisk_end > IMAGE_SIZE:
        raise PackError("output ramdisk section exceeds the envelope")
    actual_ramdisk = data[ramdisk_offset:ramdisk_end]
    if actual_ramdisk != expected_ramdisk:
        raise PackError(
            "output ramdisk does not match "
            + ("the stock ramdisk" if ramdisk is None else "--ramdisk FILE")
        )
    trailer_offset = ramdisk_offset + align_up(header.ramdisk_size, PAGE_SIZE)
    if any(data[ramdisk_end:trailer_offset]):
        raise PackError("output ramdisk page padding is not zero")
    if any(data[trailer_offset:]):
        raise PackError("output trailer is not zero; a signature may be retained")

    if android_id(kernel_section, actual_ramdisk) != header.android_id:
        raise PackError("output Android id does not match the output sections")

    return BuildResult(
        image=data,
        kernel_size=header.kernel_size,
        gzip_size=gzip_size,
        dtb_size=len(payload) - gzip_size,
        ramdisk_offset=ramdisk_offset,
        trailer_offset=trailer_offset,
    )


def _same_path(left: str, right: str) -> bool:
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except OSError:
        return False


def _print_common(stock_path: str, stock: StockImage, kernel: bytes, dtb: bytes) -> None:
    print(f"stock: {stock_path}")
    print(f"stock sha256: {sha256_hex(stock.data)}")
    print(f"kernel sha256: {sha256_hex(kernel)}")
    print(f"dtb sha256: {sha256_hex(dtb)}")
    print(f"stock PVT DTB sha256: {sha256_hex(stock.dtbs[STOCK_DTB_INDEX])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify a development Lidar Android v0 boot image."
    )
    parser.add_argument("--stock", required=True, help="stock 16 MiB boot_a.bin")
    parser.add_argument("--kernel", required=True, help="new ARM64 Image")
    parser.add_argument("--dtb", required=True, help="new compiled Lidar DTB")
    parser.add_argument("--output", help="development image to write")
    parser.add_argument("--verify", metavar="IMAGE", help="verify an existing image")
    parser.add_argument(
        "--ramdisk",
        metavar="FILE",
        help=(
            "use FILE instead of the stock ramdisk; FILE must be one complete "
            "gzip stream holding a newc cpio archive with an executable "
            "regular-file init"
        ),
    )
    parser.add_argument(
        "--cmdline-append",
        metavar="TEXT",
        help=(
            "append TEXT to the stock kernel command line once, separated by "
            "one space; without this option the header cmdline stays "
            "byte-identical to stock"
        ),
    )
    parser.add_argument(
        "--expected-pvt-sha256",
        default=STOCK_PVT_SHA256,
        help="expected SHA-256 of stock appended DTB index 4",
    )
    args = parser.parse_args(argv)

    if args.verify and args.output:
        parser.error("--verify and --output are mutually exclusive")
    if not args.verify and not args.output:
        parser.error("--output is required unless --verify is used")

    kernel = read_file(args.kernel)
    dtb = read_file(args.dtb)
    ramdisk = read_file(args.ramdisk) if args.ramdisk else None
    stock = parse_stock(args.stock, args.expected_pvt_sha256)

    if args.output and _same_path(args.output, args.stock):
        raise PackError("refusing to overwrite the stock image")
    if args.output and any(
        _same_path(args.output, path)
        for path in (args.kernel, args.dtb, args.ramdisk)
        if path
    ):
        raise PackError("refusing to overwrite an input file")

    _print_common(args.stock, stock, kernel, dtb)
    if args.ramdisk:
        print(f"ramdisk: {args.ramdisk}")
    if args.cmdline_append is not None:
        print(f"cmdline append: {args.cmdline_append}")

    if args.verify:
        result = verify_image(
            args.verify,
            stock,
            kernel,
            dtb,
            ramdisk=ramdisk,
            cmdline_append=args.cmdline_append,
        )
        print(f"verify: OK {args.verify}")
        print(f"image sha256: {sha256_hex(result.image)}")
        print(f"kernel_size: {result.kernel_size}")
        print(f"gzip kernel bytes: {result.gzip_size}")
        print(f"DTB collection bytes: {result.dtb_size}")
        header = parse_android_header(result.image)
        print(
            f"initrd: {header.ramdisk_addr:#x}.."
            f"{header.ramdisk_addr + header.ramdisk_size:#x} "
            f"({header.ramdisk_size} bytes)"
        )
        print(f"ramdisk offset: {result.ramdisk_offset:#x}")
        print(f"trailer offset: {result.trailer_offset:#x} (all zero)")
        print("signature: absent; stock certificate was not retained")
        print("hardware evidence: none")
        return 0

    result = build_image(
        stock,
        kernel,
        dtb,
        ramdisk=ramdisk,
        cmdline_append=args.cmdline_append,
    )
    output = os.path.abspath(args.output)
    try:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "wb") as handle:
            handle.write(result.image)
    except OSError as exc:
        raise PackError(f"cannot write {output}: {exc}") from exc
    print(f"output: {output}")
    print(f"image sha256: {sha256_hex(result.image)}")
    print(f"kernel_size: {result.kernel_size}")
    print(f"gzip kernel bytes: {result.gzip_size}")
    print(f"DTB collection bytes: {result.dtb_size}")
    header = parse_android_header(result.image)
    print(
        f"initrd: {header.ramdisk_addr:#x}.."
        f"{header.ramdisk_addr + header.ramdisk_size:#x} "
        f"({header.ramdisk_size} bytes)"
    )
    print(f"ramdisk offset: {result.ramdisk_offset:#x}")
    print(f"trailer offset: {result.trailer_offset:#x} (all zero)")
    print("signature: absent; stock certificate was not retained")
    print("hardware evidence: none")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
