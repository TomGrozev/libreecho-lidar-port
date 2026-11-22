#!/usr/bin/env bash
# Phase 6 step 2. From the running slot-B system: activate slot A, reboot into Kaeru
# fastboot, flash boot_a with the Phase 6 dev image, fetch boot_a/boot_b/misc back and
# compare hashes, then reboot into slot A. Writes boot_a and the misc BCB only.
set -u
root=$(cd "$(dirname "$0")/../../.." && pwd)
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
out=$root/experiments/phase-06/hw-20261121/step2-flash
img=$root/artifacts/phase-06/images/boot-lidar-dev.img
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }

t "image $(sha256sum "$img")"
timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl activate a' > "$out/activate.log" 2>&1
t "activate a rc=$?"
timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; echo --- status a; libreecho-bootctl status a; echo --- bcb; dd if=/dev/mmcblk0p8 bs=1 skip=864 count=64 2>/dev/null | od -An -tx1; sha256sum /dev/mmcblk0p8' > "$out/bcb-after-activate.log" 2>&1
t "bcb recorded rc=$?"

timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl reboot-bootloader' > "$out/reboot-bootloader.log" 2>&1
t "reboot-bootloader request rc=$? (a successful request does not return)"

for i in $(seq 1 45); do
  if timeout 10 fastboot getvar product > "$out/getvar.log" 2>&1; then break; fi
  sleep 2
done
t "fastboot getvar rc=$? after $i tries"
timeout 10 fastboot getvar product >> "$out/getvar.log" 2>&1
timeout 10 fastboot getvar kaeru-version >> "$out/getvar.log" 2>&1
timeout 20 fastboot oem fetch-enable >> "$out/getvar.log" 2>&1
timeout 10 fastboot getvar max-fetch-size >> "$out/getvar.log" 2>&1
t "vars: $(grep -E 'product:|kaeru-version:|max-fetch-size:' "$out/getvar.log" | tr '\n' ' ')"

timeout 120 fastboot flash boot_a "$img" > "$out/flash.log" 2>&1
t "flash boot_a rc=$?"
timeout 900 fastboot fetch boot_a "$out/boot_a.bin" > "$out/fetch-a.log" 2>&1
t "fetch boot_a rc=$?"
timeout 900 fastboot fetch boot_b "$out/boot_b.bin" > "$out/fetch-b.log" 2>&1
t "fetch boot_b rc=$?"
timeout 300 fastboot fetch misc "$out/misc.bin" > "$out/fetch-misc.log" 2>&1
t "fetch misc rc=$?"
{
  echo "== expected"
  sha256sum "$img"
  echo "== readbacks"
  sha256sum "$out/boot_a.bin" "$out/boot_b.bin" "$out/misc.bin"
} > "$out/hashes.log" 2>&1
t "hashes $(tr '\n' ' ' < "$out/hashes.log")"

timeout 30 fastboot reboot > "$out/fastboot-reboot.log" 2>&1
t "fastboot reboot rc=$?"
t "done"
