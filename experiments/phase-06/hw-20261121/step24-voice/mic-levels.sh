#!/bin/sh
# Step 24: ambient capture levels.  Stop waked (the mic.sock stream owner),
# capture the calibrated mono stream from micd and a raw 8-channel ALSA
# capture with tinycap, then start waked again.  Silent: no playback.
P=/data/local/tmp/voiceprobe
R=/run/libreecho
O=/data/local/tmp/step24
mkdir -p "$O"

echo "=== micd status"
"$P" recv "$R/mic.sock" '{"v":1,"id":30,"cmd":"status","args":{}}' 2 "$O/micd-status.json"
cat "$O/micd-status.json"

/etc/init.d/libreecho-waked.init stop > "$O/waked-stop.log" 2>&1
echo "waked stop rc=$?"
sleep 1

echo "=== calibrated mono stream (3 s, s16le 16 kHz)"
"$P" recv "$R/mic.sock" '{"v":1,"id":31,"cmd":"stream_mono","args":{}}' 3 "$O/mono.raw"
ls -l "$O/mono.raw"

echo "=== raw ALSA capture (3 s, 8 ch, s32le, 16 kHz)"
tinycap "$O/raw.wav" -D 0 -d 1 -c 8 -r 16000 -b 32 -T 3 > "$O/tinycap.log" 2>&1
echo "tinycap rc=$?"
ls -l "$O/raw.wav" 2>/dev/null

/etc/init.d/libreecho-waked.init start > "$O/waked-start.log" 2>&1
echo "waked start rc=$?"
sleep 2
ps | grep -E 'waked|sttd|ttsd|agentd|audio-engine|micd' | grep -v grep
