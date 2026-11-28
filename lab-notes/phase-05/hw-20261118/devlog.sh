#!/bin/sh
# Runs on the device, detached from adb. Appends kernel log deltas, USB gadget state,
# adbd state and interrupt counts to /data every second with sync, so the record
# survives a USB wedge and a power cycle. Read it back on the next boot.
#
# Test of the rebind hypothesis: libreecho-init binds the configfs gadget to the UDC
# once. When adbd closes and reopens FunctionFS, the kernel unbinds the gadget and
# nothing binds it again. With REBIND=1 this loop rebinds it, as Android's init does
# on sys.usb.ffs.ready.
REBIND=${REBIND:-1}
G=/sys/kernel/config/usb_gadget/libreecho
d=/data/libreecho-debug
mkdir -p "$d"
log="$d/run-$(cut -c1-8 /proc/sys/kernel/random/boot_id).log"
tmp=/tmp/devlog.dmesg
exec >>"$log" 2>&1
echo "== start $(cat /proc/uptime) rebind=$REBIND"
ls -l /dev/kmsg
mount | grep -E ' /dev | /run '
for f in state timeout pretimeout timeleft; do
  echo "wdt $f: $(cat /sys/class/watchdog/watchdog0/$f 2>&1)"
done
n=0
an=0
i=0
while :; do
  bound=$(cat "$G/UDC" 2>&1)
  adbd=$(pidof adbd)
  echo "== up $(cat /proc/uptime) udc=[$bound] state=$(cat /sys/class/udc/*/state 2>&1) adbd=[$adbd] ffs=$(ls /dev/usb-ffs/adb | tr '\n' ,)"
  dmesg > "$tmp"
  c=$(wc -l < "$tmp")
  [ "$c" -lt "$n" ] && n=0
  tail -n +$((n + 1)) "$tmp"
  n=$c
  c=$(wc -l < /tmp/adbd.log)
  [ "$c" -lt "$an" ] && an=0
  tail -n +$((an + 1)) /tmp/adbd.log | sed 's/^/adbd.log: /'
  an=$c
  if [ "$REBIND" = 1 ] && [ -z "$bound" ] && [ -n "$adbd" ] &&
     [ -e /dev/usb-ffs/adb/ep1 ] && [ -e /dev/usb-ffs/adb/ep2 ]; then
    udc=$(ls /sys/class/udc | head -n 1)
    if echo "$udc" > "$G/UDC"; then echo "REBIND ok $udc"; else echo "REBIND failed"; fi
  fi
  grep -E 'musb|wdt' /proc/interrupts
  if [ $((i % 10)) -eq 0 ]; then
    top -b -n 1 | head -n 12
    for t in /proc/$adbd/task/*; do
      echo "adbd task ${t##*/} $(cat $t/comm) $(sed -n 's/^State:[[:space:]]*//p' $t/status) $(cat $t/wchan)"
    done
  fi
  sync
  i=$((i + 1))
  sleep 1
done
