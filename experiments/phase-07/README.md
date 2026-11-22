# Phase 7: product integration and production tooling

Phase 7 prepares the port for the Phase 8 PR stack. The Lidar kernel, LibreEcho-Platform
and LibreEcho-UI have been rebased onto their current upstream bases (6.18 LTS and
0.14.6) in new local branches, with the work split into generic fixes and Lidar
commits, and the old experiment branches preserved as `archive/...` tags. Superseded
build outputs under `artifacts/` were cleaned after owner approval. Two
investigations (the pink-LED announce bug and silent Sendspin music) are still open.
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
| `sendspin-silence/` | Investigation of silent Sendspin music; cause open |
| `../phase-07-prep/` | Prep notes from the earlier session (kernel fixes, ALS fix, UI API and daemon fixes, v0.2.26 rebuild) |
