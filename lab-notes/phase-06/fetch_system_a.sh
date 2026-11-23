#!/usr/bin/env bash
# Read-only: identify Kaeru fastboot, then fetch system_a (Fire OS firmware source) to the
# Phase 6 dump directory. Run from the workspace root.
set -u
fb=private/lab/phase-04/fb.sh
out=private/dumps/20261121-lidar-phase6
mkdir -p "$out"
"$fb" 10 getvar product
"$fb" 10 getvar kaeru-version
"$fb" 30 oem fetch-enable
"$fb" 10 getvar max-fetch-size
"$fb" 10 getvar partition-size:system_a
[ "${1:-}" = "--fetch" ] || exit 0
"$fb" 3500 fetch system_a "$out/system_a.img"
sha256sum "$out/system_a.img" > "$out/system_a.img.sha256"
cat "$out/system_a.img.sha256"
