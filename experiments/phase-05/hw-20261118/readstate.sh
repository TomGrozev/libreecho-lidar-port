#!/bin/bash
# Read-only device state capture requested by the OTA confirm diagnosis.
out=${1:?usage: readstate.sh <file>}
timeout 120 adb wait-for-device || { echo "no device" > "$out"; exit 1; }
sleep 20
timeout 60 adb shell 'cat /proc/uptime; cat /proc/cmdline; echo ---; libreecho-update status; echo ---; cat /data/libreecho/update/features-status 2>&1; echo ---; cat /data/libreecho/update/restart-record 2>&1; echo ---; ls -la /data/libreecho/update /data/libreecho/generations; echo ---; df -h /data; echo ---; cat /tmp/ota-confirm.log 2>&1; echo ---; ls -l /run/libreecho /var/run/libreecho-*.pid 2>&1; echo ---; grep -E "features/.*/root|squash" /proc/self/mountinfo; echo ---; dmesg | tail -40; echo "--- init.log"; tail -60 /tmp/init.log; echo "--- init logs"; for f in /tmp/libreecho-*.init.log; do echo "## $f"; cat $f; done' > "$out" 2>&1
