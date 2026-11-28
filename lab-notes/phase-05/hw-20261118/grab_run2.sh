#!/bin/bash
# Read-only capture of the OTA confirm failure state on the next slot B boot.
out=${1:?usage: grab_run2.sh <file>}
timeout 180 adb wait-for-device || { echo "no device" > "$out"; exit 1; }
sleep 60
timeout 40 adb shell 'cat /proc/uptime; tr " " "\n" </proc/cmdline | grep -E "slot_suffix|lab="; ls -l /etc/libreecho/; ls -la /data/libreecho/update; for f in /data/libreecho/update/failure-15*.log /data/libreecho/update/ota.log; do echo "## $f"; cat $f; done; echo "## init.log"; cat /tmp/init.log; echo "## tmp"; ls /tmp /run/libreecho' > "$out" 2>&1
