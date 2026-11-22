# Phase 6: hardware and core feature bring-up

Phase 6 moved the port onto the 6.18 LTS kernel and brought up the hardware features
listed in PLAN.md Phase 6. The rerun of the Phase 4/5 kernel-dependent checks (slot boot, ACM
shell, pstore, reboot to fastboot, A/B fallback, OTA) passed on the unit, then the
phase ported the MT7668 Wi-Fi driver and the audio drivers, validated networking, the
UI, audio playback, all 7 microphones, the assistant and wake word daemons, buttons,
LEDs, the privacy latch, recovery entry, updates over Wi-Fi, and the EFR32
Zigbee/Thread radio. It ended with the full feature sweep (step 29) and a series of
lab OTA releases up to v0.2.28 that carried the fixes found along the way. The gate
passed on 2026-11-22.

This directory has no single running log. The hardware session log is
`hw-20261121/README.md`; the development-OTA-over-Wi-Fi runs are recorded in
`wifi-dev-updates/README.md`.

| Path | Content |
|---|---|
| `hw-20261121/` | The 2026-11-21/22 hardware session: step-by-step log in `README.md`, per-step logs and results in `stepNN-*/` directories |
| `wifi-dev-updates/` | Development updates over Wi-Fi: the supported procedure and both passing runs |
| `research/` | Pre-work research: the Platform contract and a map of the reference material |
| `physical-session.md` | What needs the owner present, and in what order |
| `components.md` | Host builds of the UI bundle and reused components, with hashes |
| `build_components.sh`, `build_images.sh` | Component and boot image build scripts |
| `fetch_system_a.sh`, `pull_system_a.sh` | Read-only pulls of Wi-Fi firmware and calibration data from `system_a` |
| `adb.sh` | Read-only adb capture helper used before the `bin/` wrappers existed |
| `ota/` | `build_ota.sh`, the lab OTA bundle builder |

Private-workspace paths (`artifacts/`, `dumps/`, `reference/`, `repos/`) appear in
the notes; their contents are not part of this archive.
