#!/usr/bin/env bash
# Step 21: push and install the lab OTA v0.2.16 (cue level match + audiod route fix).
# Writes userdata (generation tree, incoming bundle) and, via libreecho-update, the inactive boot slot + BCB.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
A=artifacts/phase-06/features-airplay2-lidar
txn=txn-0283eca3548303cfb36d2090
AD=lab/phase-06/adb.sh

$AD 20 shell 'mkdir -p /data/libreecho/generations /data/libreecho/incoming; df -h /data'
$AD 300 push "$A/ota-0.2.16/generations/$txn" /data/libreecho/generations/
$AD 300 push "$A/ota-0.2.16/lidar-lab-v0.2.16.ota.tar" /data/libreecho/incoming/local-install.ota.tar
$AD 300 shell "export PATH=/usr/local/sbin:\$PATH; g=/data/libreecho/generations/$txn
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-update status; libreecho-bootctl status"
