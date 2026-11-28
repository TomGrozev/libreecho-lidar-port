#!/usr/bin/env python3
"""Unit tests for the Lidar boot image packager. No device access needed."""

from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pack_boot as pb


def make_arm64_image(tag: bytes = b"test") -> bytes:
    image = bytearray(0x2000 + len(tag))
    image[0x08:0x10] = struct.pack("<Q", 0x080000)
    image[0x38:0x3C] = b"ARMd"
    remaining = len(image) - 0x1000
    tail = (tag * (remaining // len(tag) + 1))[:remaining]
    image[0x1000:] = tail
    return bytes(image)


def make_fdt(model: str, compatible: list[str]) -> bytes:
    values = [
        (b"model", model.encode() + b"\x00"),
        (b"compatible", b"".join(item.encode() + b"\x00" for item in compatible)),
    ]
    strings = b""
    name_offsets: dict[bytes, int] = {}
    for name, _value in values:
        if name not in name_offsets:
            name_offsets[name] = len(strings)
            strings += name + b"\x00"

    struct_block = struct.pack(">I", 1) + b"\x00" * 4  # root node, empty name
    for name, value in values:
        struct_block += struct.pack(">III", 3, len(value), name_offsets[name])
        struct_block += value
        struct_block += b"\x00" * (-len(value) % 4)
    struct_block += struct.pack(">II", 2, 9)  # FDT_END_NODE, FDT_END

    off_rsvmap = 40
    off_struct = off_rsvmap + 16
    off_strings = off_struct + len(struct_block)
    totalsize = off_strings + len(strings)
    header = struct.pack(
        ">10I",
        pb.FDT_MAGIC,
        totalsize,
        off_struct,
        off_strings,
        off_rsvmap,
        17,
        16,
        0,
        len(strings),
        len(struct_block),
    )
    return header + b"\x00" * 16 + struct_block + strings


def make_mtk_header(payload_size: int) -> bytes:
    header = bytearray(pb.MTK_HEADER_SIZE)
    struct.pack_into("<II", header, 0, pb.MTK_MAGIC, payload_size)
    header[8:16] = pb.MTK_NAME
    header[pb.MTK_FILLER_OFFSET:] = b"\xff" * (
        pb.MTK_HEADER_SIZE - pb.MTK_FILLER_OFFSET
    )
    return bytes(header)


def make_certificate() -> bytes:
    body = b"fake test certificate body"
    return b"\x30\x82" + struct.pack(">H", len(body)) + body


def make_cpio(entries: list[tuple[str, int, bytes]]) -> bytes:
    archive = bytearray()
    for ino, (name, mode, data) in enumerate(entries, 1):
        name_bytes = name.encode("ascii") + b"\x00"
        fields = (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name_bytes), 0)
        archive += b"070701" + b"".join(
            f"{value:08X}".encode("ascii") for value in fields
        )
        archive += name_bytes
        # 4-byte name alignment, as the real stock cpio uses. With the
        # 110-byte header, the short "act" name lands unaligned and needs a
        # two-byte pad, so the fixture covers the parser's name-padding path.
        archive += b"\x00" * (-len(archive) % 4)
        archive += data + b"\x00" * (-len(data) % 4)
    trailer = pb.CPIO_TRAILER
    fields = (len(entries) + 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, len(trailer), 0)
    archive += b"070701" + b"".join(
        f"{value:08X}".encode("ascii") for value in fields
    )
    archive += trailer
    archive += b"\x00" * (-len(archive) % 4)
    archive += b"\x00" * (-len(archive) % 512)
    return bytes(archive)


STOCK_INIT_RC = b"""\
on early-init
    write /proc/1/oom_score_adj -1000

on fs
    mount_all /fstab.mt6765
    mount functionfs adb /dev/usb-ffs/adb mode=0660,uid=1000,gid=1000
    chmod 0660 /dev/usb-ffs/adb/ep0

on boot
    write /proc/sys/kernel/panic 5
    start console

on property:ro.debuggable=1
    start adbd
"""

STOCK_DEFAULT_PROP = b"""\
ro.secure=1
ro.adb.secure=1
ro.debuggable=0
ro.allow.mock.location=0
persist.sys.usb.config=adb
"""

# A long suffix that crosses the 511-byte cmdline field boundary, so the
# append tests cover the split the v0 header forces.
PSTORE_CMDLINE_SUFFIX = (
    "console=ttyS0,921600n1 "
    "pstore_blk.blkdev=PARTUUID=<PARTUUID_12> "
    "pstore_blk.best_effort=y "
    "pstore_blk.pmsg_size=0 "
    "pstore_blk.console_size=64 "
    "pstore_blk.kmsg_size=64 "
    "pstore_blk.max_reason=5"
)


class Fixture:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.kernel = make_arm64_image(b"stock-kernel")
        self.dtbs = []
        for index in range(pb.STOCK_DTB_COUNT):
            if index == pb.STOCK_DTB_INDEX:
                model = "Amazon Lidar PVT"
                compatible = [pb.LIDAR_PVT_COMPATIBLE, "amzn,lidar"]
            else:
                model = f"Amazon Test {index}"
                compatible = [f"amzn,test-{index}", "amzn,lidar"]
            self.dtbs.append(make_fdt(model, compatible))
        self.pvt_sha256 = hashlib.sha256(
            self.dtbs[pb.STOCK_DTB_INDEX]
        ).hexdigest()

        gzip_kernel = pb.gzip_deterministic(self.kernel)
        kernel_payload = gzip_kernel + b"".join(self.dtbs)
        self.kernel_section = make_mtk_header(len(kernel_payload)) + kernel_payload
        self.ramdisk_entries = [
            ("act", 0o040755, b""),
            ("init", 0o100750, b"\x7fELF-synthetic-init"),
            ("init.rc", 0o100644, STOCK_INIT_RC),
            ("default.prop", 0o100644, STOCK_DEFAULT_PROP),
            ("init.environ.rc", 0o100644, b"export PATH /sbin\n"),
            ("sbin/adbd", 0o100755, b"\x7fELF-synthetic-adbd"),
            ("res", 0o040755, b""),
            ("sepolicy", 0o100644, b"test sepolicy"),
        ]
        self.ramdisk_cpio = make_cpio(self.ramdisk_entries)
        self.ramdisk = pb.gzip_deterministic(self.ramdisk_cpio)
        self.certificate = make_certificate()

        header = bytearray(pb.BOOT_HEADER_SIZE)
        header[:8] = pb.ANDROID_MAGIC
        struct.pack_into(
            "<10I",
            header,
            8,
            len(self.kernel_section),
            pb.KERNEL_ADDR,
            len(self.ramdisk),
            pb.RAMDISK_ADDR,
            0,
            pb.SECOND_ADDR,
            pb.TAGS_ADDR,
            pb.PAGE_SIZE,
            0,
            pb.OS_VERSION,
        )
        cmdline = b"bootopt=64S3,32N2,64N2 buildvariant=user\x00"
        header[64:64 + len(cmdline)] = cmdline
        header[576:596] = pb.android_id(self.kernel_section, self.ramdisk)

        self.ramdisk_offset = pb.PAGE_SIZE + pb.align_up(
            len(self.kernel_section), pb.PAGE_SIZE
        )
        self.trailer_offset = self.ramdisk_offset + pb.align_up(
            len(self.ramdisk), pb.PAGE_SIZE
        )
        self.first_dtb_offset = pb.PAGE_SIZE + pb.MTK_HEADER_SIZE + len(gzip_kernel)

        self.image = bytearray(pb.IMAGE_SIZE)
        self.image[:pb.BOOT_HEADER_SIZE] = header
        self.image[pb.PAGE_SIZE:pb.PAGE_SIZE + len(self.kernel_section)] = (
            self.kernel_section
        )
        self.image[
            self.ramdisk_offset:self.ramdisk_offset + len(self.ramdisk)
        ] = self.ramdisk
        self.image[
            self.trailer_offset:self.trailer_offset + len(self.certificate)
        ] = self.certificate

        self.stock_path = directory / "stock-boot.img"
        self.stock_path.write_bytes(bytes(self.image))

    def write_variant(self, name: str, mutate) -> Path:
        image = bytearray(self.image)
        mutate(image)
        path = self.directory / name
        path.write_bytes(bytes(image))
        return path

    def parse(self):
        return pb.parse_stock(str(self.stock_path), self.pvt_sha256)

    def write_new_dtb(self, dtb: bytes | None = None) -> Path:
        path = self.directory / "libreecho-lidar.dtb"
        path.write_bytes(dtb if dtb is not None else self.dtbs[pb.STOCK_DTB_INDEX])
        return path

    def write_kernel(self, kernel: bytes | None = None) -> Path:
        path = self.directory / "Image"
        path.write_bytes(kernel if kernel is not None else self.kernel)
        return path


class PackBootTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.directory = Path(self.tempdir.name)
        self.fixture = Fixture(self.directory)
        self.stock = self.fixture.parse()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def new_dtb(self) -> bytes:
        return make_fdt(
            "Amazon Lidar PVT Development",
            [pb.LIDAR_PVT_COMPATIBLE, "amzn,lidar", "amzn,lidar-dev"],
        )

    def archive_of(self, ramdisk: bytes):
        raw, consumed = pb.decompress_first_gzip(ramdisk, "test ramdisk")
        self.assertEqual(consumed, len(ramdisk))
        return pb.parse_cpio(raw, "test ramdisk")

    def image_ramdisk(self, image: bytes) -> bytes:
        header = pb.parse_android_header(image)
        offset = pb.PAGE_SIZE + pb.align_up(header.kernel_size, pb.PAGE_SIZE)
        return image[offset:offset + header.ramdisk_size]

    def appended_dtbs(self, image: bytes) -> list[bytes]:
        header = pb.parse_android_header(image)
        section = image[pb.PAGE_SIZE:pb.PAGE_SIZE + header.kernel_size]
        _payload, gzip_size = pb.decompress_first_gzip(
            section[pb.MTK_HEADER_SIZE:], "test"
        )
        return pb.split_dtbs(section[pb.MTK_HEADER_SIZE + gzip_size:])

    def appended_dtb(self, image: bytes) -> bytes:
        return self.appended_dtbs(image)[pb.STOCK_DTB_INDEX]

    def chosen_properties(self, dtb: bytes) -> dict[bytes, bytes]:
        tree = pb.parse_fdt(dtb, "test DTB")
        chosen = next(
            child for child in tree.root.children if child.name == b"chosen"
        )
        return {prop.name: prop.value for prop in chosen.properties}

    def make_ramdisk(self, entries=None) -> bytes:
        if entries is None:
            entries = [
                ("act", 0o040755, b""),
                ("init", 0o100750, b"\x7fELF-busybox-init"),
                ("bin/busybox", 0o100755, b"\x7fELF-busybox"),
            ]
        return pb.gzip_deterministic(make_cpio(entries))

    def stock_cmdline_text(self) -> bytes:
        return self.stock.header.cmdline.split(b"\x00", 1)[0]

    def build_with_suffix(self, suffix: str):
        dtb = self.new_dtb()
        result = pb.build_image(
            self.stock,
            self.fixture.kernel,
            dtb,
            cmdline_append=suffix,
        )
        return dtb, result

    def effective_cmdline(self, image: bytes) -> bytes:
        """Join the two asciiz fields the way the bootloader does."""
        header = pb.parse_android_header(image)
        return (
            header.cmdline.split(b"\x00", 1)[0]
            + header.extra_cmdline.split(b"\x00", 1)[0]
        )

    def test_round_trip_and_retained_blobs(self) -> None:
        dtb = self.new_dtb()
        expected_dtb = pb.set_chosen_initrd(
            dtb,
            self.stock.header.ramdisk_addr,
            len(self.fixture.ramdisk),
            "test DTB",
        )
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        self.assertEqual(len(result.image), pb.IMAGE_SIZE)
        self.assertFalse(any(result.image[result.trailer_offset:]))

        output = self.directory / "development.img"
        output.write_bytes(result.image)
        verified = pb.verify_image(
            str(output), self.stock, self.fixture.kernel, dtb
        )
        self.assertEqual(verified.kernel_size, result.kernel_size)

        header = pb.parse_android_header(result.image)
        section = result.image[pb.PAGE_SIZE:pb.PAGE_SIZE + header.kernel_size]
        _image, gzip_size = pb.decompress_first_gzip(
            section[pb.MTK_HEADER_SIZE:], "test"
        )
        out_dtbs = pb.split_dtbs(section[pb.MTK_HEADER_SIZE + gzip_size:])
        self.assertEqual(len(out_dtbs), pb.STOCK_DTB_COUNT)
        for index, blob in enumerate(out_dtbs):
            if index == pb.STOCK_DTB_INDEX:
                self.assertEqual(blob, expected_dtb)
            else:
                self.assertEqual(blob, self.fixture.dtbs[index])
        self.assertEqual(
            result.image[
                result.ramdisk_offset:
                result.ramdisk_offset + len(self.fixture.ramdisk)
            ],
            self.fixture.ramdisk,
        )

    def test_stock_image_is_not_modified(self) -> None:
        before = self.fixture.stock_path.read_bytes()
        result = pb.build_image(self.stock, self.fixture.kernel, self.new_dtb())
        self.assertNotEqual(result.image, before)
        self.assertEqual(self.fixture.stock_path.read_bytes(), before)

    def test_output_is_deterministic(self) -> None:
        dtb = self.new_dtb()
        first = pb.build_image(self.stock, self.fixture.kernel, dtb)
        second = pb.build_image(self.stock, self.fixture.kernel, dtb)
        self.assertEqual(first.image, second.image)

    def test_certificate_is_dropped(self) -> None:
        self.assertIsNotNone(self.stock.certificate)
        result = pb.build_image(self.stock, self.fixture.kernel, self.new_dtb())
        self.assertFalse(any(result.image[result.trailer_offset:]))

    def test_cli_pack_and_verify(self) -> None:
        dtb_path = self.fixture.write_new_dtb(self.new_dtb())
        kernel_path = self.fixture.write_kernel()
        output = self.directory / "artifacts" / "boot-development.img"
        common = [
            "--stock", str(self.fixture.stock_path),
            "--kernel", str(kernel_path),
            "--dtb", str(dtb_path),
            "--expected-pvt-sha256", self.fixture.pvt_sha256,
        ]
        self.assertEqual(pb.main(common + ["--output", str(output)]), 0)
        self.assertTrue(output.is_file())
        self.assertEqual(pb.main(common + ["--verify", str(output)]), 0)

    def test_cli_ramdisk_pack_and_verify(self) -> None:
        dtb_path = self.fixture.write_new_dtb(self.new_dtb())
        kernel_path = self.fixture.write_kernel()
        ramdisk = self.make_ramdisk()
        ramdisk_path = self.directory / "initramfs.cpio.gz"
        ramdisk_path.write_bytes(ramdisk)
        output = self.directory / "artifacts" / "boot-ramdisk.img"
        common = [
            "--stock", str(self.fixture.stock_path),
            "--kernel", str(kernel_path),
            "--dtb", str(dtb_path),
            "--expected-pvt-sha256", self.fixture.pvt_sha256,
            "--ramdisk", str(ramdisk_path),
        ]
        self.assertEqual(pb.main(common + ["--output", str(output)]), 0)
        self.assertEqual(self.image_ramdisk(output.read_bytes()), ramdisk)
        self.assertEqual(pb.main(common + ["--verify", str(output)]), 0)
        with self.assertRaises(pb.PackError):
            pb.main(
                [
                    "--stock", str(self.fixture.stock_path),
                    "--kernel", str(kernel_path),
                    "--dtb", str(dtb_path),
                    "--expected-pvt-sha256", self.fixture.pvt_sha256,
                    "--verify", str(output),
                ]
            )

    def test_cli_ramdisk_without_init_is_rejected(self) -> None:
        dtb_path = self.fixture.write_new_dtb(self.new_dtb())
        kernel_path = self.fixture.write_kernel()
        bad_path = self.directory / "bad-ramdisk.cpio.gz"
        bad_path.write_bytes(
            pb.gzip_deterministic(make_cpio([("act", 0o040755, b"")]))
        )
        with self.assertRaises(pb.PackError) as caught:
            pb.main(
                [
                    "--stock", str(self.fixture.stock_path),
                    "--kernel", str(kernel_path),
                    "--dtb", str(dtb_path),
                    "--expected-pvt-sha256", self.fixture.pvt_sha256,
                    "--ramdisk", str(bad_path),
                    "--output", str(self.directory / "bad-ramdisk.img"),
                ]
            )
        self.assertIn("init", str(caught.exception))

    def test_cli_cmdline_append_pack_and_verify(self) -> None:
        dtb_path = self.fixture.write_new_dtb(self.new_dtb())
        kernel_path = self.fixture.write_kernel()
        output = self.directory / "boot-cmdline-pstore.img"
        common = [
            "--stock", str(self.fixture.stock_path),
            "--kernel", str(kernel_path),
            "--dtb", str(dtb_path),
            "--expected-pvt-sha256", self.fixture.pvt_sha256,
            "--cmdline-append", PSTORE_CMDLINE_SUFFIX,
        ]
        self.assertEqual(pb.main(common + ["--output", str(output)]), 0)
        self.assertTrue(output.is_file())
        self.assertEqual(
            self.effective_cmdline(output.read_bytes()),
            self.stock_cmdline_text()
            + b" "
            + PSTORE_CMDLINE_SUFFIX.encode("utf-8"),
        )
        self.assertEqual(pb.main(common + ["--verify", str(output)]), 0)
        with self.assertRaises(pb.PackError):
            pb.main(
                [
                    "--stock", str(self.fixture.stock_path),
                    "--kernel", str(kernel_path),
                    "--dtb", str(dtb_path),
                    "--expected-pvt-sha256", self.fixture.pvt_sha256,
                    "--verify", str(output),
                ]
            )

    def test_cli_refuses_to_overwrite_stock(self) -> None:
        dtb_path = self.fixture.write_new_dtb(self.new_dtb())
        kernel_path = self.fixture.write_kernel()
        with self.assertRaises(pb.PackError):
            pb.main(
                [
                    "--stock", str(self.fixture.stock_path),
                    "--kernel", str(kernel_path),
                    "--dtb", str(dtb_path),
                    "--expected-pvt-sha256", self.fixture.pvt_sha256,
                    "--output", str(self.fixture.stock_path),
                ]
            )

    def test_default_cmdline_stays_byte_identical(self) -> None:
        dtb = self.new_dtb()
        implicit = pb.build_image(self.stock, self.fixture.kernel, dtb)
        explicit = pb.build_image(
            self.stock, self.fixture.kernel, dtb, cmdline_append=None
        )
        self.assertEqual(implicit.image, explicit.image)
        header = pb.parse_android_header(implicit.image)
        self.assertEqual(header.cmdline, self.stock.header.cmdline)
        self.assertEqual(header.extra_cmdline, self.stock.header.extra_cmdline)
        self.assertEqual(
            bytes(implicit.image[64:576]), self.stock.header.cmdline
        )
        self.assertEqual(
            self.stock_cmdline_text(),
            b"bootopt=64S3,32N2,64N2 buildvariant=user",
        )

    def test_cmdline_append_round_trip_across_header_boundary(self) -> None:
        suffix = PSTORE_CMDLINE_SUFFIX + " " + "x" * 500
        dtb, result = self.build_with_suffix(suffix)
        expected = self.stock_cmdline_text() + b" " + suffix.encode("utf-8")
        self.assertGreater(len(expected), pb.CMDLINE_SIZE - 1)
        self.assertLessEqual(len(expected), pb.MAX_CMDLINE_TEXT)

        header = pb.parse_android_header(result.image)
        split = pb.CMDLINE_SIZE - 1
        self.assertEqual(header.cmdline[:split], expected[:split])
        self.assertEqual(header.cmdline[split:], b"\x00")
        self.assertEqual(
            header.extra_cmdline,
            (expected[split:] + b"\x00").ljust(pb.EXTRA_CMDLINE_SIZE, b"\x00"),
        )
        joined = self.effective_cmdline(result.image)
        self.assertEqual(joined, expected)
        self.assertIn(
            b"buildvariant=user console=ttyS0,921600n1 "
            b"pstore_blk.blkdev=",
            joined,
        )
        self.assertEqual(joined.count(b"pstore_blk.max_reason=5"), 1)

        output = self.directory / "cmdline-append.img"
        output.write_bytes(result.image)
        verified = pb.verify_image(
            str(output),
            self.stock,
            self.fixture.kernel,
            dtb,
            cmdline_append=suffix,
        )
        self.assertEqual(verified.kernel_size, result.kernel_size)

    def test_cmdline_append_exact_capacity_and_overflow(self) -> None:
        dtb = self.new_dtb()
        base = len(self.stock_cmdline_text())
        fitting = "a" * (pb.MAX_CMDLINE_TEXT - base - 1)
        result = pb.build_image(
            self.stock,
            self.fixture.kernel,
            dtb,
            cmdline_append=fitting,
        )
        header = pb.parse_android_header(result.image)
        self.assertEqual(len(self.effective_cmdline(result.image)),
                         pb.MAX_CMDLINE_TEXT)
        self.assertEqual(header.extra_cmdline[-1], 0)
        output = self.directory / "cmdline-fits.img"
        output.write_bytes(result.image)
        pb.verify_image(
            str(output),
            self.stock,
            self.fixture.kernel,
            dtb,
            cmdline_append=fitting,
        )

        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(
                self.stock,
                self.fixture.kernel,
                dtb,
                cmdline_append=fitting + "a",
            )
        self.assertIn("overflows", str(caught.exception))

    def test_cmdline_append_rejects_empty_and_nul_suffixes(self) -> None:
        dtb = self.new_dtb()
        for suffix in ("", "pstore_blk.max_reason=5\x00"):
            with self.subTest(suffix=suffix):
                with self.assertRaises(pb.PackError):
                    pb.build_image(
                        self.stock,
                        self.fixture.kernel,
                        dtb,
                        cmdline_append=suffix,
                    )

    def test_verify_cmdline_append_detects_missing_and_wrong_suffix(self) -> None:
        dtb, result = self.build_with_suffix(PSTORE_CMDLINE_SUFFIX)
        output = self.directory / "cmdline-append.img"
        output.write_bytes(result.image)

        with self.assertRaises(pb.PackError) as missing:
            pb.verify_image(str(output), self.stock, self.fixture.kernel, dtb)
        self.assertIn("cmdline", str(missing.exception))

        wrong = PSTORE_CMDLINE_SUFFIX.replace("max_reason=5", "max_reason=6")
        self.assertEqual(len(wrong), len(PSTORE_CMDLINE_SUFFIX))
        with self.assertRaises(pb.PackError) as mismatched:
            pb.verify_image(
                str(output),
                self.stock,
                self.fixture.kernel,
                dtb,
                cmdline_append=wrong,
            )
        self.assertIn("cmdline", str(mismatched.exception))

    def test_verify_rejects_cmdline_append_on_default_image(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        output = self.directory / "default-cmdline.img"
        output.write_bytes(result.image)
        with self.assertRaises(pb.PackError):
            pb.verify_image(
                str(output),
                self.stock,
                self.fixture.kernel,
                dtb,
                cmdline_append=PSTORE_CMDLINE_SUFFIX,
            )

    def test_ramdisk_replaces_stock_and_verifies(self) -> None:
        dtb = self.new_dtb()
        ramdisk = self.make_ramdisk()
        self.assertNotEqual(ramdisk, self.fixture.ramdisk)
        result = pb.build_image(
            self.stock, self.fixture.kernel, dtb, ramdisk=ramdisk
        )
        header = pb.parse_android_header(result.image)
        self.assertEqual(header.ramdisk_size, len(ramdisk))
        self.assertEqual(self.image_ramdisk(result.image), ramdisk)
        self.assertEqual(
            result.trailer_offset,
            result.ramdisk_offset + pb.align_up(len(ramdisk), pb.PAGE_SIZE),
        )
        self.assertFalse(any(result.image[result.trailer_offset:]))

        output = self.directory / "custom-ramdisk.img"
        output.write_bytes(result.image)
        verified = pb.verify_image(
            str(output),
            self.stock,
            self.fixture.kernel,
            dtb,
            ramdisk=ramdisk,
        )
        self.assertEqual(verified.kernel_size, result.kernel_size)

        with self.assertRaises(pb.PackError):
            pb.verify_image(str(output), self.stock, self.fixture.kernel, dtb)

    def test_ramdisk_equal_to_stock_builds_identically(self) -> None:
        dtb = self.new_dtb()
        implicit = pb.build_image(self.stock, self.fixture.kernel, dtb)
        explicit = pb.build_image(
            self.stock, self.fixture.kernel, dtb, ramdisk=self.fixture.ramdisk
        )
        self.assertEqual(implicit.image, explicit.image)

    def test_chosen_initrd_properties_come_from_header(self) -> None:
        dtb = self.new_dtb()
        ramdisk = self.make_ramdisk()
        result = pb.build_image(
            self.stock, self.fixture.kernel, dtb, ramdisk=ramdisk
        )
        header = pb.parse_android_header(result.image)
        chosen = self.chosen_properties(self.appended_dtb(result.image))
        start = struct.unpack(">Q", chosen[b"linux,initrd-start"])[0]
        end = struct.unpack(">Q", chosen[b"linux,initrd-end"])[0]
        self.assertEqual(start, header.ramdisk_addr)
        self.assertEqual(end - start, len(ramdisk))
        self.assertEqual(end, header.ramdisk_addr + header.ramdisk_size)
        self.assertEqual(len(chosen[b"linux,initrd-start"]), 8)
        self.assertEqual(len(chosen[b"linux,initrd-end"]), 8)

        out_dtbs = self.appended_dtbs(result.image)
        for index, blob in enumerate(out_dtbs):
            if index != pb.STOCK_DTB_INDEX:
                self.assertEqual(blob, self.fixture.dtbs[index])

    def test_dtb_with_matching_initrd_properties_is_unchanged(self) -> None:
        dtb = self.new_dtb()
        addr = self.stock.header.ramdisk_addr
        size = len(self.fixture.ramdisk)
        with_props = pb.set_chosen_initrd(dtb, addr, size, "test DTB")
        self.assertNotEqual(with_props, dtb)
        self.assertEqual(
            pb.set_chosen_initrd(with_props, addr, size, "test DTB"), with_props
        )
        implicit = pb.build_image(self.stock, self.fixture.kernel, dtb)
        explicit = pb.build_image(self.stock, self.fixture.kernel, with_props)
        self.assertEqual(implicit.image, explicit.image)

        larger = pb.set_chosen_initrd(with_props, addr, size + 0x10, "test DTB")
        self.assertNotEqual(larger, with_props)
        chosen = self.chosen_properties(larger)
        self.assertEqual(
            struct.unpack(">Q", chosen[b"linux,initrd-end"])[0],
            addr + size + 0x10,
        )

    def test_verify_rejects_wrong_initrd_end(self) -> None:
        dtb = self.new_dtb()
        ramdisk = self.make_ramdisk()
        result = pb.build_image(
            self.stock, self.fixture.kernel, dtb, ramdisk=ramdisk
        )
        out_dtb = self.appended_dtb(result.image)
        dtb_start = result.image.index(out_dtb)
        end = struct.pack(
            ">Q", self.stock.header.ramdisk_addr + len(ramdisk)
        )
        segment = result.image[dtb_start:dtb_start + len(out_dtb)]
        self.assertEqual(segment.count(end), 1)
        offset = dtb_start + segment.index(end)
        image = bytearray(result.image)
        image[offset:offset + len(end)] = struct.pack(
            ">Q", self.stock.header.ramdisk_addr + len(ramdisk) + 1
        )
        output = self.directory / "wrong-initrd-end.img"
        output.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError) as caught:
            pb.verify_image(
                str(output),
                self.stock,
                self.fixture.kernel,
                dtb,
                ramdisk=ramdisk,
            )
        self.assertIn("linux,initrd-end", str(caught.exception))

    def test_verify_rejects_missing_initrd_start(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        out_dtb = self.appended_dtb(result.image)
        dtb_start = result.image.index(out_dtb)
        segment = result.image[dtb_start:dtb_start + len(out_dtb)]
        name = b"linux,initrd-start\x00"
        self.assertEqual(segment.count(name), 1)
        offset = dtb_start + segment.index(name)
        image = bytearray(result.image)
        image[offset:offset + len(name)] = name[:-2] + b"X\x00"
        output = self.directory / "missing-initrd-start.img"
        output.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError) as caught:
            pb.verify_image(
                str(output), self.stock, self.fixture.kernel, dtb
            )
        self.assertIn("missing linux,initrd-start", str(caught.exception))

    def test_ramdisk_without_init_is_rejected(self) -> None:
        ramdisk = self.make_ramdisk(
            [("act", 0o040755, b""), ("bin/sh", 0o100755, b"\x7fELF")]
        )
        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(
                self.stock,
                self.fixture.kernel,
                self.new_dtb(),
                ramdisk=ramdisk,
            )
        self.assertIn("init", str(caught.exception))

    def test_ramdisk_init_must_be_executable_regular_file(self) -> None:
        cases = {
            "no-exec-bit": 0o100644,
            "directory": 0o040755,
        }
        for name, mode in cases.items():
            with self.subTest(name=name):
                ramdisk = self.make_ramdisk([("init", mode, b"\x7fELF")])
                with self.assertRaises(pb.PackError) as caught:
                    pb.build_image(
                        self.stock,
                        self.fixture.kernel,
                        self.new_dtb(),
                        ramdisk=ramdisk,
                    )
                self.assertIn("init", str(caught.exception))

    def test_ramdisk_not_gzip_is_rejected(self) -> None:
        ramdisk = make_cpio([("init", 0o100755, b"\x7fELF")])
        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(
                self.stock,
                self.fixture.kernel,
                self.new_dtb(),
                ramdisk=ramdisk,
            )
        self.assertIn("gzip", str(caught.exception))

    def test_verify_rejects_bad_ramdisk(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        output = self.directory / "default-ramdisk.img"
        output.write_bytes(result.image)
        bad = self.make_ramdisk([("act", 0o040755, b"")])
        with self.assertRaises(pb.PackError) as caught:
            pb.verify_image(
                str(output), self.stock, self.fixture.kernel, dtb, ramdisk=bad
            )
        self.assertIn("init", str(caught.exception))

    def test_default_image_keeps_stock_ramdisk_and_cpio(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        ramdisk = self.image_ramdisk(result.image)
        self.assertEqual(ramdisk, self.fixture.ramdisk)
        self.assertEqual(
            pb.parse_android_header(result.image).ramdisk_size,
            len(self.fixture.ramdisk),
        )
        archive = self.archive_of(ramdisk)
        self.assertEqual(pb.serialize_cpio(archive), self.fixture.ramdisk_cpio)
        for expected, entry in zip(self.fixture.ramdisk_entries, archive.entries):
            name, mode, data = expected
            self.assertEqual(entry.text_name, name)
            self.assertEqual(entry.mode, mode)
            self.assertEqual(entry.data, data)

    def test_verify_detects_ramdisk_tamper(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        image = bytearray(result.image)
        image[result.ramdisk_offset] ^= 0xFF
        output = self.directory / "tampered-ramdisk.img"
        output.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError):
            pb.verify_image(str(output), self.stock, self.fixture.kernel, dtb)

    def test_verify_detects_retained_trailer(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        image = bytearray(result.image)
        image[result.trailer_offset] = 0x30
        output = self.directory / "tampered-trailer.img"
        output.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError):
            pb.verify_image(str(output), self.stock, self.fixture.kernel, dtb)

    def test_verify_detects_changed_dtb(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        header = pb.parse_android_header(result.image)
        section = result.image[pb.PAGE_SIZE:pb.PAGE_SIZE + header.kernel_size]
        _image, gzip_size = pb.decompress_first_gzip(
            section[pb.MTK_HEADER_SIZE:], "test"
        )
        dtb_start = pb.PAGE_SIZE + pb.MTK_HEADER_SIZE + gzip_size
        image = bytearray(result.image)
        image[dtb_start] = 0
        output = self.directory / "tampered-dtb.img"
        output.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError):
            pb.verify_image(str(output), self.stock, self.fixture.kernel, dtb)

    def test_verify_rejects_wrong_kernel(self) -> None:
        dtb = self.new_dtb()
        result = pb.build_image(self.stock, self.fixture.kernel, dtb)
        output = self.directory / "kernel-mismatch.img"
        output.write_bytes(result.image)
        other = make_arm64_image(b"other-kernel")
        with self.assertRaises(pb.PackError):
            pb.verify_image(str(output), self.stock, other, dtb)

    def test_bad_kernel_magic_is_rejected(self) -> None:
        kernel = bytearray(self.fixture.kernel)
        kernel[0x38:0x3C] = b"XXXX"
        with self.assertRaises(pb.PackError):
            pb.build_image(self.stock, bytes(kernel), self.new_dtb())

    def test_oversized_kernel_is_rejected(self) -> None:
        kernel = bytearray(os.urandom(pb.IMAGE_SIZE))
        kernel[0x38:0x3C] = b"ARMd"
        with self.assertRaises(pb.PackError):
            pb.build_image(self.stock, bytes(kernel), self.new_dtb())

    def test_bad_new_dtb_is_rejected(self) -> None:
        dtb = self.new_dtb()
        with self.assertRaises(pb.PackError):
            pb.build_image(self.stock, self.fixture.kernel, dtb[:-8])

    def test_wrong_compatible_is_rejected(self) -> None:
        dtb = make_fdt("Other Board", ["amzn,other-board"])
        with self.assertRaises(pb.PackError):
            pb.build_image(self.stock, self.fixture.kernel, dtb)

    def test_dtb_first_compatible_must_name_a_lidar_board(self) -> None:
        dtb = make_fdt(
            "Lidar with another lead", ["amzn,other-board", pb.LIDAR_PVT_COMPATIBLE]
        )
        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(self.stock, self.fixture.kernel, dtb)
        self.assertIn("amzn,lidar-", str(caught.exception))

    def test_oversized_dtb_is_rejected(self) -> None:
        dtb = make_fdt(
            "a" * pb.MAX_DTB_SIZE, [pb.LIDAR_PVT_COMPATIBLE, "amzn,lidar"]
        )
        self.assertGreater(len(dtb), pb.MAX_DTB_SIZE)
        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(self.stock, self.fixture.kernel, dtb)
        self.assertIn(f"{pb.MAX_DTB_SIZE:#x}", str(caught.exception))

    def test_missing_bootopt_prefix_is_rejected(self) -> None:
        cmdline = b"buildvariant=user\x00"

        def mutate(image: bytearray) -> None:
            image[pb.CMDLINE_OFFSET:pb.CMDLINE_OFFSET + pb.CMDLINE_SIZE] = (
                b"\x00" * pb.CMDLINE_SIZE
            )
            image[pb.CMDLINE_OFFSET:pb.CMDLINE_OFFSET + len(cmdline)] = cmdline

        path = self.fixture.write_variant("no-bootopt.img", mutate)
        stock = pb.parse_stock(str(path), self.fixture.pvt_sha256)

        with self.assertRaises(pb.PackError) as caught:
            pb.build_image(stock, self.fixture.kernel, self.new_dtb())
        self.assertIn("bootopt", str(caught.exception))

        output = self.directory / "no-bootopt-output.img"
        output.write_bytes(path.read_bytes())
        with self.assertRaises(pb.PackError) as caught:
            pb.verify_image(
                str(output),
                stock,
                self.fixture.kernel,
                self.fixture.dtbs[pb.STOCK_DTB_INDEX],
            )
        self.assertIn("bootopt", str(caught.exception))

    def test_bootopt_prefix_survives_cmdline_append(self) -> None:
        dtb, result = self.build_with_suffix(PSTORE_CMDLINE_SUFFIX)
        self.assertTrue(
            self.effective_cmdline(result.image).startswith(pb.BOOTOPT_PREFIX)
        )
        output = self.directory / "bootopt-append.img"
        output.write_bytes(result.image)
        pb.verify_image(
            str(output),
            self.stock,
            self.fixture.kernel,
            dtb,
            cmdline_append=PSTORE_CMDLINE_SUFFIX,
        )

    def test_wrong_pvt_hash_is_rejected(self) -> None:
        with self.assertRaises(pb.PackError):
            pb.parse_stock(str(self.fixture.stock_path), "00" * 32)

    def test_stock_mtk_filler_starts_at_0x28(self) -> None:
        header = bytearray(pb.MTK_HEADER_SIZE)
        struct.pack_into("<II", header, 0, pb.MTK_MAGIC, 1)
        header[8:16] = pb.MTK_NAME
        header[0x28:] = b"\xff" * (pb.MTK_HEADER_SIZE - 0x28)
        pb.validate_mtk_header(bytes(header), pb.MTK_HEADER_SIZE + 1)

    def test_bad_stock_headers_are_rejected(self) -> None:
        cases = {
            "bad-magic": lambda image: image.__setitem__(0, 0),
            "bad-page": lambda image: struct.pack_into("<I", image, 0x24, 4096),
            "bad-second-size": lambda image: struct.pack_into("<I", image, 0x18, 1),
            "bad-header-version": lambda image: struct.pack_into("<I", image, 0x28, 1),
            "bad-mtk-magic": lambda image: image.__setitem__(pb.PAGE_SIZE, 0),
            "bad-kernel-gzip": lambda image: image.__setitem__(
                pb.PAGE_SIZE + pb.MTK_HEADER_SIZE, 0
            ),
            "bad-ramdisk-gzip": lambda image: image.__setitem__(
                self.fixture.ramdisk_offset, 0
            ),
            "bad-android-id": lambda image: image.__setitem__(
                slice(576, 596), b"\x00" * 20
            ),
            "bad-dtb-magic": lambda image: image.__setitem__(
                self.fixture.first_dtb_offset, 0
            ),
            "bad-trailer": lambda image: image.__setitem__(
                self.fixture.trailer_offset + len(self.fixture.certificate) + 1, 1
            ),
            "bad-kernel-size": lambda image: struct.pack_into(
                "<I", image, 8, pb.IMAGE_SIZE
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                path = self.fixture.write_variant(f"{name}.img", mutate)
                with self.assertRaises(pb.PackError):
                    pb.parse_stock(str(path), self.fixture.pvt_sha256)

    def test_truncated_stock_is_rejected(self) -> None:
        path = self.directory / "truncated.img"
        path.write_bytes(self.fixture.image[:-1])
        with self.assertRaises(pb.PackError):
            pb.parse_stock(str(path), self.fixture.pvt_sha256)

    def test_nonzero_padding_is_rejected(self) -> None:
        image = bytearray(self.fixture.image)
        image[self.fixture.ramdisk_offset + len(self.fixture.ramdisk)] = 1
        path = self.directory / "bad-padding.img"
        path.write_bytes(bytes(image))
        with self.assertRaises(pb.PackError):
            pb.parse_stock(str(path), self.fixture.pvt_sha256)


if __name__ == "__main__":
    unittest.main()
