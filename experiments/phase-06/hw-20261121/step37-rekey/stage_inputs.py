#!/usr/bin/env python3
"""Rebuild artifacts/phase-05 input staging from the recorded locks.

Downloads the armhf cross-toolchain debs (lock has direct URLs), the mDNS
package debs (ports.ubuntu.com; pool path resolved from the published Packages
indexes), the pinned source archives, and the AOSP system/core checkout.
Every file is hash-checked against its lock before it is kept.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[4]
ART = ROOT / "artifacts/phase-05"
TC = ART / "toolchains"
SRC = TC / "sources"
ARCH = TC / "armhf-archives"
MDNS = ART / "components/mdns-packages"
PORTS = "https://ports.ubuntu.com/ubuntu-ports"


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: pathlib.Path, expected: str | None, label: str) -> None:
    if dest.exists() and (expected is None or sha256(dest) == expected):
        print(f"have {label}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + f".part.{os.getpid()}")
    print(f"GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "libreecho-rebuild/1"})
    with urllib.request.urlopen(req, timeout=300) as r, partial.open("wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    actual = sha256(partial)
    if expected is not None and actual != expected:
        partial.unlink()
        raise SystemExit(f"ERROR hash mismatch {label}: {actual} != {expected}")
    os.replace(partial, dest)
    print(f"ok   {label} {actual}")


def armhf() -> None:
    lock = json.loads((ROOT / "repos/LibreEcho/build/inputs/armhf-cross-toolchain.lock.json").read_text())
    for rec in lock["archives"]:
        fetch(rec["url"], ARCH / rec["filename"], rec["sha256"], rec["filename"])


def mdns_index() -> dict[str, str]:
    found: dict[str, str] = {}
    for suite in ("noble", "noble-updates"):
        for comp in ("main", "universe", "multiverse", "restricted"):
            url = f"{PORTS}/dists/{suite}/{comp}/binary-armhf/Packages.xz"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "libreecho-rebuild/1"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    data = lzma.decompress(r.read())
            except Exception as exc:  # noqa: BLE001 - index may be absent
                print(f"skip index {url}: {exc}")
                continue
            cur = {}
            for line in data.decode("utf-8", "replace").splitlines() + [""]:
                if not line:
                    if "Filename" in cur and "Package" in cur:
                        found.setdefault((cur["Package"], cur.get("Version", "")), cur["Filename"])
                        found.setdefault(cur["Package"], cur["Filename"])
                    cur = {}
                elif line[0] not in " \t" and ": " in line:
                    k, v = line.split(": ", 1)
                    cur[k] = v
    return found


def mdns() -> None:
    lock = json.loads((ROOT / "repos/LibreEcho/build/inputs/mdns-packages.lock.json").read_text())
    index = mdns_index()
    for rec in lock["packages"]:
        fn = rec["file"]
        # url-encoded epoch/name chars (%3a) map back to ':' in pool paths; the
        # Packages index records the real pool name.
        key = (rec["package"], rec["version"])
        dest = MDNS / fn
        # A pinned version can leave the live pool (libapparmor1 did); when the
        # verified bytes are already on disk, no index entry is needed.
        if dest.exists() and sha256(dest) == rec["sha256"]:
            print(f"have {fn}")
            continue
        pool = index.get(key)
        if pool is not None:
            fetch(f"{PORTS}/{pool}", dest, rec["sha256"], fn)
            continue
        # Superseded pins leave the ports pool but stay on Launchpad, whose
        # +files names carry no epoch.
        lp_name = re.sub(r"_\d+%3a", "_", fn)
        fetch(f"https://launchpad.net/ubuntu/+archive/primary/+files/{lp_name}", dest, rec["sha256"], fn)


def archives() -> None:
    items = [
        ("https://musl.libc.org/releases/musl-1.2.5.tar.gz",
         "a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4"),
        ("https://busybox.net/downloads/busybox-1.37.0.tar.bz2",
         "3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4"),
        ("https://archive.ubuntu.com/ubuntu/pool/main/libs/libsodium/libsodium_1.0.18.orig.tar.gz",
         "d59323c6b712a1519a5daf710b68f5e7fde57040845ffec53850911f10a5d4f4"),
        ("https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2",
         "a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6"),
        ("https://downloads.xiph.org/releases/ogg/libogg-1.3.5.tar.gz",
         "0eb4b4b9420a0f51db142ba3f9c64b333f826532dc0f48c6410ae51f4799b664"),
        ("https://downloads.xiph.org/releases/opus/opus-1.4.tar.gz",
         "c9b32b4253be5ae63d1ff16eea06b94b5f0f2951b7a02aceef58e3a3ce49c51f"),
        ("https://github.com/xiph/opusfile/archive/refs/tags/v0.12.tar.gz",
         "a20a1dff1cdf0719d1e995112915e9966debf1470ee26bb31b2f510ccf00ef40"),
    ]
    for url, digest in items:
        name = url.rsplit("/", 1)[-1]
        if "opusfile" in url:
            name = "opusfile-0.12.tar.gz"
        elif "libsodium" in url:
            # Product's fetch-public-deps.py:537 stores the Debian orig under this name.
            name = "libsodium-1.0.18.tar.gz"
        dest = SRC / "opus" / name if "xiph" in url else SRC / name
        fetch(url, dest, digest, name)


def aosp() -> None:
    dest = SRC / "aosp-system-core"
    commit = "4f247d753a8865cd16292ff0b720b72c28049786"
    if dest.exists():
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        if head == commit:
            print("have aosp-system-core")
            return
    subprocess.run(["rm", "-rf", str(dest)], check=True)
    subprocess.run(["git", "clone", "--quiet", "--filter=blob:none",
                    "https://android.googlesource.com/platform/system/core", str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", commit], check=True)
    print("ok   aosp-system-core", commit)


def main() -> None:
    for d in (ARCH, MDNS, SRC, SRC / "opus"):
        d.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1:] or ["archives", "aosp", "armhf", "mdns"]
    for step in which:
        print(f"== {step}")
        globals()[step]()


if __name__ == "__main__":
    main()
