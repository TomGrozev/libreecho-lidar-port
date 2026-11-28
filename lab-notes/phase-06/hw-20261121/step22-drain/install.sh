#!/usr/bin/env bash
# Step 22: push and install the lab OTA v0.2.17 (engine drains the PCM ring and
# flushes the sub-period cue tail before muting LO DAC).
# Writes userdata (generation tree, incoming bundle) and, via libreecho-update, the inactive boot slot + BCB.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
A=artifacts/phase-06/features-airplay2-drain
txn=txn-a0cd2a02d88a49761d4be3f1
AD=lab/phase-06/adb.sh

$AD 20 shell 'mkdir -p /data/libreecho/generations /data/libreecho/incoming; df -h /data'
$AD 300 push "$A/ota/generations/$txn" /data/libreecho/generations/
$AD 300 push "$A/ota/lidar-lab-v0.2.17.ota.tar" /data/libreecho/incoming/local-install.ota.tar
$AD 300 shell "export PATH=/usr/local/sbin:\$PATH; g=/data/libreecho/generations/$txn
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-update status; libreecho-bootctl status"
