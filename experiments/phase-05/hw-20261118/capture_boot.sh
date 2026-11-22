#!/bin/sh
# Reboot from Kaeru fastboot, then stream the kernel log (/dev/kmsg, with kernel
# timestamps) and a 1 Hz sampler over two long-lived adb shells, each line stamped
# with host time. A hang shows as the moment both streams stop. Nothing is written
# on the device.
out=${1:?usage: capture_boot.sh <outdir> [limit_s]}
limit=${2:-600}
mkdir -p "$out"
stamp() { /usr/sbin/gawk '{ print strftime("%H:%M:%S"), $0; fflush() }'; }

fastboot reboot > "$out/reboot.log" 2>&1
timeout 90 adb wait-for-device || { echo "adb never appeared"; exit 1; }
echo "adb up $(date +%T)"

adb shell cat /dev/kmsg 2>&1 | stamp > "$out/kmsg.log" &
adb shell 'i=0; while :; do
  echo "== up $(cat /proc/uptime) load $(cat /proc/loadavg)"
  grep -E "bark|wdt|musb|mmc|i2c" /proc/interrupts
  if [ $((i % 10)) -eq 0 ]; then top -b -n 1 | head -n 15; fi
  i=$((i + 1)); sleep 1
done' 2>&1 | stamp > "$out/sampler.log" &

end=$(( $(date +%s) + limit ))
n=0
while [ "$(date +%s)" -lt "$end" ]; do
  sleep 5
  n=$((n + 1))
  if [ $((n % 12)) -eq 0 ]; then
    echo "$(date +%T) sampler-last=$(tail -n 1 "$out/sampler.log" | cut -c1-8)"
  fi
  if ! lsusb | grep -qE '18d1:d001'; then echo "$(date +%T) USB gone"; break; fi
done
echo "sampler-last=$(grep '== up' "$out/sampler.log" | tail -n 1)"
sleep 5
kill $(jobs -p) 2>/dev/null
echo "done $(date +%T)"
