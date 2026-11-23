#!/usr/bin/env bash
# fastboot from the saved android-tools build: fb.sh <timeout-s> <args...>
here=$(cd "$(dirname "$0")" && pwd)
TOOLS=$here/../phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$TOOLS/lib
exec timeout "$1" "$TOOLS/bin/fastboot" "${@:2}"
