#!/usr/bin/env bash
# Step 24: reboot into the freshly installed v0.2.21 slot A, force runtime
# volume 0 before anything can speak, then wait for the terminal OTA confirm.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
S=<DEVICE_IP_A>:5555
ADB=experiments/phase-06/hw-20261121/bin/adb
OUT=experiments/phase-06/hw-20261121/step24-voice
DEV='export PATH=/usr/local/sbin:$PATH;'

timeout 20 "$ADB" connect "$S" > "$OUT/connect-pre-reboot.log" 2>&1
image_hash() { "$ADB" -s "$S" shell 'dd if=/dev/mmcblk0p10 bs=4096 count=4096 2>/dev/null | sha256sum' 2>/dev/null | tr -d '\r'; }
"$ADB" -s "$S" shell "$DEV libreecho-bootctl status; libreecho-update status" > "$OUT/pre-reboot.log" 2>&1
timeout 120 "$ADB" -s "$S" push experiments/phase-06/hw-20261121/step24-voice/voiceprobe /data/local/tmp/voiceprobe > "$OUT/push-probe.log" 2>&1
"$ADB" -s "$S" shell 'chmod 0755 /data/local/tmp/voiceprobe; /data/local/tmp/voiceprobe 2>&1 | head -1' > "$OUT/probe-smoke.log" 2>&1

echo "rebooting at $(date -u +%T)" | tee -a "$OUT/reboot.log"
timeout 15 "$ADB" -s "$S" shell reboot > /dev/null 2>&1

deadline=$(( $(date +%s) + 1500 ))
ready=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  timeout 5 "$ADB" connect "$S" > /dev/null 2>&1
  if timeout 10 "$ADB" -s "$S" shell 'echo up' 2>/dev/null | tr -d '\r' | grep -q '^up$'; then
    ready=1; break
  fi
  sleep 5
done
echo "adb back after reboot: ready=$ready at $(date -u +%T)" | tee -a "$OUT/reboot.log"
[ "$ready" = 1 ] || { echo "FAIL: no adb after 25 min"; exit 1; }

# Volume 0 first: nothing in this run may be audible.  Retry until audiod answers.
for i in $(seq 1 60); do
  timeout 20 "$ADB" -s "$S" shell "/data/local/tmp/voiceprobe recv /run/libreecho/audio.sock '{\"v\":1,\"id\":1,\"cmd\":\"set_volume\",\"args\":{\"volume\":0}}' 1 /data/local/tmp/vol0.json" >/dev/null 2>&1
  if timeout 10 "$ADB" -s "$S" shell 'grep -q "\"ok\":true" /data/local/tmp/vol0.json 2>/dev/null && echo VOLOK' 2>/dev/null | tr -d '\r' | grep -q VOLOK; then
    echo "volume 0 confirmed at $(date -u +%T)" | tee -a "$OUT/reboot.log"
    break
  fi
  sleep 5
done
timeout 20 "$ADB" -s "$S" shell 'cat /data/local/tmp/vol0.json' > "$OUT/volume0.json" 2>&1

# Watch the health worker to its terminal state.
n=0
while [ "$(date +%s)" -lt "$deadline" ]; do
  timeout 30 "$ADB" -s "$S" shell "$DEV libreecho-bootctl status; libreecho-update status; echo ===PS; ps | grep -E 'waked|sttd|ttsd|agentd|audio-engine' | grep -v grep" > "$OUT/wait-$n.log" 2>&1
  tr -d '\r' < "$OUT/wait-$n.log" > "$OUT/wait-$n.clean"
  if grep -q '^ota_transaction_state=none' "$OUT/wait-$n.clean" && grep -q '^slot_a_success=1' "$OUT/wait-$n.clean"; then
    echo "confirmed at $(date -u +%T) after ${n} polls" | tee -a "$OUT/reboot.log"
    cp "$OUT/wait-$n.clean" "$OUT/confirmed.log"
    break
  fi
  if grep -q '^ota_transaction_state=rollback' "$OUT/wait-$n.clean"; then
    echo "ROLLED BACK at $(date -u +%T)" | tee -a "$OUT/reboot.log"
    cp "$OUT/wait-$n.clean" "$OUT/rolledback.log"
    break
  fi
  n=$((n + 1))
  sleep 10
done
tr -d '\r' < "$OUT/wait-$n.log"
