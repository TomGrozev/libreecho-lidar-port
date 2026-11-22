#!/usr/bin/env bash
# Development update over Wi-Fi (PLAN.md, Phase 6, "Validate development updates over Wi-Fi").
# Every device command goes to adb over TCP ($S); USB is never addressed.
#   wifi_ota.sh good     <outdir>  install the v0.2.18 bundle, reboot, wait for the confirm
#   wifi_ota.sh rollback <outdir>  install the v0.2.20 bundle, whose image fails the OTA
#                                  health probe (web-status) and reboots itself; reboot once,
#                                  then only watch until LK falls back to the starting slot
# Writes userdata (generation tree, incoming bundle) and, through libreecho-update, the
# inactive boot slot and the BCB. No fastboot.
set -u
root=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$root"
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
part=${1:?usage: wifi_ota.sh good|rollback <outdir>}
out=${2:?usage: wifi_ota.sh good|rollback <outdir>}
case $part in
  good)     dir=artifacts/phase-06/ota-wifi/good;     ver=0.2.18 ;;
  rollback) dir=artifacts/phase-06/ota-wifi/rbtest;   ver=0.2.20 ;;
  *) echo "unknown part $part" >&2; exit 2 ;;
esac
tx=$(basename "$dir"/generations/txn-*)
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }
# The old TCP session dies with the reboot; reconnect until a shell answers.
reconnect() {
  sleep 15
  for i in $(seq 1 60); do
    timeout 10 adb connect "$S" > /dev/null 2>&1
    if [ "$(dev 'echo up' 10)" = up ]; then t "wifi adb back after $i tries"; return 0; fi
    sleep 5
  done
  t "no wifi adb after reboot"; return 1
}
state='uname -r; tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ls /data/libreecho/update; ip -4 addr show wlan0'

timeout 10 adb connect "$S" > "$out/connect.log" 2>&1
adb devices -l > "$out/devices.log" 2>&1
start=$(slot); [ -n "$start" ] || { t "no wifi adb at start"; exit 1; }
target=$([ "$start" = a ] && echo b || echo a)
t "start: part=$part bundle=v$ver tx=$tx slot=$start target=$target"
dev "$state" > "$out/state-before.log"

dev 'mkdir -p /data/libreecho/generations /data/libreecho/incoming' > /dev/null
timeout 600 adb -s "$S" push "$dir/generations/$tx" /data/libreecho/generations/ > "$out/push-gen.log" 2>&1 ||
  { t "push generation failed"; exit 1; }
timeout 600 adb -s "$S" push "$dir/lidar-lab-v$ver.ota.tar" /data/libreecho/incoming/local-install.ota.tar > "$out/push-tar.log" 2>&1 ||
  { t "push bundle failed"; exit 1; }
t "pushed: $(tail -n 1 "$out/push-tar.log")"
dev "g=/data/libreecho/generations/$tx
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-bootctl status" 600 > "$out/install.log"
t "install: $(grep -E 'verify_rc|signature|UPDATE_READY|install_rc' "$out/install.log" | tr '\n' ' ')"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }

if [ "$part" = good ]; then
  timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
  t "reboot requested"
  reconnect || exit 1
  first=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
  for i in $(seq 1 40); do
    s=$(dev "$state" 60)
    printf '== poll %s %s\n%s\n' "$i" "$(date +%T)" "$s" >> "$out/polls.log"
    boot=$(printf '%s\n' "$s" | grep -xE '[0-9a-f-]{36}' | head -n 1)
    if [ -n "$boot" ] && [ "$boot" != "$first" ]; then t "rebooted before confirm (rollback path)"; break; fi
    if printf '%s\n' "$s" | grep -qx "androidboot.slot_suffix=_$target" &&
       printf '%s\n' "$s" | grep -qx 'state=installed' &&
       printf '%s\n' "$s" | grep -qx "current=$tx" &&
       printf '%s\n' "$s" | grep -qx "generation=$tx" &&
       printf '%s\n' "$s" | grep -qx "slot_${target}_success=1" &&
       ! printf '%s\n' "$s" | grep -qx 'ota_transaction_pending=1'; then
      dev "$state" > "$out/state-after.log"
      t "PASS: confirmed on slot $target, generation $tx, over wifi"
      exit 0
    fi
    sleep 20
  done
  dev "$state" > "$out/state-after.log"
  t "FAIL: not confirmed"; exit 1
fi

# rollback: after the one reboot into the candidate, the host never reboots the unit. The
# candidate's health worker fails web-status, reboots with `reboot -f`, and LK spends one try
# per boot until it falls back. Record every boot seen over Wi-Fi until the start slot returns.
last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
t "reboot requested (the only host-initiated reboot); pre-reboot boot_id $last"
n=0
now=
deadline=$(( $(date +%s) + 2400 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  timeout 5 adb connect "$S" > /dev/null 2>&1
  s=$(dev "$state; grep -E 'ota-health-probe|ota-health-confirm|ota-slot|rollback' /tmp/init.log | tail -n 8" 30)
  boot=$(printf '%s\n' "$s" | grep -xE '[0-9a-f-]{36}' | head -n 1)
  if [ -n "$boot" ] && [ "$boot" != "$last" ]; then
    n=$((n + 1)); last=$boot
    now=$(printf '%s\n' "$s" | grep -oE 'slot_suffix=_[ab]' | head -n 1)
    t "boot $n seen: $now $(printf '%s\n' "$s" | grep -E 'libreecho.lab|slot_[ab]_(tries|success)=' | tr '\n' ' ')"
  fi
  [ -n "$boot" ] && printf '== %s boot %s\n%s\n' "$(date +%T)" "$n" "$s" >> "$out/polls.log"
  if [ "$n" -ge 1 ] && [ -n "$boot" ] && [ "$now" = "slot_suffix=_$start" ]; then
    sleep 90
    dev "$state" > "$out/state-after.log"
    t "PASS: LK fell back to slot $start with no host reboot after the first; wifi adb back"
    exit 0
  fi
  sleep 15
done
t "FAIL: not back on slot $start within 40 min"; exit 1
