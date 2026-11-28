#!/usr/bin/env bash
# Read-only: pull boot-chain areas from the live unit over adb (shell+base64,
# since this adb lacks exec-out) for hash evidence.
set -u
here=$(cd "$(dirname "$0")" && pwd)
T=$here/../../phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$T/lib
A=$T/bin/adb
out=$here/live-read
mkdir -p "$out"

read_area() {
  name=$1 dev=$2 skip=$3 cnt=$4
  echo "== $name dev=$dev bs=512 skip=$skip count=$cnt"
  timeout 240 "$A" shell "dd if=$dev bs=512 skip=$skip count=$cnt 2>/dev/null | base64" > "$out/$name.b64"
  base64 -d "$out/$name.b64" > "$out/$name.bin"
  rm -f "$out/$name.b64"
  host=$(sha256sum "$out/$name.bin" | cut -d' ' -f1)
  devhash=$(timeout 240 "$A" shell "dd if=$dev bs=512 skip=$skip count=$cnt 2>/dev/null | sha256sum" | cut -d' ' -f1)
  echo "bytes=$(stat -c%s "$out/$name.bin") host_sha256=$host device_sha256=$devhash match=$([ "$host" = "$devhash" ] && echo yes || echo NO)"
}

read_area gpt /dev/mmcblk0 0 176
read_area gpt_backup /dev/mmcblk0 14942175 33
read_area lk_a /dev/mmcblk0p3 0 2048
read_area lk_b /dev/mmcblk0p5 0 2048
read_area tee1 /dev/mmcblk0p4 0 10240
read_area tee2 /dev/mmcblk0p6 0 10240
read_area expdb /dev/mmcblk0p7 0 20480
read_area misc /dev/mmcblk0p8 0 1024

echo "== persist on-device hash (contents not pulled)"
timeout 240 "$A" shell "dd if=/dev/mmcblk0p9 bs=65536 count=256 2>/dev/null | sha256sum"
