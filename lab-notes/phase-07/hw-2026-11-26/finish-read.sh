#!/usr/bin/env bash
# Read-only: finish the remaining live-area reads after the adb drop.
set -u
here=$(cd "$(dirname "$0")" && pwd)
T=$here/../../phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
A=$T/bin/adb
out=$here/live-read

timeout 20 "$A" devices -l
if ! timeout 10 "$A" shell true 2>/dev/null; then
  echo "DEVICE STILL OFFLINE"
  exit 0
fi
for spec in "tee2:/dev/mmcblk0p6:0:10240" "expdb:/dev/mmcblk0p7:0:20480" "misc:/dev/mmcblk0p8:0:1024"; do
  name=${spec%%:*}; rest=${spec#*:}; dev=${rest%%:*}; rest=${rest#*:}; skip=${rest%%:*}; cnt=${rest#*:}
  echo "== $name dev=$dev"
  timeout 240 "$A" shell "dd if=$dev bs=512 skip=$skip count=$cnt 2>/dev/null | base64" > "$out/$name.b64"
  base64 -d "$out/$name.b64" > "$out/$name.bin"
  rm -f "$out/$name.b64"
  echo "bytes=$(stat -c%s "$out/$name.bin") host_sha256=$(sha256sum "$out/$name.bin" | cut -d' ' -f1)"
done
echo "== persist on-device hash (contents not pulled)"
timeout 240 "$A" shell "dd if=/dev/mmcblk0p9 bs=65536 count=256 2>/dev/null | sha256sum"
