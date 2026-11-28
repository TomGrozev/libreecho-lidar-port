#!/bin/bash
# Phase 5 step 6: OTA v1 -> v2 over adb, following private/lab/phase-05/ota/README.md:136-166.
out=${1:?usage: ota_step6.sh <outdir>}
tx=txn-508529626fbd711fdbf6bf1c
run=../../../artifacts/phase-05/ota/lab-v2
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }

t "before: $(dev 'libreecho-update status; cat /data/libreecho/update/current' | tr '\n' ' ')"
dev 'mkdir -p /data/libreecho/generations /data/libreecho/incoming' > /dev/null
timeout 300 adb push "$run/generations/$tx" /data/libreecho/generations/ > "$out/push-gen.log" 2>&1 || { t "push generation failed"; exit 1; }
timeout 300 adb push "$run/lidar-lab-v0.2.12.ota.tar" /data/libreecho/incoming/local-install.ota.tar > "$out/push-tar.log" 2>&1 || { t "push bundle failed"; exit 1; }
t "pushed"
dev "g=/data/libreecho/generations/$tx
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync" 600 > "$out/install.log"
t "install: $(tr '\n' ' ' < "$out/install.log")"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }
# The persisted init log and its started-marker live on /data and would otherwise carry
# lines from earlier runs into this one.
dev 'rm -f /data/libreecho/init-persist.started /data/libreecho/init-persist.log' > /dev/null
timeout 15 adb shell reboot > /dev/null 2>&1
sleep 10
timeout 150 adb wait-for-device || { t "no adb after reboot"; exit 1; }
t "booted: $(dev 'tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"' | tr '\n' ' ')"
# Confirm runs only after a 180 s startup-ready wait plus three spaced probes, and the
# slot-B /tmp logs vanish on a reset, so poll for 12 min.  The reset evidence a
# reset leaves behind is the kernel's (pstore/last_kmsg); everything the script
# itself needs to survive is copied to /data every cycle, because these images
# keep /tmp on tmpfs: pstore, the init log tail and the boot-control state.
cap='mkdir -p /data/libreecho/reset-logs/pstore
r=$(tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p")
if [ "$r" = b ] && [ ! -e /data/libreecho/init-persist.started ]; then
  : > /data/libreecho/init-persist.started
  nohup sh -c "tail -f /tmp/init.log >> /data/libreecho/init-persist.log" >/dev/null 2>&1 &
fi
echo "== uptime $(cut -d" " -f1 /proc/uptime) boot_id $(cat /proc/sys/kernel/random/boot_id) $(tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab")"
libreecho-update status; cat /data/libreecho/update/features-status /data/libreecho/update/pending /data/libreecho/update/state
ls -l /run/libreecho
ps | grep -E "sttd|ttsd|waked" | grep -v grep
tail -n 30 /var/log/libreecho-sttd.log /var/log/libreecho-ttsd.log /var/log/libreecho-waked.log 2>/dev/null
ls -la /data/libreecho/update /data/libreecho/generations
cat /tmp/ota-confirm.log 2>/dev/null
tail -n 300 /tmp/init.log 2>/dev/null
tail -n 400 /tmp/init.log > /data/libreecho/reset-logs/init.log.tail 2>/dev/null
echo "== init-persist"; tail -n 400 /data/libreecho/init-persist.log 2>/dev/null
cp -a /sys/fs/pstore/. /data/libreecho/reset-logs/pstore/ 2>/dev/null
echo "== pstore"; ls -la /sys/fs/pstore; cat /sys/fs/pstore/* 2>/dev/null
echo "== last_kmsg"; cat /proc/last_kmsg 2>/dev/null
echo "== dmesg"; dmesg | tail -n 100
echo "== bcb"; if [ -n "$r" ]; then libreecho-bootctl status "$r"; else libreecho-bootctl status; fi
tail -n 400 /tmp/init.log 2>/dev/null | grep -q "ota-health-confirm-failed-rebooting" && echo "== step6-failure"'
# Failure logs are capped at three, so their count cannot signal a new failure; a changed
# boot_id after the first slot-B boot means the candidate was reset, which is the failure.
first_boot=
for i in $(seq 1 36); do
  timeout 60 adb wait-for-device > /dev/null 2>&1
  chunk=$(dev "$cap" 60)
  printf '%s\n' "$chunk" >> "$out/captures.log"
  boot=$(printf '%s\n' "$chunk" | sed -n 's/^== uptime .* boot_id \([^ ]*\).*/\1/p' | head -n 1)
  [ -z "$first_boot" ] && first_boot=$boot
  if printf '%s\n' "$chunk" | grep -q '== step6-failure' ||
     { [ -n "$boot" ] && [ "$boot" != "$first_boot" ]; }; then
    t "confirm failed for this boot (boot_id $first_boot -> ${boot:-?})"
    exit 1
  fi
  s=$(dev 'r=$(tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"); if [ -n "$r" ]; then libreecho-bootctl status "$r"; else libreecho-bootctl status; fi | grep -E "selected|success"; libreecho-update status; echo current=$(cat /data/libreecho/update/current)' | tr '\n' ' ')
  case $s in *"$tx"*slot_b_success=1*|*slot_b_success=1*"$tx"*) t "confirmed: $s"; exit 0 ;; esac
  sleep 20
done
t "not confirmed after 12 min: $s"
exit 1
