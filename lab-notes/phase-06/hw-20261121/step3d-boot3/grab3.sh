#!/usr/bin/env bash
# Boot slot A (6.18, MUSB fix) from Kaeru and grab state with one short adb command per
# read. Each command has its own timeout so a wedged adbd does not swallow the next one.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
out=$root/lab/phase-06/hw-20261121/step3d-boot3
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
timeout 20 adb shell 'cat /proc/sys/kernel/random/boot_id' > "$out/boot_id.txt" 2>&1; t "boot_id rc=$?"
sleep 20
timeout 60 adb shell 'dmesg' > "$out/dmesg.txt" 2>&1;                            t "dmesg rc=$? lines=$(wc -l < "$out/dmesg.txt")"
timeout 20 adb shell 'cat /proc/partitions' > "$out/partitions.txt" 2>&1;        t "partitions rc=$?"
timeout 20 adb shell 'ls -l /sys/class/mmc_host; ls /sys/bus/mmc/devices; ls -l /dev/mmcblk* 2>&1 | head -30' > "$out/mmc.txt" 2>&1; t "mmc rc=$?"
timeout 20 adb shell 'ls /sys/bus/sdio/devices; for d in /sys/bus/sdio/devices/*; do echo "$d $(cat $d/vendor 2>/dev/null) $(cat $d/device 2>/dev/null)"; done' > "$out/sdio.txt" 2>&1; t "sdio rc=$?"
timeout 20 adb shell 'cat /sys/kernel/debug/devices_deferred 2>&1; echo ---; cat /proc/mounts' > "$out/deferred_mounts.txt" 2>&1; t "deferred rc=$?"
timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl status a' > "$out/bootctl.txt" 2>&1; t "bootctl rc=$?"
timeout 20 adb shell 'cat /proc/asound/cards 2>&1; echo ---; cat /proc/asound/pcm 2>&1' > "$out/audio.txt" 2>&1; t "audio rc=$?"
timeout 20 adb shell 'cat /sys/class/net/*/address 2>/dev/null; echo ---; ls /sys/class/net; echo ---; ls /sys/class/bluetooth 2>&1; echo ---; cat /proc/bus/input/devices' > "$out/net_input.txt" 2>&1; t "net_input rc=$?"
timeout 20 adb shell 'ls /sys/class/leds | head -40; echo ---; ls /sys/fs/pstore; ls -la /sys/fs/pstore' > "$out/leds_pstore.txt" 2>&1; t "leds_pstore rc=$?"
timeout 20 adb shell 'ls -la /run/libreecho 2>&1; echo ---; cat /data/libreecho/update/features-status 2>&1' > "$out/runtime.txt" 2>&1; t "runtime rc=$?"
t done
