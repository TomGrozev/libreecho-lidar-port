# LibreEcho feature inventory for the Lidar feature sweep

Source: `repos/LibreEcho-UI/README.md` (state-at-a-glance table, implemented and
target-dependent lists), `docs/ARCHITECTURE.md`, `docs/HOME_ASSISTANT_VOICE.md`,
and `web/openapi.json` (69 documented paths). Device requirement names the image
piece the feature needs on the target.

## Platform surfaces

| Feature | Source state | Device requirement |
|---|---|---|
| Web UI and HTTP API (`libreecho-web`) | Implemented | `libreecho-web`, web root, config and users files |
| Mock backend (`--backend mock`) | Implemented | Host only, never device evidence |
| Linux telemetry (`/proc`, `/sys`, storage, network) | Implemented | Linux backend in the image |
| Authentication (bootstrap, login, bearer, CSRF, Origin, rate limit) | Implemented | users file, writable config path |
| Companion daemon adapters (AF_UNIX, newline JSON) | Implemented | `networkd`, `audiod`, `ledd`, `waked`, `btd`, `agentd`, `lived`, `logd` |
| Logs, diagnostics, bounded events | Implemented | `logd`, `/var/log/libreecho`, kernel log access |
| Signed OTA status and apply | Implemented at API boundary | `libreecho-bootctl`, `libreecho-update`, `libreecho-update-fetch`, signing key policy |
| First-boot setup, local firmware import, `wlan0` registration | Implemented | vendor assets, setup state files |
| Guarded reboot, shutdown, factory reset | Implemented | init and boot control helpers |

## Audio and voice

| Feature | Source state | Device requirement |
|---|---|---|
| Volume, microphone gain and mute, announcements, test tone | Implemented through service boundaries | ALSA devices and `audiod` |
| Microphone listing, beams, baby monitor stream | Implemented | Radar capture (`micd`, `tinycap`), microphone calibration |
| Local voice pipeline (wake, STT, assistant, TTS) | Implemented | `waked`, `sttd`, `agentd`, `ttsd`, feature payloads |
| Custom Wyoming Whisper/Piper clients | Implemented | network reachability to my endpoints |
| Home Assistant ESPHome mode | Implemented | `libreecho-esphomed`, stable MAC, TCP 6053, Noise key |
| GPT-Live (`lived`) | Implemented, disarmed by default | `lived` payload and transport |
| Voice-turn history and latency telemetry | Implemented | `agentd` history store |

## Lighting, input, time

| Feature | Source state | Device requirement |
|---|---|---|
| LED colour, brightness, profiles, test, startup, visualizer | Implemented and adapter-wired | `ledd`, sysfs LED or IS31FL3236 I2C path |
| Idle mode, sleep light, night mode | Implemented | `ledd` |
| Physical buttons, cues, mappings | Implemented | `buttond`, GPIO input, privacy node |
| Timers and alarms | Implemented | `timerd`, `timed` |
| Timezone and NTP | Implemented | `timed`, RTC or NTP reachability |

## Network, discovery, media sources

| Feature | Source state | Device requirement |
|---|---|---|
| Wi-Fi scan, connect, disconnect, liveness, recovery AP | Implemented and adapter-wired | `networkd`, `wpa_supplicant`, DHCP, WLAN driver |
| Hostname, local API bind, MAC overrides | Implemented | `networkd` |
| Internet radio (MP3/AAC/HLS, optional Ogg Opus and TLS) | Implemented | `radiod`, stream reachability, optional Opus/TLS libs |
| Spotify Connect status | Implemented | Spotify daemon in the image |
| Sendspin (Music Assistant multiroom) | Implemented | Sendspin player in the image, mDNS |
| AirPlay receiver and its LED/visualizer bridge | Implemented | `airplayd`, `shairport-sync`, `mdnsd`, port 7000 |
| USB storage listing and playback | Implemented | USB host mass-storage mount |
| LibreEcho News | Implemented | network fetch of the feed |

## Privacy and integrations

| Feature | Source state | Device requirement |
|---|---|---|
| Privacy settings and microphone mute gate | Implemented | privacy sysfs input plus `audiod` |
| Integrations bitmask (HA, REST, Spotify, Sendspin, radio and others) | Implemented | per-integration payloads |
| Wake word selection, sensitivity, reload | Implemented | `waked` with model payloads |
| Appearance (`ui_theme`, `color_mode`) | Implemented | none |
| Config export/import | Implemented | writable config path |

## Target-dependent gaps the README already names

Real audio output, Radar capture, Wi-Fi credential handoff, wake-word hardware,
physical button and mute integration, Bluetooth controller transport, kernel
diagnostics, static IPv4, SSH control, config restore, privilege dropping, and
OTA without the helper set. A host or API pass is never hardware evidence.
