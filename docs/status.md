# Project status

This is the status of the Lidar port on 2026-11-28. "Works" means I demonstrated it on the
one development unit. It is not a support claim and not a release.

The phases and their gates are in [the port plan](plan.md). Each phase record under
[lab-notes/](../lab-notes/README.md) holds the commands, logs and outcomes behind the
statements below.

## Phase gates

| Phase | Name | State | Gate evidence |
| --- | --- | --- | --- |
| 0 | Experimental workspace | done, 2026-11-10 | [notes](../lab-notes/phase-00/notes.md) |
| 1 | Read-only boot-chain inventory | done, 2026-11-10 | [notes](../lab-notes/phase-01/notes.md) |
| 2 | Boot-chain construction and restore tooling | done, 2026-11-10 | [notes](../lab-notes/phase-02/notes.md) |
| 3 | Boot chain and fastboot | done, 2026-11-15 | [notes](../lab-notes/phase-03/notes.md) |
| 4 | Kernel and DTB bring-up | done, 2026-11-17 | [README](../lab-notes/phase-04/README.md) |
| 5 | Platform, install, recovery, OTA | done, 2026-11-21 | [README](../lab-notes/phase-05/README.md) |
| 6 | Hardware and core feature bring-up | done, 2026-11-22 | [README](../lab-notes/phase-06/hw-20261121/README.md) |
| 7 | Product integration and production tooling | in progress | [README](../lab-notes/phase-07/README.md) |
| 8 | Validation and PR preparation | in progress | [notes](../lab-notes/phase-08/wifi-slowdown-20261126/notes.md) |

## What works on hardware

| Area | Status | Evidence |
| --- | --- | --- |
| Custom boot chain | I installed the chain from the reference kit's hardware-proven Kaeru and Koboreru stages, after a stock backup, restore drill and readback checks; I never wrote BOOT1. The same chain built from source is not yet hardware-proven. | [phase-03](../lab-notes/phase-03/) |
| Kernel | Source-built ARM64 kernel (6.18 LTS base, `fix/stable-6.18.64` fixes) boots from a boot slot. | [step 3-9](../lab-notes/phase-06/hw-20261121/) |
| Wi-Fi | MT7668 SDIO driver ported to 6.18; DHCP, DNS, link flap and supplicant restart pass. | [step11-net](../lab-notes/phase-06/hw-20261121/step11-net/) |
| Bluetooth | Mainline `btmtksdio`; my phone paired, A2DP and AVRCP worked. | [step26-bt](../lab-notes/phase-06/hw-20261121/step26-bt/) |
| Audio playback | Two-way speaker through the TLV320 AIC32x4 with Amazon's crossover biquads; volume cues and music heard on the product path. | [step16-audio](../lab-notes/phase-06/hw-20261121/step16-audio/), [step21-cue](../lab-notes/phase-06/hw-20261121/step21-cue/), [step22-drain](../lab-notes/phase-06/hw-20261121/step22-drain/) |
| Microphones | All 7 microphones capture; each lane verified by a per-mic rub test. | [step17-mics](../lab-notes/phase-06/hw-20261121/step17-mics/) |
| Buttons and LEDs | Volume, mute and Action keys; 36-channel LED ring, volume meter, mute ring, boot animation. | [step18-buttons](../lab-notes/phase-06/hw-20261121/step18-buttons/), [step19-flash](../lab-notes/phase-06/hw-20261121/step19-flash/) |
| Privacy latch | While latched, capture is exactly zero on every lane and the ring shows steady red; capture returns on release. | [step17-mics](../lab-notes/phase-06/hw-20261121/step17-mics/), [step19-flash](../lab-notes/phase-06/hw-20261121/step19-flash/) |
| UI and control API | Web setup page, bootstrap and authenticated API pass; the LibreEcho feature sweep passed with classified gaps. | [step13-ui](../lab-notes/phase-06/hw-20261121/step13-ui/), [step29-features](../lab-notes/phase-06/hw-20261121/step29-features/) |
| OTA, A/B updates | True A/B with LK tries fallback; install, health confirm and forced rollback pass, including over Wi-Fi without USB. | [phase-05](../lab-notes/phase-05/), [wifi-dev-updates](../lab-notes/phase-06/wifi-dev-updates/) |
| Voice | Wake word and Home Assistant satellite voice commands work; speech-to-text runs on the device. The online assistant reply needs internet and was not tested. | [step24-voice](../lab-notes/phase-06/hw-20261121/step24-voice/), [step29-features](../lab-notes/phase-06/hw-20261121/step29-features/) |
| EFR32 radio (Zigbee/Thread) | Gecko bootloader answered; OpenThread RCP and stock Zigbee NCP each ran. The permanent Thread service is open. | [step25-efr32](../lab-notes/phase-06/hw-20261121/step25-efr32/) |

## What does not work, or is unproven

- A fresh unit has not gone through the install guide end to end. The preparation command
  `lidar_prepare.py` has passed host tests and dry runs only
  ([prep-command](../lab-notes/phase-07/prep-command.md)).
- The boot chain built from source is not hardware-proven. The earlier normal-boot failure was
  inconclusive ([phase-03 notes](../lab-notes/phase-03/notes.md), "Limitation").
- The expdb guard's refuse path has not fired on hardware
  ([expdb-guard](../lab-notes/phase-07/expdb-guard.md)).
- A build from a clean clone has host evidence only; see [BUILDING.md](../BUILDING.md).
- Hosted CI has not run on any fork: Actions is not enabled on my forks
  ([hosted-ci](../lab-notes/phase-07/hosted-ci.md)).
- The announce bug (pink LED, then no audio) is fixed on the host; the on-device check is
  pending ([announce-bug](../lab-notes/phase-07/announce-bug/notes.md)).
- A software microphone mute turns the ring red but leaves the mute-button lamp dark; only
  the hardware latch lights it. I decided to keep this behavior
  ([mute-lamp](../lab-notes/phase-07/mute-lamp.md)).
- Internet features (online assistant reply, radio, news, NTP) were not tested because the
  test network had no WAN ([feature sweep](../lab-notes/phase-06/hw-20261121/step29-features/result.md)).
- Spotify Connect is not in the image: no Spotify daemon was packaged
  ([feature sweep](../lab-notes/phase-06/hw-20261121/step29-features/result.md)).
- The board has no working RTC, so the clock falls back to retrying NTP
  ([feature sweep](../lab-notes/phase-06/hw-20261121/step29-features/result.md)).
- The unit does not roam between access points; a weak BSS made everything 10 to 18 times
  slower ([Wi-Fi slowdown](../lab-notes/phase-08/wifi-slowdown-20261126/notes.md)).
- No upstream PR is open; the PR bodies are drafted and nothing is pushed
  ([phase-07](../lab-notes/phase-07/README.md)).

## Evidence kinds

I keep four kinds of evidence apart, and a hardware claim needs the last one:

- Host: a test or build on my workstation.
- CI: a pass in a repository workflow.
- Image: a verifier checking a built image.
- Hardware: a capture or observation on the Echo Plus 2nd Gen itself.

The install path is in [install-new-lidar.md](install-new-lidar.md); the safety rules are in
[boot-chain-safety.md](boot-chain-safety.md).
