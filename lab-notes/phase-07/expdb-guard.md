# expdb chain-generation guard (Phase 7)

## Rule source

`private/forks/LibreEcho-Platform/AGENTS.md:69-90` ("Boot-chain safety"). Rule 2,
`AGENTS.md:84-88`:

> **Establish the chain generation before any flash write.** Read
> `expdb[0:16]`: MTK magic `88 16 88 58` means the kaeru payload is present and
> v2.0.0 is in use; ASCII `FASTBOOT_PLEASE` means the chain is already broken.
> A partition *name* check (`PARTNAME=expdb`) cannot detect this -- the name is
> identical in both generations and only the content differs.

Rule 1 (`AGENTS.md:79-83`): never write `FASTBOOT_PLEASE` to expdb, never erase
expdb on a v2 chain. Both tools already refuse an expdb write by name; the
allow-list tests pin that.

## Expected value and provenance

On the installed chain `expdb[0:16]` is the LK sub-image's MTK header
`88 16 88 58 | <payload size LE32> | "LK\0" | ...`; the Kaeru patch payload
follows at `round8(512 + LK data size)`.

- `private/lab/phase-01/boot-chain-analysis.md:126` shows the same header at
  offset 0 of the stock `lk_a.bin`.
- `private/lab/phase-05/research/platform-runtime-map.md:156,470` records the
  device-side `libreecho_bootctl.c:376-397` rule: read 48 bytes, require
  `88 16 88 58`, any size, and `"LK\0"` at +8.
- The two lab expdb sources (installed and reference builds) begin
  `88 16 88 58 d0 40 03 00 4c 4b` and `88 16 88 58 40 16 03 00 4c 4b`; the
  size differs per build, so only the magic is compared.
- Product `_expdb_kaeru_chain_ok` already proves LK-then-Kaeru over ADB; the new
  guard is the generation check that runs in the flash context.

## How each context reads it

- Kaeru fastboot: the fork registers `fetch:<name>[:<off>[:<len>]]`, capped at
  1 MiB (`private/forks/kaeru/lib/fastboot/cmd_fetch.c`). Both installers issue
  one `fetch:expdb:0:16` directly on the fastboot USB interface; the stock CLI
  has no range argument and a 10 MiB full fetch is refused. No new device
  capability was added.
- BROM: the future preparation command reads the same 16 bytes with mtkclient
  and calls the shared decision. That command does not exist yet and is not in
  this change.

## Implementation

- Platform `tools/mt8167-arm64/install/expdb_guard.py`:
  `check_expdb_prefix(bytes) -> 'kaeru-v2'`, raising `ExpdbGenerationError` for
  a short/absent read, `FASTBOOT_PLEASE`, or any non-MTK payload. Exposed for
  the preparation command before boot0/LK writes.
- Platform `lidar_install.py`: `require_kaeru_expdb_chain(fb, log)` runs before
  the install write loop and at the start of `bcb_write` (the only misc flash).
  It converts a guard failure or read failure into `Refusal` (exit 2, no write).
- Product `tools/libreecho-install.py`: `check_expdb_chain_generation` plus
  `require_lidar_expdb_generation` (fetch-enable, bounded USB read). Every Lidar
  flash goes through `_flash_fastboot_partition` or the guard at the top of
  `format_userdata_in_fastboot`; Radar and Biscuit take the unchanged path.
- expdb is still not in either write allow-list; no tool can write it by name.

## Tests

- Platform: `python3 -m unittest test_lidar_install` (31 tests, OK). Matching
  generation flashes; `FASTBOOT_PLEASE`, blank, short and unreadable expdb
  refuse with exit 2 and an empty fake-fastboot write log; a bcb write is
  refused before misc is flashed.
- Product: `python3 -m unittest tools.test_release_tools` (see below). Guard
  accepts the MTK prefix and refuses the three bad cases; the flash wrapper
  refuses before `fastboot flash` on mismatch and leaves the Radar command
  untouched.

Unverified: no hardware run; `fetch:expdb:0:16` against a live unit was not
repeated (the same Kaeru range command is exercised by the misc readback path).
