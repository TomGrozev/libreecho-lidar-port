#!/usr/bin/env bash
# Owner-approved plain reboot to restore the tsl2540 after the rebind probe
# left it degraded. No flash, no image install; slot a stays the boot slot.
set -u
root=$(cd "$(dirname "$0")/../../../../.." && pwd)
out=$(cd "$(dirname "$0")" && pwd)
S=<DEVICE_IP_A>:5555
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
dev() { timeout "${2:-30}" adb -s "$S" shell "$1" 2>&1 | tr -d '\r'; }

old=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
echo "old boot_id: $old"
dmesg_before=$(dev 'dmesg | grep -c "Probe ok"' 20)
echo "probe_ok before: $dmesg_before"
echo "reboot output: $(dev 'reboot' 20)"
echo "reboot sent $(date +%T)"
deadline=$(( $(date +%s) + 600 ))
new=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  timeout 5 adb connect "$S" > /dev/null 2>&1
  cur=$(dev 'cat /proc/sys/kernel/random/boot_id' 8)
  if [ -n "$cur" ] && [ "$cur" != "$old" ]; then
    new=$cur
    echo "new boot_id: $new at $(date +%T)"
    break
  fi
  sleep 4
done
if [ -z "$new" ]; then
  echo "NO REBOOT: boot_id unchanged after 600 s"
  exit 1
fi
sleep 15
timeout 10 adb -s "$S" forward tcp:18090 tcp:8080 > /dev/null 2>&1
{
  echo "uname: $(dev 'uname -a' 20)"
  echo "slot: $(dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20)"
  echo "boot_id: $(dev 'cat /proc/sys/kernel/random/boot_id' 20)"
  echo "=== update state"
  dev 'cat /data/libreecho/update/current; cat /data/libreecho/update/boot-health 2>/dev/null' 20
  echo "=== tsl2540 dmesg"
  dev 'dmesg | grep -i -E "tsl2540|TSL2540" | tail -20' 30
  echo "=== als attrs"
  dev 'D=/sys/devices/platform/soc/11009000.i2c/i2c-0/0-0039; for f in als_power_state als_lux als_ch0 als_ch1 als_gain als_itime; do echo "$f=$(cat $D/$f 2>/dev/null)"; done' 30
  echo "=== oops count"
  dev 'echo "end_trace=$(dmesg | grep -c "end trace")"' 20
  echo "=== daemons"
  dev 'ps | grep -E "libreecho-(web|btd|timed|micd|waked|esphomed|audiod)" | grep -v grep' 30
} > "$out/api/reboot-after.txt" 2>&1
cat "$out/api/reboot-after.txt"
