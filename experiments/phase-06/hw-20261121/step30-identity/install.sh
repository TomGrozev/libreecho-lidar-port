#!/usr/bin/env bash
# Step 30: install the v0.2.23 identity/privacy lab OTA over Wi-Fi and wait
# for the terminal confirmed state (PLAN.md Phase 6, "Validate development
# updates over Wi-Fi").  Every device command goes to adb over TCP; USB is
# never addressed.
#
# Bundle: artifacts/phase-06/ota-step30-identity/ -- OTA-profile v2 boot from
# the rebuild with the wlan0 factory-MAC fallback in esphomed and the Lidar
# DTS privacy node named amz_privacy, plus the phase-05 feature catalog so the
# voice stack and drain engine stay byte-identical.  Writes userdata
# (generation tree, incoming bundle) and, through libreecho-update, the
# inactive boot slot and the BCB. No fastboot.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
dir=artifacts/phase-06/ota-step30-identity
ver=0.2.23
out=experiments/phase-06/hw-20261121/step30-identity
tx=$(basename "$dir"/generations/txn-*)
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }
# The old TCP session dies with the reboot; reconnect until a shell answers.
reconnect() {
  local deadline=$(( $(date +%s) + ${1:-1200} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    timeout 10 adb connect "$S" > /dev/null 2>&1
    if timeout 15 adb -s "$S" shell 'true' > /dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}
state='uname -r; tr " " "\n" < /proc/cmdline; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ls /data/libreecho/update; ip -4 addr show wlan0'

timeout 10 adb connect "$S" > "$out/connect.log" 2>&1
adb devices -l > "$out/devices.log" 2>&1
start=$(slot); [ -n "$start" ] || { t "no wifi adb at start"; exit 1; }
target=$([ "$start" = a ] && echo b || echo a)
t "start: bundle=v$ver tx=$tx slot=$start target=$target"
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
t "install: $(sed -n 's/.*\(verify_rc=[0-9]*\).*/\1/p;s/.*\(UPDATE_READY[^ ]*\) slot=\([ab]\).*/ready=\2/p;s/.*\(install_rc=[0-9]*\).*/\1/p' "$out/install.log" | tr '\n' ' ')"
sed -n 's/.*ota_manifest_signature=\(.*\)/signature=\1/p' "$out/install.log" >> "$out/events.log"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }

last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
t "reboot requested; pre-reboot boot_id $last"
[ "$(dev 'cat /proc/sys/kernel/random/boot_id' 20)" != "$last" ] || true
reconnect 1200 || { t "no adb after reboot"; exit 1; }
t "adb back on slot $(slot)"

# Terminal confirmed state: the target slot runs, the transaction is installed,
# and generation/current agree.  Same check as ota_step6_618.sh.
deadline=$(( $(date +%s) + 1200 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  s=$(dev "$state" 20)
  {
    echo "== $(date +%T)"
    printf '%s\n' "$s"
  } >> "$out/polls.log"
  now=$(printf '%s\n' "$s" | sed -n 's/^androidboot.slot_suffix=_//p' | head -n 1)
  [ -z "$now" ] && now=$(printf '%s\n' "$s" | sed -n 's/.*androidboot.slot_suffix=_\([ab]\).*/\1/p' | head -n 1)
  gen=$(printf '%s\n' "$s" | sed -n 's/^generation=//p' | head -n 1)
  cur=$(printf '%s\n' "$s" | sed -n 's/^current=//p' | head -n 1)
  st=$(printf '%s\n' "$s" | sed -n 's/^state=//p' | head -n 1)
  if [ "$now" = "$target" ] && [ "$st" = installed ] && [ "$gen" = "$tx" ] && [ "$cur" = "$tx" ]; then
    printf '%s\n' "$s" > "$out/state-after.log"
    t "CONFIRMED: slot=$now state=$st generation=$gen current=$cur"
    break
  fi
  sleep 15
done
[ -s "$out/state-after.log" ] || { t "FAIL: not confirmed on slot $target within 20 min"; exit 1; }

# Powers the serial/GPIO acceptance checks; read-only.
dev 'ls -l /dev/ttyS2 /dev/gpiochip*; cat /sys/bus/gpio/devices/gpiochip*/uevent; cat /sys/class/tty/ttyS2/type; readlink /sys/class/tty/ttyS2/device; dmesg | grep -i -E "ttyS|gpiochip" | tail -20; ps | grep -E "libreecho-(agentd|waked|audiod|micd|networkd|ttsd|sttd|esphomed)" | grep -v grep; cat /run/libreecho/startup-ready 2>/dev/null' 120 > "$out/after-checks.log"

# Identity: the DTS node rename must give every reader the expected sysfs path.
dev 'ls -d /sys/devices/platform/*privacy*; ls -l /sys/devices/platform/*privacy*/privacy_state /sys/devices/platform/*privacy*/mute_lamp 2>/dev/null; cat /sys/devices/platform/*privacy*/privacy_state 2>/dev/null' 60 > "$out/privacy-checks.log"

# ESPHome config load: the satellite must own an identity MAC.  A missing
# status file is fine while the pipeline mode is local; the health check only
# asserts the running daemon, and the log shows any config rejection.
dev 'P=$(cat /var/run/libreecho-esphomed.pid 2>/dev/null)
if [ -n "$P" ]; then
  /usr/local/sbin/libreecho-esphomed --health-check /var/run/libreecho-esphomed.pid /run/libreecho/esphome-status.json 6053 /usr/local/sbin/libreecho-esphomed ready; echo "esphomed_health_rc=$?"
else
  echo esphomed_pid_missing
fi
cat /run/libreecho/esphome-status.json 2>/dev/null
tail -n 5 /var/log/libreecho-esphomed.log 2>/dev/null' 60 > "$out/esphomed-checks.log"
t "after-checks: $out/after-checks.log privacy: $out/privacy-checks.log esphomed: $out/esphomed-checks.log"
