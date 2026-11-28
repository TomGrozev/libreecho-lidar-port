#!/usr/bin/env bash
# Kaeru: fetch ramoops left by the previous boot, flash boot_a, read it back.
#   flash.sh <image> <tag>   (tag names the dump files)
set -u
D=private/lab/phase-04/hw-20261117-k1-fetch-diag
O=private/dumps/20261117-lidar-k1-fetch-diag
IMG=${1:?image}
TAG=${2:?tag}
T=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
fb() { timeout "$1" "$T/bin/fastboot" "${@:2}" 2>&1; }
mkdir -p "$O"
fb 5 getvar product | tee "$D/getvar.log"
case "$(cat "$D/getvar.log")" in *LIDAR*) ;; *) echo "not in Kaeru"; exit 1;; esac
fb 10 oem fetch-enable | tee "$D/fetch-$TAG.log"
fb 30 fetch ramoops "$O/ramoops-before-$TAG.bin" >> "$D/fetch-$TAG.log"
sha256sum "$IMG" | tee "$D/flash-$TAG.log"
fb 60 flash boot_a "$IMG" | tee -a "$D/flash-$TAG.log"
fb 60 fetch boot_a "$O/boot_a-readback-$TAG.bin" >> "$D/fetch-$TAG.log"
sha256sum "$O/ramoops-before-$TAG.bin" "$O/boot_a-readback-$TAG.bin" | tee -a "$D/fetch-$TAG.log"
