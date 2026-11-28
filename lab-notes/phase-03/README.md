# Phase 3: Boot chain and fastboot

Phase 3 moved from host work to the device, one hardware session at a time, each approved
by me beforehand. The restore drill wrote each saved stock boot-chain image back to its
source partition, verified every readback, and confirmed a normal stock boot. I then
installed the custom boot chain in the order expdb, tee1, then BOOT0 area 1 from the 2019
preloader with sector 0 last. A later session replaced it with the kit's hardware-proven
reference chain, under a separate approval. I verified Kaeru fastboot on the unit
(`product: LIDAR`, `unlock_status: true`), repeated BROM and fastboot entry worked, and a
persistence retest proved that all three chain images survived a true power cycle. The
phase also surfaced an eMMC clean-shutdown issue that shaped later sessions. `notes.md`
is the full record.

| Path | Content |
|---|---|
| `notes.md` | Full phase record: sessions, decisions, the persistence retest, known limitations |
| `FASTBOOT.md` | Fastboot interface notes for the Kaeru chain |
| `enter_fastboot.py` | Helper to enter fastboot on the unit |
| `identity.json`, `offsets.json` | Device identity and partition offsets used by the plans |
| `manifests/` | The per-session plan manifests (drill, install, reference chain, kaeru fix) |
| `logs/` | Session journals, preflight and result reports, the 2026-11-15 fastboot transcript, and the `persistence-retest-20261115/` capture |

The stock boot-chain backups this phase verified live in the private workspace under
`dumps/`.
