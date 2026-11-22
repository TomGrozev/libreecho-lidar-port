#!/usr/bin/env bash
# Wait for adb after a power cycle and grab the kernel log before anything else touches the
# device. The first 6.18 boot lost adb after a heavy state capture, so each read here is one
# short command with its own timeout.
set -u
out=experiments/phase-06/hw-20261121/step3b-early
mkdir -p "$out"
adb=experiments/phase-06/adb.sh
for _ in $(seq 1 180); do
	if $adb 5 get-state 2>/dev/null | awk '/device/{f=1} END{exit !f}'; then break; fi
	sleep 1
done
date -u +%FT%TZ > "$out/found.txt"
$adb 20 shell 'uname -r; cat /proc/cmdline; cat /proc/uptime' > "$out/id.txt" 2>&1
$adb 60 shell 'dmesg' > "$out/dmesg.txt" 2>&1
$adb 10 shell 'cat /proc/partitions; ls /sys/class/mmc_host /sys/bus/mmc/devices; ls /dev | sed -n "/mmc/p"' > "$out/mmc.txt" 2>&1
$adb 10 shell 'cat /sys/kernel/debug/devices_deferred 2>&1; ls /sys/fs/pstore' > "$out/deferred.txt" 2>&1
wc -l "$out"/*.txt
