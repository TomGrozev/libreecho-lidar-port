#!/bin/sh
# Reboot from fastboot, then snapshot device state every 20 s for 5 minutes.
out=step3b
mkdir -p "$out"
fastboot reboot > "$out/reboot.log" 2>&1
i=0
while [ $i -lt 16 ]; do
  sleep 20
  i=$((i + 1))
  t=$(date -u +%T)
  if timeout 15 adb shell 'cat /proc/uptime /proc/loadavg; free; grep -E " /data " /proc/mounts; dmesg | tail -n 25; ps' > "$out/snap-$i.txt" 2>&1; then
    echo "$t snap $i ok"
  else
    echo "$t snap $i FAILED rc=$?"
  fi
done
timeout 20 adb shell dmesg > "$out/dmesg-final.txt" 2>&1
echo final rc=$?
