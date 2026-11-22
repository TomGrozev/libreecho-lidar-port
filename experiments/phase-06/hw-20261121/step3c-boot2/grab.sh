#!/usr/bin/env bash
# Boot slot A from Kaeru fastboot, then grab state with one short adb command per read.
# The first 6.18 boot lost adb after a long multi-command capture, so nothing here is batched.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
out=$root/experiments/phase-06/hw-20261121/step3c-boot2
mkdir -p "$out"
t() { echo "$(date +%T) $*" >> "$out/events.log"; }

fastboot reboot > "$out/reboot.log" 2>&1
t "fastboot reboot rc=$?"
found=0
for _ in $(seq 1 120); do
  if timeout 5 adb get-state 2>/dev/null | grep -q '^device$'; then found=1; break; fi
  sleep 1
done
t "adb found=$found"
[ "$found" = 1 ] || exit 1

timeout 20 adb shell 'id; uname -r; cat /proc/uptime' > "$out/id.txt" 2>&1;      t "id rc=$?"
timeout 20 adb shell 'cat /proc/cmdline' > "$out/cmdline.txt" 2>&1;              t "cmdline rc=$?"
sleep 25
timeout 60 adb shell 'dmesg' > "$out/dmesg.txt" 2>&1;                            t "dmesg rc=$? lines=$(wc -l < "$out/dmesg.txt")"
timeout 20 adb shell 'cat /proc/partitions' > "$out/partitions.txt" 2>&1;        t "partitions rc=$?"
timeout 20 adb shell 'ls -l /sys/class/mmc_host; ls /sys/bus/mmc/devices; ls -l /dev/mmcblk* /dev/mmcblk0p*' > "$out/mmc.txt" 2>&1; t "mmc rc=$?"
timeout 20 adb shell 'cat /sys/kernel/debug/devices_deferred 2>&1; echo ---; ls /sys/fs/pstore; echo ---; ls /sys/bus/sdio/devices 2>&1; ls /sys/class/net 2>&1; ls /sys/class/bluetooth 2>&1' > "$out/deferred.txt" 2>&1; t "deferred rc=$?"
timeout 20 adb shell 'cat /proc/mounts' > "$out/mounts.txt" 2>&1;                  t "mounts rc=$?"
timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl status a' > "$out/bootctl.txt" 2>&1; t "bootctl rc=$?"
timeout 20 adb shell 'ls -la /run/libreecho; cat /data/libreecho/update/features-status 2>&1' > "$out/runtime.txt" 2>&1; t "runtime rc=$?"
t done
