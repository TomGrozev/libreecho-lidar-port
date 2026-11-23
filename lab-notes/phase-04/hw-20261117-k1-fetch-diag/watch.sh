#!/usr/bin/env bash
# Log Lidar USB IDs once a second for up to 400 s; on the ACM gadget run the diagnostics,
# on fastboot after a preloader has been seen, stop.
D=private/lab/phase-04/hw-20261117-k1-fetch-diag
: > "$D/observer.log"
start=$(date +%s)
last=; seenpl=
for i in $(seq 1 400); do
  ids=$(lsusb | awk '/0bb4|0e8d|1d6b:0104/ {print $6}' | tr '\n' ' ')
  if [ "$ids" != "$last" ]; then echo "$(date +%T) +$(( $(date +%s) - start ))s [$ids]" | tee -a "$D/observer.log"; last=$ids; fi
  case "$ids" in
    *0e8d:2000*) seenpl=1;;
    *1d6b:0104*) python3 private/lab/phase-04/acm_shell.py --usbfs --wait 30 --log "$D/acm-diagnostics.log" >/dev/null 2>&1
                 echo "$(date +%T) acm rc=$?" | tee -a "$D/observer.log"; exit 0;;
    *0bb4:0c01*) [ -n "$seenpl" ] && { echo "$(date +%T) fastboot after boot" | tee -a "$D/observer.log"; exit 0; };;
  esac
  sleep 1
done
