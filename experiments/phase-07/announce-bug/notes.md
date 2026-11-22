# Announcement bug: pink LED, then no audio (2026-11-22)

Status: investigation only. No source change, no device write, no reboot. The root cause is
narrowed to one function but not proven at the line level.

## Report

The owner sends a Home Assistant (HA) text-to-speech announcement to the Lidar. The ring
flashes pink and the announcement stops. Sending it again plays the audio and the LED does
not flash.

Unit: <DEVICE_IP_A>, LibreEcho lab OTA v0.2.28, UI `repos/LibreEcho-UI` f43dade, engine
LibreEcho-Platform 32f3dbd. HA 2026.11.2 (User-Agent in the pod capture; an earlier note said
2026.10.4) at <LAN_HOST_A_2>. Music Assistant (MA) 2.10.13 at <LAN_HOST_A_52>, connected to
`sendspind`.

## What ran

- Read-only device reads over the phase-06 adb wrapper. Raw output is in
  `dumps/20261122-lidar-announce/` (private; `proc-starts.txt` has the Sendspin PSK removed).
- `capture-device.sh`: a read-only 50 ms poller of esphomed status, engine status, TCP
  peers and the `system.pcm` mtime. It ran as `adb shell sh -s < capture-device.sh`.
  Output: `dumps/20261122-lidar-announce/capture-live.txt`. The owner sent two
  announcements from the HA media panel (TTS, "Sendspin device") during the capture.
- `EngineBusInterplay/fifo_semantics.c` and `run.log`: a host test of FIFO write errors
  with the engine's open mode.
- `EsphomedPlaybackRepro/`: a host harness that drives the real `esp_playback_tick` over a
  socketpair with an instrumented copy of `esphome_playback.c` (records the failing line).
- HA, MA, aiohttp and ffmpeg source reading at the pinned tags (no traffic capture).

## Evidence

1. Pink is esphomed's `error` profile (`src/adapter/esphomed.c:108-110`). `turn_clear()`
   sets it when a turn ends with any result other than `success` (`esphomed.c:118-120`).
2. All three captured esphomed attempts ended with `last_result: playback_error`
   (00:56:03 from the first report, and both live attempts).
3. In the live capture, each attempt opens one TCP connection to HA port 8123. The engine
   shows the `system` bus active about 80 ms later. `playback_error` appears within the next
   50 to 80 ms poll, and the HA socket is gone in the same sample. The engine keeps playing
   the queued audio for 0.75 s (first attempt) and 0.23 s (second attempt) after the error.
   The owner heard the start of the chime only.
4. `playback_error` with bus audio already written comes only from
   `esp_playback_tick() < 0` (`esphomed.c:344`). The other `playback_error` sites
   (`esphomed.c:175,191,204`) fail before any bus write.
5. The engine cannot cause the write error. It holds every bus FIFO open `O_RDWR` from
   start to exit (`audio_engine.c:1387-1390`, closed only at `:3064`), so a producer write
   sees `EAGAIN` and never `EPIPE` (`fifo_semantics.c`, `run.log`). The engine stayed in
   the `system` session after esphomed gave up, so its reader was alive.
6. HA serves the same bytes for a first send and a repeat: a chunked response with no
   `Content-Length`, a WAV header with RIFF and data sizes `0xFFFFFFFF`, 48 kHz mono
   16-bit, in reads of at most 2048 bytes (`esphome/ffmpeg_proxy.py`, chunk size 2048).
   HA ignores `success=false` from the device, so it does not retry.
7. esphomed logs nothing when playback fails (`libreecho-esphomed.log` is empty), so the
   device does not record which branch failed.

## Conclusion

The failure is in esphomed's fetch and decode of HA's proxied WAV stream
(`src/adapter/esphome_playback.c`, `tick_once()` and `fetch()`), a few HA chunks after
playback starts. The engine, the audio bus and 32f3dbd are not the cause.

The "second send works" part of the first report did not go through esphomed: there was no
new esphomed result and no `system.pcm` write. The airplayd log shows Sendspin stream
starts at that time. MA's announcement routing falls back to its own Sendspin stream when
it does not find a ready native player
(`music_assistant/controllers/players/announcements.py:474-497`). This is an inference;
no MA log was read. In the live capture, Sendspin stayed idle and both sends failed.

## Candidate branches

Confirmed defect on the failing path, trigger on the device not proven:
`dechunk()` loses state when a `recv()` ends inside a chunk-size line
(`esphome_playback.c:89-91`). A split after 1 to 3 hex digits drops the digits it parsed
(the loop breaks at `:90`, and `p->received = w` at `:106` discards them), so the next read
parses the rest of the line as a size, usually 0, and the stream then fails. A split
between `\r` and `\n` returns -1 at `:91`. The host harness reproduces both. A plain HTTP
stream can split anywhere when TCP segments or the 8192-byte read cap cut a chunk header.
The harness did not hit the split with HA's chunk layout and 8192-byte read boundaries.

The same loss hits the final `0\r\n\r\n`. A read ending after 1 to 4 of its bytes drops the
parsed `0\r\n` (or the `0`), and the next read sees a bare `\r\n` and fails at `:91`, after
the whole body has arrived. Harness, send 4 body from the <BRIDGE_A> capture, `chunked:2048`, writes
every 4096 bytes plus one split in the terminator: the split before `0` passes; the four
splits inside it fail at `:91` with about 0.9 s of audio already written. A failure here
leaves no unread data, so the device closes with FIN, the same as a success.

Reachable, not reproduced with HA-shaped input:

- The response closes without the final `0\r\n\r\n` chunk (`esphome_playback.c:160`).
- Bytes after the final chunk (`esphome_playback.c:96`).
- The end-of-body sample count check (`esphome_playback.c:200`); every tested shape ended
  within 2 frames.

## Pod-side capture (01:30:07 to 01:31:13 UTC)

The owner ran `talosctl pcap` on node <K8S_NODE_A>, interface `<CILIUM_IFACE_A>` (the Cilium side of
the HA pod `<K8S_NAMESPACE_A>/<HA_POD_A>`, pod IP <CLUSTER_IP_1>), and sent three
announcements. File: `<PCAP_FILE_A>` (owner's home, not copied into the workspace). Parsed
with an ad hoc Python reader in the session; no script kept.

Limits: the capture holds only packets the pod sent, and nothing to or from <LAN_NET_B>.
The pod reaches the IoT LAN through a Multus macvlan interface (`net2`, <LAN_HOST_A_2>, master
`<BRIDGE_A>`, from `kubectl get pod` and the `network/<NETATTACH_A>` NetworkAttachmentDefinition),
so the device's fetch and the ESPHome API traffic did not cross the captured interface.

What it shows:

| Send | play_media result | `<HA_ENTITY_A>` | HA ffmpeg read of MA's `/announcement/<MA_PLAYER_A>.mp3` | Outcome |
| --- | --- | --- | --- | --- |
| 1 | 26.824 | playing 26.826, idle 30.961 | 26.900 to 27.002, whole file (about 134 KB), normal close | played |
| 2 | 38.363 | playing 38.365, idle 42.211 | 38.443 to 38.597, whole file, normal close | played |
| 3 | 57.934 | playing 57.938, idle 58.076 | 57.999 to 58.078, 79 KB read, then FIN and RST from HA | pink, esphomed `playback_error` at 01:30:58 |

Times are seconds after 01:30:00 UTC.

- All three sends took the same route. The owner states every attempt was a Sendspin send.
  On HA's side: MA announcement on its player `<MA_PLAYER_A>`, HA `play_media` on
  `<HA_ENTITY_A>`, and HA's ffmpeg pulls the MP3 from MA
  (<CLUSTER_IP_2>:8097). The service calls came over a websocket from the
  `network/<HOME_DOMAIN_A>-gateway` pod. Which device service received each stream is not in
  the capture.
- Sends 1 and 2 played over this route with the same input that failed in send 3.
- In send 3 the device dropped its HA connection about 70 ms after its GET. HA stopped
  ffmpeg 2 ms after the device reported idle, with MA data still arriving. The MA source
  was not stalled or truncated.
- Only during send 3 was the MA entity `<HA_ENTITY_B>` playing (53.47 to 63.58,
  position 14 s at 56.07). The earlier live failures had Sendspin idle, so this overlap is
  not the only trigger. Whether it contributes is unproven.

The capture narrows the failure to the first roughly 70 ms of esphomed's stream and shows it is
intermittent with identical input. Without the HA-to-device bytes it does not name the
failing line.

## <BRIDGE_A> capture (02:49:25 to 02:50:55 UTC)

The owner ran `talosctl pcap` on <K8S_NODE_A>, interface `<BRIDGE_A>` (the macvlan master behind the HA pod's
IoT interface), and sent four announcements. File: `<PCAP_FILE_B>` (owner's home, not copied),
8670 packets, both directions. Parsed with an ad hoc Python reader in the session; no script
kept. The owner confirms all four played with no pink flash.

| Send | Device GET (UTC) | Body, audio | Download | Device close | 92-byte API message |
| --- | --- | --- | --- | --- | --- |
| 1 | 02:49:43.614 | 358,688 B, 3.74 s | 178 ms | FIN 6 ms after HA's FIN | GET + 4.49 s |
| 2 | 02:50:18.308 | 383,766 B, 4.00 s | 244 ms | FIN 1 ms after | GET + 4.36 s |
| 3 | 02:50:34.776 | 311,040 B, 3.24 s | 179 ms | FIN 4 ms after | GET + 3.61 s |
| 4 | 02:50:48.747 | 268,408 B, 2.80 s | 167 ms | FIN 3 ms after | GET + 3.06 s |

- Each response is HA's ffmpeg proxy (`/api/esphome/ffmpeg_proxy/…wav`): chunked, complete,
  ending in `0\r\n\r\n`. The WAV is 48 kHz mono 16-bit with RIFF and data sizes `0xFFFFFFFF`
  and a 26-byte LIST chunk after `fmt `. Chunk sizes vary (2048, 920, 460 and others); sends
  1 and 3 start with a 78-byte chunk holding only the WAV header.
- The device read every response to the end and closed with FIN. Closing a socket with unread
  data sends RST, so esphomed did not stop mid-stream in any of the four.
- Port 6053 is Noise-encrypted, but message sizes show the outcome. The device sent exactly
  four 92-byte messages, one per send, each 0.26 to 0.75 s after that send's audio would have
  ended. Reading them as the end-of-playback report is an inference from timing; a failed send
  would report within about 0.2 s of its GET.
- After the capture the device status reads `success` at 02:51:16, a fifth send after the
  capture stopped. `libreecho-waked` logged a playback start for each of the five sends.
- Host replay of each captured body with its real chunk sizes through
  `EsphomedPlaybackRepro/repro`: reads cut at the captured segment ends or at 10 ms arrival
  windows pass for all four. Reads cut at every 1448-byte segment make send 4 fail at
  `esphome_playback.c:91` (a read ends after the `\r` of a chunk-size line); the other three
  pass. HA's real byte stream can therefore hit the `dechunk()` defect when reads land on
  segment boundaries. The device's reads did not hit it in this capture.

The capture caught no failure, so it does not name the failing line.

## Next measurement (needs approval)

Two options settle the failing line:

1. A packet capture of one failing send on `<BRIDGE_A>` of the node that runs the HA pod, filtered
   afterwards to <DEVICE_IP_A>. No device write. Run once (see <BRIDGE_A> capture); all four sends
   played, so it needs a repeat that catches a failure.
2. A debug esphomed that logs the failing line and the last bytes read, installed on the
   device for one test. This is a device write and a service restart.

## Separate findings

- `sendspind` progress timeout is 20 ms (`engine_sink_session.h:71`). The engine services the
  sink at period boundaries (`audio_engine.c:1556`) and also while the period drains
  (`sendspin_service_until_writable`, `:166-203`); a host run shows the drain servicing
  works on the Lidar ring (`../sendspin-silence/notes.md`). The `err=11` re-arm in the log
  is a PROGRESS timeout whose cause on the device is open.
- The "Failed to send audio chunk" lines come from the SDK when the 4096-frame sink refuses
  an offer (`audio_sink.c:978-979`, `engine_sink.cpp:504-533`). After the 02:26 restart,
  Sendspin music is silent on this unit while they flood the log, so they are not proven
  harmless here. That investigation is in `../sendspin-silence/notes.md`; it is independent
  of the announcement failure.
