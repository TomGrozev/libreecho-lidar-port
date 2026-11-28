# Phase 1: live read-only boot-chain inventory

Before planning any write, I took a read-only inventory of the stock boot chain on the
Echo Plus 2nd Gen. I put the device into BROM mode with the action button held at
power-on. Then my mtkclient checkout (unmodified apart from a DA log-frame patch) read
BOOT0, BOOT1, a refreshed GPT, tee1, expdb, lk_a, lk_b, boot_a, boot_b and misc without
writing anything. The reads confirmed the SoC hardware code `0x8167`, picked the
production Lidar DTB out of the 19 appended DTBs, and measured the anti-rollback exposure
of the stock BOOT0. `notes.md` is the full record.

| Path | Content |
|---|---|
| `notes.md` | Full phase record: commands, tool trail, findings, hashes |
| `read-inventory.sh` | Every read command used, in run order |
| `boot-chain-analysis.md` | Analysis of the stock boot chain and anti-rollback exposure |
| `dtb-analysis.md` | Identification of the production Lidar DTB |
| `manifest.json`, `hashes.txt` | Manifest of everything read, with sizes and SHA-256 hashes |
| `brom-printgpt.log`, `printgpt-live.log` | Partition table reads from BROM and from the live session |
| `efuse.log`, `connect-mode.log` | eFuse state and BROM connect-mode captures |
| `dtb/` | The stock DTBs read from the device |
| `mtkclient-da-logframes.patch` | The local mtkclient patch that forwards DA log frames |

The stock boot-chain backups themselves live in the private workspace under `dumps/`.
