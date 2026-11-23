#!/bin/sh
# Runs on the Lidar. Adds an ACM function beside ffs.adb, rebinds the UDC and
# respawns a root shell on /dev/ttyGS0. Logs to /tmp/acm-rebind.log.
g=/sys/kernel/config/usb_gadget/libreecho
c=$(ls "$g/configs")
u=$(cat "$g/UDC")
{
  echo "udc=$u cfg=$c"
  echo > "$g/UDC"
  mkdir -p "$g/functions/acm.gs0"
  [ -e "$g/configs/$c/acm.gs0" ] || ln -s "$g/functions/acm.gs0" "$g/configs/$c/acm.gs0"
  sleep 1
  echo "$u" > "$g/UDC"
  sleep 1
  echo "functions: $(ls "$g/functions")"
  echo "config: $(ls "$g/configs/$c")"
  ls -l /dev/ttyGS0 2>&1
  while :; do
    [ -c /dev/ttyGS0 ] && setsid -c sh </dev/ttyGS0 >/dev/ttyGS0 2>&1
    sleep 2
  done
} > /tmp/acm-rebind.log 2>&1
