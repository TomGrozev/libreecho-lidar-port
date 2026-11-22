#!/usr/bin/env bash
# Read-only: copy system_a (p13, Fire OS firmware source) from the running LibreEcho image
# over adb to the Phase 6 dump directory. Run from the workspace root.
set -eu
out=dumps/20261121-lidar-phase6
mkdir -p "$out"
adb=experiments/phase-06/adb.sh
"$adb" 20 shell 'cat /sys/class/block/mmcblk0p13/uevent; cat /sys/class/block/mmcblk0p13/size' > "$out/system_a.uevent"
"$adb" 600 shell 'sha256sum /dev/mmcblk0p13' > "$out/system_a.device-sha256"
"$adb" 1800 pull /dev/mmcblk0p13 "$out/system_a.img"
sha256sum "$out/system_a.img" > "$out/system_a.img.sha256"
cat "$out/system_a.uevent" "$out/system_a.device-sha256" "$out/system_a.img.sha256"
ls -l "$out/system_a.img"
