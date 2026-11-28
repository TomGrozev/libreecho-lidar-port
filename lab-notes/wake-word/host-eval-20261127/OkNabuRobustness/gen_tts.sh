#!/bin/bash
# Throwaway TTS clip generator for the ok_nabu robustness comparison.
# Uses the espeak-ng built in ./build (source: work/inputs/public-deps/espeak-ng-source).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ESP="$HERE/build/src/espeak-ng"
export ESPEAK_DATA_PATH="$HERE/build/espeak-ng-data"
OUT="$HERE/audio/tts"
mkdir -p "$OUT"
tmp="$HERE/audio/.tmp"
mkdir -p "$tmp"

voices=(en-us en-us+f3 en-gb en-gb-x-rp en-gb-x-gbcwmd en-gb-x-gbclan en-029 en-gb-scotland)
speeds=(140 200)

for v in "${voices[@]}"; do
  for s in "${speeds[@]}"; do
    for phrase in "okay nabu" "ok nabu" "okey nabu"; do
      tag=$(echo "${phrase// /_}")
      base="$tmp/nabu_${v}_${s}_${tag}"
      "$ESP" -v "$v" -s "$s" -w "$base.wav" "$phrase" >/dev/null 2>&1
      ffmpeg -v error -y -i "$base.wav" -ar 16000 -ac 1 -sample_fmt s16 \
        "$OUT/nabu_${v}_${s}_${tag}.wav"
    done
    base="$tmp/alexa_${v}_${s}"
    "$ESP" -v "$v" -s "$s" -w "$base.wav" "alexa" >/dev/null 2>&1
    ffmpeg -v error -y -i "$base.wav" -ar 16000 -ac 1 -sample_fmt s16 \
      "$OUT/alexa_${v}_${s}.wav"
    base="$tmp/alexa2_${v}_${s}"
    "$ESP" -v "$v" -s "$s" -w "$base.wav" "alexa, what time is it" >/dev/null 2>&1
    ffmpeg -v error -y -i "$base.wav" -ar 16000 -ac 1 -sample_fmt s16 \
      "$OUT/alexa2_${v}_${s}.wav"
  done
done
rm -rf "$tmp"
ls "$OUT" | wc -l
