#!/usr/bin/env bash
# Wait for a Lidar U-Boot fastboot device, RAM-boot the pstore U-Boot, and
# drain `pstore display` (all ramoops zones) into <out>.
set -u
OUT=${1:?usage: pstore_readback.sh <out.raw>}
TOOLS=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$TOOLS/lib
fb() { timeout "$1" "$TOOLS/bin/fastboot" "${@:2}"; }

for i in $(seq 1 240); do lsusb -d 0bb4:0c01 >/dev/null && break; sleep 1; done
echo "fastboot seen $(date +%T)"
sleep 2
fb 30 boot private/artifacts/phase-04/uboot/u-boot-stage2-pstore.img 2>&1
for i in $(seq 1 60); do sleep 1; fb 3 getvar version >/dev/null 2>&1 && break; done
echo "pstore U-Boot up after ${i}s"
while fb 5 oem console >/dev/null 2>&1; do :; done
fb 20 oem 'run:run lidar_pstore' 2>&1
fb 20 oem 'run:pstore display' 2>&1
: > "$OUT"
for i in $(seq 1 600); do
  out=$(fb 5 oem console 2>&1); echo "$out" >> "$OUT"
  case "$out" in *"Empty console"*|*FAILED*) break;; esac
done
echo "lines: $(wc -l < "$OUT")"
