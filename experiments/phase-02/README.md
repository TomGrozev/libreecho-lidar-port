# Phase 2: experimental boot-chain construction and restore tooling

Phase 2 built the experimental boot chain and the restore tooling on the host before
anything touched the device. The Kaeru stage got a new Lidar config and board, derived
from the stock lk_a. The MIT-licensed Koboreru source got a Lidar device definition,
derived from the 2019 replacement preloader, with patch sites and addresses taken from
the donor device image. The restore tool gained an mtkclient backend with exact
identity, size and hash checks, readback verification after each write, and atomic
manifests. It passed host tests against synthetic images and fault cases. No device was
written or booted; all evidence is host-side. `notes.md` is the full record, and its
"Gate status" section states the outcome.

| Path | Content |
|---|---|
| `notes.md` | Full phase record and gate status |
| `restore/` | The restore tool: `lidar_restore.py`, the `lidarrestore` driver, tests and usage README |
| `logs/` | Build logs for the Kaeru and Koboreru images and toolchain setup |

The Kaeru and Koboreru derivation records are in `notes.md`; the address
derivation for the Koboreru patch sites is in `notes.md` and cited from `PLAN.md`
Phase 2. Donor binaries and dumps stayed in the private workspace and are not part of
this archive.
