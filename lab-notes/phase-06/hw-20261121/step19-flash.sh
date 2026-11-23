#!/usr/bin/env bash
# Phase 6 step 19. From the running slot-B system: reboot into Kaeru fastboot, flash boot_b
# with the mute/LED/capture-fix v2 image, read boot_b back and compare, then reboot.
# Writes boot_b only; the BCB already selects slot B.
set -u
root=$(cd "$(dirname "$0")/../../.." && pwd)
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
out=$root/lab/phase-06/hw-20261121/step19-flash
img=$root/artifacts/phase-06/images-mute/boot-lidar-v2.img
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }

t "image $(sha256sum "$img")"
timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; tr " " "\n" </proc/cmdline | grep slot_suffix; libreecho-bootctl status b' > "$out/before.log" 2>&1
t "before rc=$? $(tr '\n' ' ' < "$out/before.log")"
timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl reboot-bootloader' > "$out/reboot-bootloader.log" 2>&1
t "reboot-bootloader request rc=$?"

for i in $(seq 1 45); do
  if timeout 10 fastboot getvar product > "$out/getvar.log" 2>&1; then break; fi
  sleep 2
done
t "fastboot getvar rc=$? after $i tries"
timeout 20 fastboot oem fetch-enable >> "$out/getvar.log" 2>&1

timeout 120 fastboot flash boot_b "$img" > "$out/flash.log" 2>&1
t "flash boot_b rc=$?"
timeout 900 fastboot fetch boot_b "$out/boot_b.bin" > "$out/fetch-b.log" 2>&1
t "fetch boot_b rc=$?"
want=$(sha256sum < "$img" | cut -d' ' -f1)
got=$(sha256sum < "$out/boot_b.bin" | cut -d' ' -f1)
t "expected $want readback $got"
if [ "$want" != "$got" ]; then t "MISMATCH: staying in fastboot"; exit 1; fi

timeout 30 fastboot reboot > "$out/fastboot-reboot.log" 2>&1
t "fastboot reboot rc=$?"
for i in $(seq 1 60); do
  if timeout 5 adb shell true >/dev/null 2>&1; then break; fi
  sleep 3
done
t "adb back after $i tries"
sleep 20
timeout 30 adb shell 'tr " " "\n" </proc/cmdline | grep slot_suffix; uname -r; grep -E "ledd|buttond|audiod" /var/log/libreecho/system.log | tail -15; tinymix -D 0 contents | grep -E "Output Mixer|LO DAC|PGA Capture"; cat /sys/bus/i2c/devices/0-003f/boot_animation' > "$out/after.log" 2>&1
t "after rc=$?"
t "done"
