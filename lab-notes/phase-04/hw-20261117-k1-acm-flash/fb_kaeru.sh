#!/usr/bin/env bash
# fastboot wrapper for this run: fb_kaeru.sh <timeout> <args...>
T=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
exec timeout "$1" "$T/bin/fastboot" "${@:2}"
