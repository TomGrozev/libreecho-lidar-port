#!/bin/sh
# Step 24: silent STT probe.  Synthesize phrases with the on-device TTS
# "render" command (writes 16 kHz mono s16 PCM to /run/libreecho, never to the
# announcement bus, so nothing is audible), then feed each clip straight to
# sttd's recognize_stream socket.  No agentd, no wake word, no playback.
P=/data/local/tmp/voiceprobe
R=/run/libreecho
mkdir -p /data/local/tmp/step24

render() {
  # $1 text, $2 destination path under /run/libreecho
  "$P" recv "$R/tts.sock" "{\"v\":1,\"id\":20,\"cmd\":\"render\",\"args\":{\"text\":\"$1\",\"path\":\"$2\"}}" 8 "$2.reply" >/dev/null 2>&1
  echo "render $2: $(cat "$2.reply" 2>/dev/null)"
}

recognize() {
  # $1 pcm path, $2 label
  "$P" send "$R/stt.sock" '{"v":1,"id":10,"cmd":"recognize_stream","args":{}}' "$1" "/data/local/tmp/step24/$2.out" > "/data/local/tmp/step24/$2.reply" 2>&1
  echo "=== $2"
  cat "/data/local/tmp/step24/$2.reply"
  cat "/data/local/tmp/step24/$2.out"
}

render "set a timer for ten seconds" "$R/step24-timer10.pcm"
render "set a timer for two minutes" "$R/step24-timer2m.pcm"
render "what time is it" "$R/step24-time.pcm"

recognize "$R/step24-timer10.pcm" timer10
recognize "$R/step24-timer2m.pcm" timer2m
recognize "$R/step24-time.pcm" time
recognize /data/local/tmp/step24/alexa-what-time.pcm alexa-what-time
recognize /data/local/tmp/step24/alexa-twice.pcm alexa-twice
