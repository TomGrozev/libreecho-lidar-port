#!/usr/bin/env bash
# Phase 6 step 4: A/B fallback on the 6.18 dev image, adapted from
# lab/phase-05/hw-20261118/slotb_fallback.sh. Starts booted on A,
# activates B, then reboots until LK returns to A (or the boot limit).
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
out=$root/lab/phase-06/hw-20261121/step4-ab-fallback
mkdir -p "$out"
max=${1:-6}
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
snap() {
  timeout 25 adb shell 'uname -r; tr " " "\n" < /proc/cmdline | grep -E "slot_suffix|libreecho.lab"; export PATH=/usr/local/sbin:$PATH; libreecho-bootctl status a' 2>&1 | tr -d '\r'
}
wait_adb() { timeout 150 adb wait-for-device && sleep 3; }
bcu() { timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl status a' 2>&1 | tr -d '\r'; }

if ! wait_adb; then t "no adb at start"; exit 1; fi
snap > "$out/boot0.txt"
t "boot 0 done"
bcu > "$out/bcb-before-activate.txt"
t "bcb before activate: $(tr '\n' ' ' < "$out/bcb-before-activate.txt")"
timeout 20 adb shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl activate b' > "$out/activate.log" 2>&1
t "activate b rc=$?"
bcu > "$out/bcb-after-activate.txt"
t "bcb after activate: $(tr '\n' ' ' < "$out/bcb-after-activate.txt")"

for n in $(seq 1 "$max"); do
  timeout 15 adb shell 'reboot' > /dev/null 2>&1
  sleep 8
  if ! wait_adb; then t "boot $n: no adb"; exit 1; fi
  snap > "$out/boot$n.txt"
  if grep -q 'slot_suffix=_a' "$out/boot$n.txt"; then
    t "boot $n: back on A"
    break
  fi
  t "boot $n: $(head -1 "$out/boot$n.txt") slot $(grep slot_suffix "$out/boot$n.txt" | tr -d ' ')"
done
bcu > "$out/bcb-final.txt"
snap > "$out/final.txt"
t "final: $(tr '\n' ' ' < "$out/final.txt")"
