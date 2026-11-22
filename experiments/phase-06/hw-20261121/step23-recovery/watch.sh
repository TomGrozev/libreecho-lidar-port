#!/usr/bin/env bash
# Step 23: wait up to ~4 min for Kaeru fastboot after the owner's Action-held power-on, then
# read kaeru-version and current-slot. Read-only: no flash, no erase, no oem writes.
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root" || exit 1
log=experiments/phase-06/hw-20261121/step23-recovery/fastboot.log
fb=experiments/phase-04/fb.sh
out=""
for i in $(seq 1 80); do
  out=$("$fb" 4 devices 2>&1)
  if [[ "$out" == *fastboot* ]]; then break; fi
  sleep 2
done
{
  date +%T
  echo "watch: $out"
  "$fb" 15 getvar kaeru-version 2>&1
  "$fb" 15 getvar current-slot 2>&1
} | tee -a "$log"
