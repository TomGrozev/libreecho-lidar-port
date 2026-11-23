#!/usr/bin/env bash
# Add a CDC ACM function next to ffs.adb at runtime, respawn a root shell on
# /dev/ttyGS0, then drive that shell from the host with the Phase 4 helper.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
out=$root/lab/phase-06/hw-20261121/step3d-boot3
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }

timeout 20 adb shell 'g=/sys/kernel/config/usb_gadget/libreecho; c=$(ls $g/configs); u=$(cat $g/UDC); echo "udc=$u cfg=$c"; \
  nohup setsid sh -c "echo > $g/UDC; mkdir -p $g/functions/acm.gs0; [ -e $g/configs/$c/acm.gs0 ] || ln -s $g/functions/acm.gs0 $g/configs/$c/acm.gs0; sleep 1; echo $u > $g/UDC; sleep 1; while :; do [ -c /dev/ttyGS0 ] && setsid -c sh </dev/ttyGS0 >/dev/ttyGS0 2>&1; sleep 2; done" </dev/null >/tmp/acm-rebind.log 2>&1 &' > "$out/acm-setup.txt" 2>&1
t "rebind issued rc=$?"
sleep 5
found=0
for _ in $(seq 1 60); do
  if timeout 5 adb get-state 2>/dev/null | grep -q '^device$'; then found=1; break; fi
  sleep 1
done
t "adb after rebind found=$found"
if [ "$found" = 1 ]; then
  timeout 20 adb shell 'ls -l /sys/kernel/config/usb_gadget/libreecho/configs/*/ ; ls -l /dev/ttyGS0; cat /sys/class/udc/*/state' >> "$out/acm-setup.txt" 2>&1
fi
python3 "$root/lab/phase-04/acm_shell.py" --wait 60 --timeout 20 \
  --log "$out/acm-shell.log" \
  'id; uname -r; cat /proc/uptime; echo ACM618-MARKER' > "$out/acm-host.log" 2>&1
t "acm_shell rc=$?"
