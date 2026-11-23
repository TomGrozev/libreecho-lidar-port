#!/bin/sh
# Step 31: bounded microphone level measurement.  Stop waked (the mono stream
# owner), read the mixer, capture 5 s of raw codec lanes and up to 8 s of the
# calibrated mono stream, then start waked again.
#
# The step 24 bug: `voiceprobe recv` uses its timeout per read, and micd never
# stops producing audio, so stream_mono never ended.  Every capture here is
# bounded by a total `timeout` deadline as well.  Silent: no playback.
P=/data/local/tmp/voiceprobe
R=/run/libreecho
O=/data/local/tmp/step31
mkdir -p "$O"
TAG=${1:-measure}

echo "=== micd status"
"$P" recv "$R/mic.sock" '{"v":1,"id":30,"cmd":"status","args":{}}' 2 \
    "$O/micd-status-$TAG.json"

echo "=== mixer PGA (Lidar ADC3101: ADC1..ADC4, range 0..80)"
for adc in ADC1 ADC2 ADC3 ADC4; do
    printf '%s: ' "$adc"
    tinymix get "$adc PGA Capture Volume"
done

echo "=== mic sensor contract before capture"
cat /proc/asound/card*/pcm*/sub*/hw_params 2>/dev/null | head -20

/etc/init.d/libreecho-waked.init stop > "$O/waked-stop-$TAG.log" 2>&1
echo "waked stop rc=$?"
sleep 1

echo "=== raw codec capture (5 s, 8 ch s32le 16 kHz, device 1 = profile)"
timeout -s INT 8 tinycap "$O/raw-$TAG.wav" -D 0 -d 1 -c 8 -r 16000 \
    -b 32 -p 640 -n 4 > "$O/tinycap-$TAG.log" 2>&1
echo "tinycap rc=$?"
ls -l "$O/raw-$TAG.wav" 2>/dev/null

echo "=== calibrated mono stream (bounded: 6 s request, 10 s total deadline)"
timeout -s KILL 10 "$P" recv "$R/mic.sock" \
    '{"v":1,"id":31,"cmd":"stream_mono","args":{}}' 6 "$O/mono-$TAG.bin"
echo "mono rc=$?"
ls -l "$O/mono-$TAG.bin" 2>/dev/null

/etc/init.d/libreecho-waked.init start > "$O/waked-start-$TAG.log" 2>&1
echo "waked start rc=$?"
sleep 2
ps -o pid,etime,args | grep -E 'waked|micd' | grep -v grep
