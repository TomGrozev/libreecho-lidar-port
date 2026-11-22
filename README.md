# LibreEcho on the Echo Plus 2nd Gen (Lidar): port archive

This repository is the plan and evidence archive of the port of
[LibreEcho](https://github.com/aslater3/LibreEcho) to the Echo Plus 2nd Gen. LibreEcho is
free firmware that replaces Amazon's software on Echo speakers. The device codename is
Lidar and its system-on-chip is a MediaTek MT8167. The work ran in a private lab workspace
against one development unit. This archive keeps the phase plan, the experiment notes and
the measurement results, with device and owner identifiers replaced by placeholders (see
[SCRUB.md](SCRUB.md)). It holds text only.

## Status

As of 2026-11-22, Phases 0 to 6 of [PLAN.md](PLAN.md) are complete and their gates
passed on the device. Phase 7 (product integration and production tooling) is in
progress: the Lidar changes are rebased onto current upstream branches. Phase 8
(validation and PR preparation) has not started. The port is experimental and not
released. Hardware results come from one development unit, and the upstream product does
not yet ship a Lidar target. Nothing here is a support claim.

## What works on hardware

Each row links to the evidence directory. "Works" means the feature was demonstrated on
the development unit. It does not mean released or supported.

| Area | State | Evidence |
| --- | --- | --- |
| Boot chain (owner access) | Owner-access chain built from the reference kit's hardware-proven Kaeru and Koboreru stages, installed after a stock backup, a restore drill and readback checks. BOOT1 was never written. The same chain built from source is not yet hardware-proven. | [`experiments/phase-03/`](experiments/phase-03/) |
| Kernel | Source-built ARM64 Linux 6.18.64 boots from a boot slot on the device. | [`experiments/phase-06/hw-20261121/`](experiments/phase-06/hw-20261121/) (steps 3-9) |
| Wi-Fi | MT7668 SDIO driver ported to 6.18 from lidar-mainline's port of Amazon's GPL gen4 driver. DHCP, DNS, link flap and supplicant restart all pass. | [`experiments/phase-06/hw-20261121/step11-net/`](experiments/phase-06/hw-20261121/step11-net/) |
| Bluetooth | Mainline `btmtksdio`; owner phone paired, A2DP and AVRCP work. | [`experiments/phase-06/hw-20261121/step26-bt/`](experiments/phase-06/hw-20261121/step26-bt/) |
| Audio playback | Two-way speaker through the TLV320 AIC32x4, with Amazon's crossover biquads; volume cues and music heard on the product path. | [`experiments/phase-06/hw-20261121/step16-audio/`](experiments/phase-06/hw-20261121/step16-audio/), [`step21-cue/`](experiments/phase-06/hw-20261121/step21-cue/), [`step22-drain/`](experiments/phase-06/hw-20261121/step22-drain/) |
| Microphones | All 7 microphones capture; each lane verified by a per-mic rub test. | [`experiments/phase-06/hw-20261121/step17-mics/`](experiments/phase-06/hw-20261121/step17-mics/) |
| Buttons and LEDs | Volume, mute and Action keys, the 36-channel LED ring, volume meter, mute ring and boot animation. | [`experiments/phase-06/hw-20261121/step18-buttons/`](experiments/phase-06/hw-20261121/step18-buttons/), [`step19-flash/`](experiments/phase-06/hw-20261121/step19-flash/) |
| Privacy latch | While latched, capture is exactly zero on every lane and the ring shows a steady red; capture returns on release. | [`experiments/phase-06/hw-20261121/step17-mics/`](experiments/phase-06/hw-20261121/step17-mics/), [`step19-flash/`](experiments/phase-06/hw-20261121/step19-flash/) |
| UI and control API | Web setup page, bootstrap and authenticated API pass; the LibreEcho feature sweep passed with classified gaps. | [`experiments/phase-06/hw-20261121/step13-ui/`](experiments/phase-06/hw-20261121/step13-ui/), [`step29-features/`](experiments/phase-06/hw-20261121/step29-features/) |
| OTA, A/B updates | True A/B with LK tries fallback; installs, health confirms and a forced-rollback test all passed, including over Wi-Fi without USB. | [`experiments/phase-05/`](experiments/phase-05/), [`experiments/phase-06/wifi-dev-updates/`](experiments/phase-06/wifi-dev-updates/) |
| Voice | Wake word and Home Assistant satellite voice commands work; speech-to-text runs on the device. The online assistant reply needs internet and was not tested. | [`experiments/phase-06/hw-20261121/step24-voice/`](experiments/phase-06/hw-20261121/step24-voice/), [`step29-features/`](experiments/phase-06/hw-20261121/step29-features/) |
| EFR32 radio (Zigbee/Thread) | Gecko bootloader answered; the OpenThread RCP and the stock Zigbee NCP each ran on the radio. The permanent Thread service is deferred to Phase 7. | [`experiments/phase-06/hw-20261121/step25-efr32/`](experiments/phase-06/hw-20261121/step25-efr32/) |

## Known gaps

- Phase 7 is not finished and Phase 8 has not started: there is no production installer
  path yet and no upstream PR.
- The stock boot-chain restore path after Kaeru installation needs a separately reviewed
  BROM procedure; never restore `expdb` alone ([PLAN.md](PLAN.md), "Boot-chain safety").
- Sendspin music playback is silent on Lidar. The cause is still under investigation
  ([`experiments/phase-07/sendspin-silence/`](experiments/phase-07/sendspin-silence/)).
- A Home Assistant announcement can flash the ring pink and play no audio; sending it again
  plays it. The investigation is open
  ([`experiments/phase-07/announce-bug/`](experiments/phase-07/announce-bug/)).
- The test network has no internet access, so internet features (online assistant reply,
  radio, news, NTP) were not tested. They are not counted as failures.
- The board has no real-time clock, so the clock restarts at 1970 after a power cut.
- USB storage is not available (the port works only as a USB device, not as a host) and
  Spotify Connect has no daemon in any LibreEcho image.

## Where to start

Read in this order:

1. This page, for the result, the status and the known gaps.
2. [`experiments/README.md`](experiments/README.md), for the phase layout and the evidence
   rules.
3. [PLAN.md](PLAN.md), the authoritative record of scope, phases, gates and decisions.
4. The phase README under `experiments/phase-XX/` for the area you care about.

The repository holds:

- `PLAN.md`, the plan and decision record.
- `experiments/`, the phase records: notes, logs, results and the scripts used.
- `GLOSSARY.md`, the project terms.
- `SCRUB.md`, the redaction record, and `NOTICE.md`, the third-party licence notes.
- `AGENTS.md` and `PRESERVATION.md`, the working contract and its safety boundaries.
- `LICENSES/`, the full licence texts.

[`experiments/README.md`](experiments/README.md) explains why paths such as `dumps/`,
`artifacts/`, `repos/` and `reference/` point to lab workspace material that is
deliberately absent here.

## How this port was worked

The owner ran the port with AI coding agents under a written contract,
[AGENTS.md](AGENTS.md). The contract's "Main" is the agent session that plans and
coordinates; the other agents execute phases and report evidence back. Every hardware
write and reboot needed separate approval from the owner, and agent results marked
`[INFERENCE]` are conclusions the agent drew rather than recorded measurements. The
contract text is kept as a record of how the work was done.

## Safety

Porting an Echo device means writing to its boot chain. A bad write to BOOT0, BOOT1,
`expdb` or the tee partitions can brick the unit, and on this device there is no UART to
recover with. The boot-chain rules follow from that: read-only inspection first, a
verified stock backup and restore drill before the first write, readback verification
after every write, and a separate approval for each hardware write or reboot. See
[PRESERVATION.md](PRESERVATION.md) for the purpose and the boundaries, and
[PLAN.md](PLAN.md), "Boot-chain safety", for the rules.

## Related repositories

- Upstream product: [aslater3/LibreEcho](https://github.com/aslater3/LibreEcho).
- The owner's forks hold the Lidar branches:
  [TomGrozev/LibreEcho-Platform](https://github.com/TomGrozev/LibreEcho-Platform),
  [TomGrozev/LibreEcho-UI](https://github.com/TomGrozev/LibreEcho-UI),
  [TomGrozev/LibreEcho-Linux](https://github.com/TomGrozev/LibreEcho-Linux),
  [TomGrozev/kaeru](https://github.com/TomGrozev/kaeru),
  [TomGrozev/amonet-koboreru](https://github.com/TomGrozev/amonet-koboreru) and
  [TomGrozev/u-boot](https://github.com/TomGrozev/u-boot).
- The feature branch is `feature/lidar-support`; the U-Boot second-stage fastboot tool is
  on branch `lidar-fastboot-stage2`. None of these branches is merged upstream.

## Privacy and redaction

Device and owner identifiers in the source workspace were replaced with stable
placeholders before this archive was created, and the result was scanned to zero hits.
[SCRUB.md](SCRUB.md) records what was removed, what was kept on purpose, and the full
placeholder table.

## License

Documentation, notes and logs are licensed under CC BY 4.0. Scripts and source files
written for this port are licensed under MIT. See [LICENSE](LICENSE),
[NOTICE.md](NOTICE.md) for third-party material, and the `LICENSES/` directory for the
full texts.
