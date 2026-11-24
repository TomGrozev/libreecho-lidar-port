# Lidar preparation command

Host-only implementation of the reviewed preparation flow for a stock Echo Plus
2nd Gen (Lidar, MT8167).  It replaces the experimental mtkclient and manual
reference steps (`PLAN.md:796-805`) with one staged command.  Everything here
was tested against fakes and a dry-run adapter; no device was touched.

## Entry points

`private/forks/LibreEcho-Platform/tools/mt8167-arm64/prepare/`

| Path | Purpose |
| --- | --- |
| `lidar_prepare.py` | stages, GPT/geometry checks, chain composition, CLI |
| `mtk_adapter.py` | the only mtkclient seam (`printgpt`, `r`, `ro`, `w`, `wo`) |
| `test_lidar_prepare.py` | 31 host tests with an in-memory fake device |
| `README.md` | usage and safety summary |

Reused instead of copied: `install/lidar_backup_set.py` (area set, manifest,
verification), `install/expdb_guard.py` (`check_expdb_prefix`), and
`libreecho_platform_targets.py` (partition and product tables).

## Stages

1. `identify` - BROM `printgpt`; require hwcode 0x8167, 7650410496-byte user
   area, 2 MiB boot area, 512-byte sectors, a GPT whose primary and backup
   entries agree, and the reviewed partition offsets and sizes.
2. `backup` - read every backup-set area twice, write the first read, require
   the second to hash identically, then write and verify the manifest.  Never
   overwrites an existing backup.
3. `drill` - re-read each area, compare with the backup, then rewrite the same
   bytes and verify the readback in the phase-2 order.  BOOT0 body is written
   before sector 0 (last); BOOT1 is read and verified but never written.
4. `stock-boot` - operator gate: power-cycle to a normal stock boot, then a
   fresh BROM entry.  Writes a signed report.
5. `install` - take the signed preloader from the verified backup's `boot0`,
   require its digest to equal the reviewed 2019 image (`fb987ad9...`,
   `PLAN.md:65-80`), refuse an installed or broken expdb before writing,
   write Kaeru to expdb, pass a fresh 16-byte `check_expdb_prefix` read before
   tee1, write Koboreru over the stock tee1 tail, then write BOOT0 body and
   sector 0 last.  BOOT1 must read back unchanged.
6. `confirm` - fastboot `getvar product`; require `LIDAR`.

`run` chains all six from one session directory.  `--dry-run` prints every
mtkclient and fastboot command, including second reads and readbacks, without
opening USB.

## Chain layout and sources

- expdb: Kaeru LK stage padded with zeros to 0x40000.
- tee1: Koboreru ATF prefix + stock tee1 tail from the verified backup.
- BOOT0 area 1: backup preloader; bytes 512..end first, sector 0 last.
- Layout: `private/lab/phase-03/manifests/install.json:12-59`;
  drill order and notes: `private/lab/phase-03/notes.md:54-126`.
- Live GPT offsets and geometry: `private/lab/phase-01/brom-printgpt.log:106-142`.
- Boot-chain safety rules: `PLAN.md:114-124`.
- Owner decisions: `PLAN.md:832-841`; final user flow: `PLAN.md:851-860`.
- expdb prefix rule: `install/expdb_guard.py`.

## Hardware steps (each needs separate owner approval)

1. Enter BROM; run `identify` and review the identity event.
2. Run `backup` to a fresh directory; review the manifest and second-read
   verification.
3. Run `drill --yes`; it rewrites only identical bytes, BOOT0 sector 0 last,
   and never BOOT1.
4. Remove power, let the unit boot stock normally, remove power, then re-enter
   BROM; record `stock-boot`.
5. From a fresh mtkclient work directory, run `install --yes`; review the
   expdb readback, the fresh generation check, tee1, BOOT0, and the unchanged
   BOOT1.
6. `confirm` over fastboot: product must be `LIDAR`.

## Unverified

- No stage ran against hardware; all command syntax is checked only against
  the reviewed mtkclient invocation and a recording runner.
- The dry run uses the checked-in Kaeru and Koboreru images
  (`private/forks/kaeru/lidar-kaeru.bin`,
  `private/artifacts/phase-02/koboreru/tee-payload-lidar.img`).  It does not
  prove the real backup's boot0 is the reviewed 2019 preloader; the command
  refuses if it is not.
- mtkclient's `r boot0 --parttype boot1` slicing is assumed from the adapter
  contract (`offset + size` from area 1); the fake enforces the same contract.
- Fastboot product parsing and the two power-cycle gate are untested on the
  unit.
- The same-byte drill's risk (a power loss mid-write) is unchanged by this
  tool and still needs the owner's approval.

The dry-run transcript was a session output and is not published.
