#!/usr/bin/env bash
# adb from the saved android-tools build: adb.sh <timeout-s> <args...>
tools=experiments/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$tools/lib
exec timeout "$1" "$tools/bin/adb" "${@:2}"
