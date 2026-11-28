#!/bin/bash
# Phase 6 step 6: OTA v1 -> v2 on 6.18, following the Phase 5 run 7 procedure
# (private/lab/phase-05/hw-20261118/ota_step6.sh).
# Setup: v1 image on boot_a, then install the v2 bundle from v1 over adb.
set -u
out=${1:?usage: ota_step6_618.sh <outdir>}
export PATH=$PWD/private/lab/phase-06/hw-20261121/bin:$PATH
tx=txn-7303218adf4646e5decf1908
run=private/artifacts/phase-06/ota/lab-v2
v1=private/artifacts/phase-06/images/boot-lidar-v1.img
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }

# --- setup: v1 on boot_a -------------------------------------------------
if timeout 5 fastboot getvar product > /dev/null 2>&1; then
  t "already in fastboot"
else
  t "reboot to fastboot for v1 flash"
  timeout 30 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl reboot-bootloader' > "$out/reboot-bootloader.log" 2>&1
  sleep 3
fi
for i in $(seq 1 30); do timeout 3 fastboot getvar product > /dev/null 2>&1 && break; sleep 2; done
timeout 20 fastboot oem fetch-enable > /dev/null 2>&1
timeout 60 fastboot fetch misc "$out/misc-before-v1.bin" > "$out/fetch-misc-before-v1.log" 2>&1
timeout 120 fastboot flash boot_a "$v1" > "$out/flash-v1.log" 2>&1 || { t "flash v1 failed"; exit 1; }
timeout 90 fastboot fetch boot_a "$out/boot_a-v1.bin" > "$out/fetch-v1.log" 2>&1
sha256sum "$v1" "$out/boot_a-v1.bin" > "$out/v1-hashes.txt"
h=$(sha256sum "$v1" | cut -d' ' -f1); [ "$(grep -c "$h" "$out/v1-hashes.txt")" -eq 2 ] || { t "v1 readback mismatch"; exit 1; }
timeout 10 fastboot reboot > /dev/null 2>&1
sleep 8
timeout 180 adb wait-for-device || { t "no adb after v1 boot"; exit 1; }
t "v1 boot: $(dev 'uname -r; tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"' | tr '\n' ' ')"
dev 'uname -a; cat /proc/cmdline; libreecho-update status; cat /data/libreecho/update/current 2>/dev/null; libreecho-bootctl status a; df -h /data; ls -la /data/libreecho/generations 2>/dev/null' > "$out/setup-state.log" 2>&1
t "v1 state captured"

# --- data snapshot ------------------------------------------------------
snap='cd /data/libreecho && find . -type f ! -path "./update/boot-*" ! -path "./init-persist.log" ! -path "./reset-logs/*" ! -path "./log/*" -exec sha256sum {} \; | sort'
dev "$snap" > "$out/data-before.log" 2>&1

# --- deliver v2 as an OTA ----------------------------------------------
dev 'mkdir -p /data/libreecho/generations /data/libreecho/incoming' > /dev/null
timeout 300 adb push "$run/generations/$tx" /data/libreecho/generations/ > "$out/push-gen.log" 2>&1 || { t "push generation failed"; exit 1; }
timeout 300 adb push "$run/lidar-lab-v0.2.14.ota.tar" /data/libreecho/incoming/local-install.ota.tar > "$out/push-tar.log" 2>&1 || { t "push bundle failed"; exit 1; }
t "pushed"
dev "g=/data/libreecho/generations/$tx
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync" 600 > "$out/install.log"
t "install: $(tr '\n' ' ' < "$out/install.log")"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }
dev 'rm -f /data/libreecho/init-persist.started /data/libreecho/init-persist.log' > /dev/null
timeout 15 adb shell reboot > /dev/null 2>&1
sleep 10
timeout 150 adb wait-for-device || { t "no adb after reboot"; exit 1; }
t "booted: $(dev 'tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"' | tr '\n' ' ')"

# --- confirm polling (Phase 5 run 7 logic) ------------------------------
cap='mkdir -p /data/libreecho/reset-logs/pstore
r=$(tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p")
if [ "$r" = b ] && [ ! -e /data/libreecho/init-persist.started ]; then
  : > /data/libreecho/init-persist.started
  nohup sh -c "tail -f /tmp/init.log >> /data/libreecho/init-persist.log" >/dev/null 2>&1 &
fi
echo "== uptime $(cut -d" " -f1 /proc/uptime) boot_id $(cat /proc/sys/kernel/random/boot_id) $(tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab")"
libreecho-update status; cat /data/libreecho/update/features-status /data/libreecho/update/pending /data/libreecho/update/state
ls -l /run/libreecho
ps | grep -E "agentd|sttd|ttsd|waked" | grep -v grep
tail -n 40 /var/log/libreecho-agentd.log /var/log/libreecho-sttd.log /var/log/libreecho-ttsd.log /var/log/libreecho-waked.log 2>/dev/null
cat /tmp/ota-confirm.log 2>/dev/null
tail -n 300 /tmp/init.log 2>/dev/null
tail -n 400 /tmp/init.log > /data/libreecho/reset-logs/init.log.tail 2>/dev/null
echo "== init-persist"; tail -n 400 /data/libreecho/init-persist.log 2>/dev/null
cp -a /sys/fs/pstore/. /data/libreecho/reset-logs/pstore/ 2>/dev/null
echo "== pstore"; ls -la /sys/fs/pstore; cat /sys/fs/pstore/* 2>/dev/null
echo "== dmesg"; dmesg | tail -n 100
echo "== bcb"; if [ -n "$r" ]; then libreecho-bootctl status "$r"; else libreecho-bootctl status; fi
tail -n 400 /tmp/init.log 2>/dev/null | grep -q "ota-health-confirm-failed-rebooting" && echo "== step6-failure"'
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
  # Terminal confirmation only.  `transaction_id` in the pending record and
  # slot_b_success=1 from bootctl both appear mid-confirm (BCB is confirmed
  # before the feature commit and the installed state), so matching either one
  # on its own declared success while the transaction was still `pending`.
  s=$(dev 'r=$(tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"); if [ -n "$r" ]; then libreecho-bootctl status "$r"; else libreecho-bootctl status; fi; libreecho-update status; echo current=$(cat /data/libreecho/update/current)')
  if printf '%s\n' "$s" | grep -qx 'state=installed' &&
     printf '%s\n' "$s" | grep -qx "current=$tx" &&
     printf '%s\n' "$s" | grep -qx "generation=$tx" &&
     printf '%s\n' "$s" | grep -qx 'slot_b_success=1' &&
     ! printf '%s\n' "$s" | grep -qx 'ota_transaction_pending=1'; then
    t "confirmed: $(printf '%s\n' "$s" | tr '\n' ' ')"
    exit 0
  fi
  sleep 20
done
t "not confirmed after 12 min: $s"
exit 1
