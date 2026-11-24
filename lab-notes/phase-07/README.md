# Phase 7: product integration and production tooling

Phase 7 prepares the port for the Phase 8 PR stack. The Lidar kernel, LibreEcho-Platform
and LibreEcho-UI have been rebased onto their current upstream bases (6.18 LTS and
0.14.6) in new local branches, with the work split into generic fixes and Lidar
commits, and the old experiment branches preserved as `archive/...` tags. Superseded
build outputs under `artifacts/` were cleaned after owner approval. The Sendspin
silence is fixed; lab OTA v0.2.34 is installed and device-confirmed (the installer's
confirmation gate did not pass) and the owner reports it works. The
announce-bug investigation (pink LED, then no audio) is still open.
The files below record the rebase. PLAN.md Phase 7 lists the remaining unchecked items,
among them the target descriptor, schema generalization, production scripts and the
Thread service.

| Path | Content |
|---|---|
| `kernel-rebase.md` | Kernel rebase onto the 6.18 LTS: branches, ported commits, build and CI results |
| `platform-rebase.md` | LibreEcho-Platform rebase onto 0.14.6: commit classification, conflict resolutions, host CI suite results |
| `ui-rebase.md` | LibreEcho-UI rebase onto 0.14.6: generic and Lidar branches, test results, archive tags |
| `artifact-cleanup.md` | Owner-approved deletion of superseded build outputs, with size and hash lists |
| `artifact-cleanup-du.txt`, `artifact-cleanup-sha256.txt` | Size and hash evidence for the cleanup |
| `announce-bug/` | Investigation of the announce bug (pink LED, then no audio); cause narrowed, not fixed |
| `sendspin-silence/` | Investigation and fix of silent Sendspin music; see also `sendspin-silence/versions.md` for the v0.2.29-v0.2.34 OTA series |
| `mute-lamp.md` | Why the mute-button lamp stays dark after a software mute, and the owner's decision to keep that behavior |
| `../phase-07-prep/` | Prep notes from the earlier session (kernel fixes, ALS fix, UI API and daemon fixes, v0.2.26 rebuild) |
