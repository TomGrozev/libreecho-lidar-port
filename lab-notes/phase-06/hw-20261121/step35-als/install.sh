#!/usr/bin/env bash
# Step 35: install the v0.2.27 lab OTA that adds the TSL2540 remove() fix
# and boot-on (private/lab/phase-07-prep/AlsFix.md) over Wi-Fi and wait for the confirmed state.
# Install procedure is the same as step31-mic/install.sh.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
dir=artifacts/phase-06/ota-step35-als
ver=0.2.27
out=lab/phase-06/hw-20261121/step35-als
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

# Step 33 fixes, read-only: light sensor, power controller, tmp112 and the
# thermal zone, clock persistence state, and the daemons that must still run.
dev 'uname -a
dmesg | grep -i -E "tsl2540|taos|mtk-power-controller|scpsys|tmp112|lm75|thermal" | tail -n 40
for f in /sys/bus/i2c/devices/0-0039/als_power_state /sys/bus/i2c/devices/0-0039/als_lux; do echo "$f=$(cat $f)"; done; ls /sys/bus/iio/devices/ 2>/dev/null; cat /sys/bus/iio/devices/*/name 2>/dev/null
for z in /sys/class/thermal/thermal_zone*; do echo "$z $(cat $z/type) $(cat $z/temp)"; done
for h in /sys/class/hwmon/hwmon*; do echo "$h $(cat $h/name) $(cat $h/temp1_input 2>/dev/null)"; done
ls -l /data/libreecho/config/time-epoch 2>/dev/null
grep -a -E "timed" /var/log/libreecho/system.log | tail -n 10
ps | grep -E "libreecho-(web|btd|timed|micd|waked|esphomed|audiod)" | grep -v grep' 120 > "$out/fix-checks.log"
t "fix-checks: $out/fix-checks.log"
