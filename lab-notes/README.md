# Experiments

This directory is the lab notebook of the Lidar port. It records what was done, in
the order it was done, with the evidence for each step. This is not a tutorial: the
procedure for installing LibreEcho on an Echo Plus 2nd Gen lives in the LibreEcho
repositories, not here. [`../PLAN.md`](../PLAN.md) is the plan the phases follow, and
[`../README.md`](../README.md) explains the port as a whole.

## How to read it

Work is organised as phases under `experiments/phase-XX/`. Most phase directories hold
a `notes.md` (the running record) plus logs, scripts, image manifests, and hardware
captures from that phase. Several phases also have a `README.md` that indexes the
directory. The notes are dated and were written while the work ran, so later
sections supersede earlier ones where a decision changed. Hardware sessions are named
`hw-YYYYMMDD`; the Phase 6 session numbers its steps and keeps one `stepNN-name/`
directory per step.

Evidence comes in four kinds, which PLAN.md keeps separate. Host evidence is a test
or build run on the workstation and says nothing about the device. CI evidence is a
pass in a repository workflow. Image evidence is a verifier checking a built boot
image. Hardware evidence is a capture or observation on the real Echo Plus 2nd Gen.
A hardware claim needs hardware evidence; nothing else counts.

## What is not here

The notes mention workspace paths such as `dumps/`, `artifacts/`, `repos/`,
`reference/` and `mtkclient/`. These are locations in the private lab workspace:
device dumps, built images, clones of the LibreEcho repositories, third-party
reference material, and the mtkclient checkout. Their contents are not part of this
public archive, so links into them do not resolve. Tokens such as `<SERIAL_A>` are
redactions of identifiers; `../SCRUB.md` explains what was removed and what was kept.

## Phase record

| Phase | Goal | Outcome | Closed | Main record |
|---|---|---|---|---|
| 0 | Experimental workspace | Repos cloned, branches created, tools recorded | 2026-11-10 | [notes.md](phase-00/notes.md) |
| 1 | Read-only boot-chain inventory | Stock boot chain read live from the device; backups and manifest recorded | 2026-11-10 | [notes.md](phase-01/notes.md) |
| 2 | Boot-chain construction and restore tooling | Kaeru stage, Koboreru image and restore tool built and host-checked; no device write | 2026-11-10 | [notes.md](phase-02/notes.md) |
| 3 | Owner access and fastboot | Restore drill passed, owner-access chain installed, Kaeru fastboot proven on the unit | 2026-11-15 | [notes.md](phase-03/notes.md) |
| 4 | Kernel and DTB bring-up | 6.1 ARM64 kernel boots from a slot with a root shell over USB ACM; peripherals probe | 2026-11-17 | [notes.md](phase-04/notes.md) |
| 5 | Platform, install, recovery, OTA | Platform profile built; install, A/B fallback, reboot to fastboot, OTA and reinstall all passed on hardware | 2026-11-21 | [README.md](phase-05/README.md) |
| 6 | Hardware and core feature bring-up | 6.18 kernel rebased and rerun; Wi-Fi, Bluetooth, audio, mics, buttons, LEDs, voice, EFR32, and the feature sweep all passed on hardware; lab OTAs up to v0.2.28 | 2026-11-22 | [hw-20261121/README.md](phase-06/hw-20261121/README.md) |
| 7 | Product integration and production tooling | Rebase of Platform, UI and kernel onto upstream 0.14.6 / 6.18 LTS done in branches; artifact cleanup; Sendspin silence root-caused and fixed; v0.2.34 installed and device-confirmed (installer gate not passed), owner reports it works; announce-bug investigation still open | in progress, 2026-11-23 | [phase-07/sendspin-silence/](phase-07/sendspin-silence/), [phase-07/README.md](phase-07/README.md) |
| 8 | Validation and PR preparation | Not started | - | - |

Phase status and gate wording in `../PLAN.md` are authoritative if this table and the
plan ever differ.
