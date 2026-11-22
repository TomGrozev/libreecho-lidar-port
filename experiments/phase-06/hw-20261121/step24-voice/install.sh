#!/usr/bin/env bash
# Step 24: install the v0.2.21 voice-stack lab OTA over Wi-Fi into slot A.
# Bundle: images-cue v2 boot (12f31aed, OTA profile, audio-profile present) +
# features-airplay2-drain catalog (wakeword, stt, tts, assistant, drain engine).
# Writes userdata (generation tree, incoming bundle) and, through
# libreecho-update, the inactive boot slot and the BCB. No fastboot, no USB.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
S=<DEVICE_IP_A>:5555
ADB=experiments/phase-06/hw-20261121/bin/adb
OUT=experiments/phase-06/hw-20261121/step24-voice
A=artifacts/phase-06/ota-step24-voice
txn=txn-219f754fee5dc47b9e27a977
mkdir -p "$OUT"

timeout 20 "$ADB" connect "$S" > "$OUT/connect.log" 2>&1
"$ADB" -s "$S" shell 'export PATH=/usr/local/sbin:$PATH; libreecho-bootctl status; libreecho-update status; cat /data/libreecho/update/current' > "$OUT/state-before.log" 2>&1

"$ADB" -s "$S" shell 'mkdir -p /data/libreecho/generations /data/libreecho/incoming; df -h /data' > "$OUT/df.log" 2>&1
timeout 600 "$ADB" -s "$S" push "$A/generations/$txn" /data/libreecho/generations/ > "$OUT/push-gen.log" 2>&1 || { echo "push generation failed"; exit 1; }
timeout 600 "$ADB" -s "$S" push "$A/lidar-lab-v0.2.21.ota.tar" /data/libreecho/incoming/local-install.ota.tar > "$OUT/push-tar.log" 2>&1 || { echo "push bundle failed"; exit 1; }

"$ADB" -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; g=/data/libreecho/generations/$txn
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-bootctl status; libreecho-update status" > "$OUT/install.log" 2>&1
echo "--- install log tail ---"
tr -d '\r' < "$OUT/install.log" | tail -n 60
