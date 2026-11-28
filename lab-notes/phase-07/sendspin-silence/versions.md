# Sendspin silence: lab OTA versions v0.2.29 to v0.2.34

What each lab OTA fixed on the way to a working Sendspin music path, with the evidence
for each build and install. The root-cause investigation log stays private; its result is
summarized here, and `deploy/notes.md` records the v0.2.29 outcome and the v0.2.30 rebuild.
Artifact trees live under
`artifacts/phase-07/` in the private workspace; the per-version install and poll logs are
private lab records.

## Root cause (fixed in this series)

`chain_output_latency_us()` returned -1 for `lidar_chain`, so the engine published
TIMING_INVALID on every progress reply (`finish_us` always 0). The Sendspin companion
refused to report played frames without a horizon, so the SDK never cleared
`initial_decode` and streamed 25 ms of priming silence forever. Full chain and fix:
`artifacts/phase-07/sendspin-silence-fix.txt`. Fix branch
`fix/sendspin-uncalibrated-horizon` (UI, commit `d63a58a`); `pump_feedback()` now reports
the played prefix with the local CLOCK_MONOTONIC sample time when no horizon exists.

## Versions

| Version | What it carried | Evidence |
| --- | --- | --- |
| v0.2.29 | First Sendspin fix trial (UI `d63a58a`) on the v0.2.28 image base. Install failed the confirm gate: the new `libreecho-reconcile-features` aborts all persisted features when topology reconcile fails, so airplay2 never became ready. Not deployed. | `deploy/notes.md`, "Confirm failure" and "Postmortem" (install PASS, confirm refused, slot b fallback) |
| v0.2.30 | Platform reconcile fix (`fix/reconcile-topology-nonfatal`, `07549ae3`) plus UI `715dd4f` (service wrappers, startup gate backs off for absent voice payloads and a disabled ESPHome integration). | `deploy/notes.md`, "Rebuild v0.2.30" and the v0.2.30 install notes; `artifacts/phase-07/ota-715dd4f/` |
| v0.2.31 | v0.2.30 plus the `load_image_target` lidar case and the EFR32-firmware-bearing build; superseded within the same session by later candidates. | `deploy/notes.md`; `artifacts/phase-07/ota-v0231/` |
| v0.2.32 | First full-image rebuild from the rebased trees (Platform `2278dedde`, UI `715dd4f`). Superseded: its OTA health probe did not require the Lidar Wi-Fi radio, so a slot could confirm with no `wlan0`. | `artifacts/phase-07/v0232/SUPERSEDED.txt`; `deploy/notes.md`, "Rebuild v0.2.30" |
| v0.2.33 | Platform `3fce9b077` adds the Wi-Fi-radio health probe; deploy candidate with the fix and the gate. Its UI startup gate predates the aggregated target-parser check and the final startup-gate fix. Install logs show the boot stuck in `boot-validating` with `startup-ready` missing and the degraded-start health path confirming the slot. | `artifacts/phase-07/v0233/SUPERSEDED.txt`, `verify-v0233.log` (15 PASS); the private install and poll logs record the boot stuck in `boot-validating` with `startup-ready` missing and the degraded-start confirm |
| v0.2.34 | Platform `57324285b` and UI `0d2285b` on `feature/lidar-support-0.14.6`: aggregated target-parser check (the MT8167 verifier rejects v0.2.30-style targets) and the UI startup-gate fix. Host verify: 17 PASS, 0 FAIL. Installed 2026-11-23: pushed, rebooted, back on slot a (19:04:35). The device confirmed the slot (19:04-19:11:22: `boot_state=confirmed`, `update_state=installed`, `startup_ready=yes`), but the installer's own gate never passed: the ledd hand-off marker did not appear in 7 min of polls, and the polls then stopped when the workspace move removed the adb wrapper and log dir mid-run, so the script reported FAIL at 19:14:37 (not confirmed within 10 min). Tom reports music plays over Sendspin. | `artifacts/phase-07/v0234/README.txt`, `verify-v0234.log`; the install and confirm logs, private |

My report that v0.2.34 works is my statement, not an instrumented
capture; the device logs prove the install and the boot confirm, and the installer gate
itself did not pass (see the v0.2.34 row).

## Superseded artifacts

`artifacts/phase-07/v0232/SUPERSEDED.txt` and `v0233/SUPERSEDED.txt` record why each tree
was replaced and forbid flashing them. v0.2.29 to v0.2.31 have no SUPERSEDED.txt; their
status is recorded in `deploy/notes.md`. The hand build and install scripts from this
series are gone; `tools/lab-build.py` is the builder now.
