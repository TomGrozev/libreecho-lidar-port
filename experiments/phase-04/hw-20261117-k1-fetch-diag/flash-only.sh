#!/usr/bin/env bash
# Kaeru: flash boot_a and read it back, without the ramoops fetch.
# Used after a cold boot, where the ramoops fetch can fail and leave the USB link stuck.
#   flash-only.sh <image> <tag>
set -u
D=experiments/phase-04/hw-20261117-k1-fetch-diag
O=dumps/20261117-lidar-k1-fetch-diag
IMG=${1:?image}
TAG=${2:?tag}
T=experiments/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
fb() { timeout "$1" "$T/bin/fastboot" "${@:2}" 2>&1; }
mkdir -p "$O"
fb 5 getvar product | tee "$D/getvar.log"
case "$(cat "$D/getvar.log")" in *LIDAR*) ;; *) echo "not in Kaeru"; exit 1;; esac
sha256sum "$IMG" | tee "$D/flash-$TAG.log"
fb 90 flash boot_a "$IMG" | tee -a "$D/flash-$TAG.log"
fb 10 oem fetch-enable | tee "$D/fetch-$TAG.log"
fb 90 fetch boot_a "$O/boot_a-readback-$TAG.bin" | tee -a "$D/fetch-$TAG.log"
sha256sum "$O/boot_a-readback-$TAG.bin" | tee -a "$D/fetch-$TAG.log"
