#!/usr/bin/env bash
# Kaeru: reboot into the normal boot path (boot_a) without flashing anything.
set -u
D=private/lab/phase-04/hw-20261117-k1-fetch-diag
T=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
fb() { timeout "$1" "$T/bin/fastboot" "${@:2}" 2>&1; }
fb 5 getvar product | tee "$D/getvar.log"
case "$(cat "$D/getvar.log")" in *LIDAR*) ;; *) echo "not in Kaeru"; exit 1;; esac
fb 10 reboot
