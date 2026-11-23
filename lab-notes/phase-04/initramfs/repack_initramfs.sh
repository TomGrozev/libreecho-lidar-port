#!/usr/bin/env bash
# Repack the test initramfs with the current ./init and the busybox binary
# taken from an existing archive, without rebuilding the musl/LLVM toolchain.
# Same staging, mtimes and gen_init_cpio/gzip flags as build_initramfs.sh.
#   [LIDAR_INIT=<init>] repack_initramfs.sh <old.cpio.gz> <out.cpio.gz>
set -euo pipefail
OLD=$(realpath "${1:?old archive}")
OUT=$(realpath -m "${2:?output archive}")
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
WORK=$(mktemp -d /tmp/lidar-initramfs-repack.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT

mkdir -p "$WORK/x" "$WORK/root/bin" "$WORK/root/dev"
# Device nodes fail to extract as non-root; only bin/busybox is needed.
( cd "$WORK/x" && zcat "$OLD" | cpio -idm --quiet bin/busybox )
cc -O2 -o "$WORK/gen_init_cpio" "$ROOT/forks/LibreEcho-Linux/usr/gen_init_cpio.c"
install -m 0755 "$WORK/x/bin/busybox" "$WORK/root/bin/busybox"
install -m 0755 "${LIDAR_INIT:-$HERE/init}" "$WORK/root/init"
touch -d @0 "$WORK/root/init" "$WORK/root/bin/busybox"
( cd "$WORK/root" && "$WORK/gen_init_cpio" -t 0 "$HERE/initramfs.list" ) > "$WORK/initramfs.cpio"
gzip -n -9 -c "$WORK/initramfs.cpio" > "$OUT"
sha256sum "$OUT"
