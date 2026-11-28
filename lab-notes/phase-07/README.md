# Phase 7: product integration and production tooling

Phase 7 prepares the port for the Phase 8 PR stack. I rebased the Lidar kernel,
LibreEcho-Platform and LibreEcho-UI onto their current upstream bases (6.18 LTS and
0.14.6) in new local branches, with the work split into generic fixes and Lidar
commits, and the old experiment branches preserved as `archive/...` tags. I cleaned the
superseded build outputs under `artifacts/` after I confirmed the list. The Sendspin
silence is fixed. v0.2.42 failed its confirm and rolled back, v0.2.43 was installed and
confirmed on slot a, v0.2.44 exists on the host only, and the lab series ran through
v0.2.45 to v0.2.68. v0.2.68 was built on 2026-11-28, installed on the development unit
and booted (owner report).
I fixed the announce bug (pink LED, then no audio) on the host: the 0.14.6 branch's
`unframe()` state machine replaced the defective `dechunk()`, and I fixed the remaining
chunk-extension defect in UI `0cc5507` with regression tests. The fix ships in v0.2.68;
no announcement has been sent on that image, so the on-device check is still pending.
The files below hold the phase's results and evidence. PLAN.md Phase 7 lists the
remaining unchecked items: schema generalization (open only for a hosted CI run), the
production scripts' hardware run, and the radio service, now on `feat/lidar-radio`.

| Path | Content |
|---|---|
| `announce-bug/` | Investigation and host fix of the announce bug (pink LED, then no audio); the fix ships in v0.2.68, on-device check still open |
| `sendspin-silence/` | Investigation and fix of silent Sendspin music; see also `sendspin-silence/versions.md` for the v0.2.29-v0.2.34 OTA series |
| `thread-service.md` | Thread and Zigbee host work; packaged in v0.2.68 (image evidence only), no device run |
| `hw-2026-11-26/` | Read-only device checks: identity, slots and OTA state, expdb magic and guard verdict, partition table |
| `hosted-ci.md` | Hosted CI state: branch heads, what each fork's CI runs, the results on the 2026-11-28 pushes, and the fork settings still open |
| `mute-lamp.md` | Why the mute-button lamp stays dark after a software mute, and my decision to keep that behavior |
| `AlsFix.md`, `KernelFixes.md`, `UiApiFixes.md`, `UiDaemonFixes.md`, `RebuildV26.md` | Prep notes from the earlier session (kernel fixes, ALS fix, UI API and daemon fixes, v0.2.26 rebuild) |
