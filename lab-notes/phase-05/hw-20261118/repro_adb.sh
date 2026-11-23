#!/bin/sh
# Boot slot A from Kaeru fastboot, start devlog.sh detached on the device, then
# restart the host adb server (the action that preceded each device-side USB
# disconnect) and check whether adb comes back.
out=${1:?usage: repro_adb.sh <outdir> [cycles]}
cycles=${2:-5}
here=$(dirname "$0")
mkdir -p "$out"
probe() {
  r=$(timeout 15 adb shell 'cat /proc/uptime /sys/kernel/config/usb_gadget/libreecho/UDC' 2>&1 | tr '\n' ' ')
  echo "$(date +%T) $1: $r" | tee -a "$out/probes.log"
  case $r in *.*' '*.*) return 0 ;; *) return 1 ;; esac
}

fastboot reboot > "$out/reboot.log" 2>&1
timeout 120 adb wait-for-device || { echo "adb never appeared $(date +%T)"; exit 1; }
echo "adb up $(date +%T)"
adb push "$here/devlog.sh" /data/libreecho-debug/devlog.sh > "$out/push.log" 2>&1 ||
  { adb shell 'mkdir -p /data/libreecho-debug' &&
    adb push "$here/devlog.sh" /data/libreecho-debug/devlog.sh >> "$out/push.log" 2>&1; }
adb shell 'setsid sh /data/libreecho-debug/devlog.sh </dev/null >/dev/null 2>&1 &'
sleep 3
probe start || exit 1

k=1
while [ "$k" -le "$cycles" ]; do
  adb kill-server
  sleep 2
  adb start-server > /dev/null 2>&1
  if timeout 30 adb wait-for-device && probe "restart-$k"; then :; else
    echo "$(date +%T) adb lost after server restart $k"
    break
  fi
  sleep 10
  k=$((k + 1))
done
lsusb | grep -E '18d1|0e8d' || echo "$(date +%T) not on USB"
journalctl -k --since "-15min" --no-pager | grep 'usb 1-1\.2' > "$out/host-usb.log"
echo "done $(date +%T)"
