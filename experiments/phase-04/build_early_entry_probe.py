#!/usr/bin/env python3
"""Build and verify the minimal ARM64 LK-entry probe.

Assembles experiments/phase-04/early_entry.S with the aarch64 target, copies
its single code section to a raw arm64 Image, asserts the Image header and
instruction layout, then packs it with the current stock image and the stock
PVT DTB via experiments/phase-04/pack_boot.py.  The real pack_boot.py --verify
path is run afterwards.

Only standard-library Python and the host LLVM/clang tools are used.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / "early_entry.S"
STOCK = ROOT / "dumps/20261110-lidar-readback/boot_a.bin"
OUTPUT = ROOT / "artifacts/phase-04/boot-lidar-early-entry-probe.img"
PACK_BOOT = HERE / "pack_boot.py"

LLVM_BIN = Path("/tmp/lidar-arm64-tools/root/usr/bin")
LLVM_LIB = Path("/tmp/lidar-arm64-tools/root/usr/lib")

IMAGE_MAGIC = 0x644D5241  # "ARM\x64"
CODE_OFFSET = 0x40
EXPECTED_WORDS = (
    0xD5034FDF,  # msr daifset, #0xf
    0x528E0001,  # movz w1, #0x7000
    0x72A20001,  # movk w1, #0x1000, lsl #16
    0xB9400022,  # ldr w2, [x1]
    0x121F7842,  # and w2, w2, #0xfffffffe  (clear WDT_MODE_EN)
    0x52A44003,  # movz w3, #0x2200, lsl #16 (WDT_MODE_KEY)
    0x2A030042,  # orr w2, w2, w3
    0xB9000022,  # str w2, [x1]
    0x14000000,  # b .
)


def environment() -> dict[str, str]:
    env = os.environ.copy()
    roots = [str(LLVM_BIN), env.get("PATH", ""), "/usr/sbin"]
    env["PATH"] = ":".join(part for part in roots if part)
    libs = [str(LLVM_LIB), env.get("LD_LIBRARY_PATH", "")]
    env["LD_LIBRARY_PATH"] = ":".join(part for part in libs if part)
    return env


def find_tool(name: str, env: dict[str, str]) -> str:
    path = shutil.which(name, path=env["PATH"])
    if path is None:
        raise SystemExit(f"missing tool: {name}")
    return path


def run(command: list[str], env: dict[str, str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout if capture else ""


def branch_target(word: int, pc: int) -> int:
    if word & 0xFC000000 != 0x14000000:
        raise AssertionError(f"not a B instruction: {word:#010x}")
    immediate = word & 0x03FFFFFF
    if immediate & (1 << 25):
        immediate -= 1 << 26
    return pc + 4 * immediate


def check_image(image: bytes) -> None:
    if len(image) != 0x64:
        raise AssertionError(f"unexpected Image size: {len(image)}")
    code0, code1 = struct.unpack_from("<II", image, 0)
    text_offset, image_size, flags = struct.unpack_from("<QQQ", image, 8)
    reserved = struct.unpack_from("<QQQ", image, 0x20)
    magic = struct.unpack_from("<I", image, 0x38)[0]
    pe_offset = struct.unpack_from("<I", image, 0x3C)[0]

    if code0 != 0xD503201F:
        raise AssertionError(f"code0 is not the non-EFI NOP: {code0:#010x}")
    if branch_target(code1, 4) != CODE_OFFSET:
        raise AssertionError("code1 does not branch to the entry code")
    if (text_offset, image_size, flags) != (0, len(image), 0xA):
        raise AssertionError(
            f"bad header fields: {text_offset=:#x} {image_size=:#x} {flags=:#x}"
        )
    if reserved != (0, 0, 0):
        raise AssertionError(f"reserved header words are set: {reserved}")
    if magic != IMAGE_MAGIC:
        raise AssertionError(f"bad ARM64 magic: {magic:#010x}")
    if pe_offset != 0:
        raise AssertionError(f"unexpected PE header offset: {pe_offset:#x}")

    words = struct.unpack_from("<9I", image, CODE_OFFSET)
    if words != EXPECTED_WORDS:
        raise AssertionError(
            "entry instructions differ:\n"
            f"  expected {[hex(word) for word in EXPECTED_WORDS]}\n"
            f"  actual   {[hex(word) for word in words]}"
        )


def extract_stock_pvt(path: Path) -> bytes:
    sys.path.insert(0, str(HERE))
    import pack_boot

    stock = pack_boot.parse_stock(str(STOCK), pack_boot.STOCK_PVT_SHA256)
    pvt = stock.dtbs[pack_boot.STOCK_DTB_INDEX]
    digest = hashlib.sha256(pvt).hexdigest()
    if digest != pack_boot.STOCK_PVT_SHA256:
        raise AssertionError(f"stock PVT digest changed: {digest}")
    path.write_bytes(pvt)
    return pvt


def pack(kernel: Path, dtb: Path, output: Path, env: dict[str, str]) -> str:
    return run(
        [
            sys.executable,
            str(PACK_BOOT),
            "--stock",
            str(STOCK),
            "--kernel",
            str(kernel),
            "--dtb",
            str(dtb),
            "--output",
            str(output),
        ],
        env,
        capture=True,
    )


def verify(kernel: Path, dtb: Path, image: Path, env: dict[str, str]) -> str:
    return run(
        [
            sys.executable,
            str(PACK_BOOT),
            "--verify",
            str(image),
            "--stock",
            str(STOCK),
            "--kernel",
            str(kernel),
            "--dtb",
            str(dtb),
        ],
        env,
        capture=True,
    )


def main() -> int:
    env = environment()
    clang = find_tool("clang", env)
    objcopy = find_tool("llvm-objcopy", env)
    objdump = find_tool("llvm-objdump", env)
    readelf = find_tool("llvm-readelf", env)

    with tempfile.TemporaryDirectory(prefix="early-entry-probe.") as tmp:
        tmpdir = Path(tmp)
        obj = tmpdir / "early_entry.o"
        image_path = tmpdir / "Image"
        dtb = tmpdir / "stock-pvt.dtb"
        first = tmpdir / "first.img"
        second = tmpdir / "second.img"

        run([clang, "-target", "aarch64-linux-gnu", "-c", str(SOURCE), "-o", str(obj)], env)
        relocations = run([readelf, "-r", str(obj)], env, capture=True)
        if "no relocations" not in relocations:
            raise AssertionError(f"assembled object has relocations:\n{relocations}")
        run(
            [objcopy, "-O", "binary", "--only-section=.text.early_entry", str(obj), str(image_path)],
            env,
        )

        image = image_path.read_bytes()
        check_image(image)
        extract_stock_pvt(dtb)

        pack(image_path, dtb, first, env)
        pack(image_path, dtb, second, env)
        if first.read_bytes() != second.read_bytes():
            raise AssertionError("packing is not deterministic on this host")

        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(first, OUTPUT)
        verify_out = verify(image_path, dtb, OUTPUT, env)
        if "verify: OK" not in verify_out:
            raise AssertionError(f"pack_boot --verify did not report OK:\n{verify_out}")

        disassembly = run(
            [objdump, "-d", "--no-show-raw-insn", str(obj)], env, capture=True
        )

    digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    print(f"source: {SOURCE}")
    print(f"image:  {OUTPUT}")
    print(f"sha256: {digest}")
    print(f"kernel sha256: {hashlib.sha256(image).hexdigest()}")
    print("disassembly:")
    print(disassembly, end="")
    print(verify_out, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
