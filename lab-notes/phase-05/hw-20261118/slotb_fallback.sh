#!/bin/bash
# Phase 5 step 4. From Kaeru fastboot: boot slot A, activate slot B, then reboot
# from whichever slot is running and record slot, image and BCB on every boot
# until LK returns to slot A (or the boot limit is reached).
out=${1:?usage: slotb_fallback.sh <outdir> [max_boots]}
max=${2:-10}
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
snap() {
  timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH
    tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"
    libreecho-bootctl status | grep -E "selected|slot_[ab]_(priority|tries|success)"' 2>&1 | tr -d '\r' | tr '\n' ' '
}
wait_adb() { timeout 150 adb wait-for-device && sleep 3; }

fastboot reboot > /dev/null 2>&1
wait_adb || { t "slot A boot: no adb"; exit 1; }
t "boot 0: $(snap)"
t "activate b: $(timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl activate b; libreecho-bootctl status | grep -E "slot_b_(priority|tries)"' 2>&1 | tr -d '\r' | tr '\n' ' ')"
for ((n = 1; n <= max; n++)); do
  timeout 15 adb shell reboot > /dev/null 2>&1
  sleep 10
  if ! wait_adb; then t "boot $n: no adb within 150 s"; lsusb | grep -E '18d1|0e8d|0bb4' >> "$out/events.log"; exit 1; fi
  s=$(snap)
  t "boot $n: $s"
  # Back on slot A after having run slot B means LK fell back.
  case $s in *slot_suffix=_a*) [ "$n" -gt 1 ] && { t "fell back to A"; break; } ;; esac
done
t "done"
