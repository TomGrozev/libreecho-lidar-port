#!/usr/bin/env bash
# Reboot the Lidar from fastboot, then log every change in the Lidar-related
# USB IDs and ACM ttys. Usage: observe_usb.sh <seconds> <logfile>
set -u
dur=$1
log=$2
tools=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
start=$(date +%s.%N)
stamp() { printf '%8.3f %s\n' "$(echo "$(date +%s.%N) - $start" | bc)" "$*" | tee -a "$log"; }
stamp "reboot: $(LD_LIBRARY_PATH=$tools/lib "$tools/bin/fastboot" reboot 2>&1 | tr '\n' ' ')"
prev=""
end=$(echo "$start + $dur" | bc)
while [ "$(echo "$(date +%s.%N) < $end" | bc)" = 1 ]; do
    cur="usb=[$(lsusb | grep -E '0bb4:|0e8d:|1d6b:0104' | sed 's/^Bus ... Device ...: ID //' | tr '\n' ';')] tty=[$(ls /dev/ttyACM* 2>/dev/null | tr '\n' ' ')]"
    if [ "$cur" != "$prev" ]; then
        stamp "$cur"
        prev=$cur
    fi
    sleep 0.25
done
stamp end
