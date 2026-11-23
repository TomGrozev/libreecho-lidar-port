# StreamPlayback: esphomed TTS streaming

Repo: `repos/LibreEcho-UI`, branch `fix/lidar-port-identity`.
Base commit when work started: `371950abb70d7e4f2f731c6a32fdcacf059226` (clean tree).
Parent of the commit below: `4b3c17d` (CpufreqWake landed first; no rebase needed).

## Commit

`a9cea2ea5a0b605d574e1fb2ce9e407262c7fde3` perf(esphomed): stream TTS playback and prime the amp on wake

Files:

- `src/adapter/esphome_playback.c`: `fetch_http()` drains up to 16 x 8 KiB reads per
  loop pass and playback starts on the first decoded audio rather than after the
  whole body; `dechunk()` de-frames chunked transfer encoding incrementally;
  `prepare()` returns 0 (need more), 1 (started), -1 (error), with exact size
  checks deferred to `p->eof`; streamed WAV (data size `UINT32_MAX` or 0) plays
  to EOF; receive buffer compaction in a 64 KiB window; `pad_silence()` on a
  mid-stream stall; CA chain parsed once per process (esphomed is
  single-threaded); `esp_playback_poll_fd()` added.
- `src/adapter/esphome_playback.h`: `eof`, `fetching`, `chunk_left`; per-instance
  `mbedtls_x509_crt` removed.
- `src/adapter/esphomed.c`: main loop polls the playback fd while `S.playing`
  (poll set 2 + CLIENTS, plus 1); `prime_bus()` writes 150 ms of zero 48 kHz
  stereo S16 frames to `S.bus_path` from `voice_start()` after the accept guard,
  best effort (nonblocking, stops on short write, never fails the turn), so
  Lidar's speaker amp settle is paid while the user is still speaking.
- Tests: `tests/test_esphomed_http.c` (streaming semantics, de-chunk cases),
  `tests/test_esphomed_playback_pacing.c` (`prepare()==1`),
  `tests/test_esphomed_playback_stream.c` (new: start before body end; streamed
  WAV to EOF with stall padding), `tests/test_esphomed_run.py` new `stream` case.

## Host tests (run, pass)

Built with host gcc against mbedTLS 3.6.7 at `/tmp/mbed-host/prefix`:

```
cc -std=c99 -D_POSIX_C_SOURCE=200809L -O1 -g -Wall -Wextra -Werror \
   -Wno-misleading-indentation -I/tmp/mbed-host/prefix/include \
   tests/test_esphomed_http.c src/adapter/radio_resample.c \
   /tmp/mbed-host/prefix/lib/libmbedtls.a \
   /tmp/mbed-host/prefix/lib/libmbedx509.a \
   /tmp/mbed-host/prefix/lib/libmbedcrypto.a -lm -o /tmp/t-http
```

Same pattern for `tests/test_esphomed_playback_pacing.c` (`t-pacing`),
`tests/test_esphomed_playback_stream.c` (`t-stream`), and
`tests/test_esphomed_playback.c` (`t-url`). Results: all OK (header ceiling and
de-chunking, WAV sizes and alignment, streaming start before body end, stall
padding, pacing lead >= 101 ms at 22050/16000/48000 Hz, URL boundary).

## ARM artifact

```
artifacts/phase-06/latency/stream-playback/libreecho-esphomed
sha256 1bbc3b03f74f8658cc2aab5ba4e9541e8d6e8206b49a0f007b06825859ece0cb
```

ELF 32-bit ARM EABI5 PIE, interpreter `/lib/ld-linux-armhf.so.3`.

Build (from `repos/LibreEcho-UI`):

```
artifacts/phase-05/toolchains/armhf-cc/arm-linux-gnueabihf-gcc \
  -Os -std=c99 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror \
  -Wno-misleading-indentation -ffunction-sections -fdata-sections \
  -I artifacts/phase-06/components/mbedtls-arm32/include -Isrc -Isrc/adapter \
  src/adapter/esphomed.c src/adapter/esphome_proto.c src/adapter/esphome_frame.c \
  src/adapter/esphome_noise.c src/adapter/esphome_playback.c \
  src/adapter/radio_resample.c src/adapter/mdns_client.c \
  src/adapter/mdns_lease.c src/config_store.c src/json.c \
  artifacts/phase-06/components/mbedtls-arm32/lib/libmbedtls.a \
  artifacts/phase-06/components/mbedtls-arm32/lib/libmbedx509.a \
  artifacts/phase-06/components/mbedtls-arm32/lib/libmbedcrypto.a \
  -Wl,--gc-sections -lm -o artifacts/phase-06/latency/stream-playback/libreecho-esphomed
```

`-Wno-misleading-indentation` is required: the tree's existing dense one-line
style trips that warning and the toolchain is built with `-Werror`.

## Integrator instructions

Copy the artifact over the UI bundle's esphomed at
`bundle/share/libreecho/esphomed` (the path `step31-mic/install.sh` and the
step20-engine `deploy.md` install), then build the image/OTA with
`build_images.sh` / `ota/build_ota.sh`. It is the same binary slot, so nothing
else in the payload changes.

## Verified vs not

Verified: host unit tests above; ARM cross build links and is a valid ARM PIE;
sha256 recorded. Not verified: no on-device run, no latency measurement of the
new path, `prime_bus()` behaviour against a real amp and a full bus FIFO, and
`tests/test_esphomed_run.py` was not executed (it needs a live esphomed and
network).
