#!/usr/bin/env python3
"""Read-only: run the prepare command's own GPT/geometry gate on live reads.

Feeds the live gpt.bin / gpt_backup.bin pulled over adb into parse_gpt() and
check_geometry(), plus lidar_backup_set's data.  Identity fields that only BROM
reports (hwcode) come from the reviewed BROM printgpt evidence for this same
unit; flash size is corroborated by /proc/partitions.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PREP = REPO / "private/forks/LibreEcho-Platform/tools/mt8167-arm64/prepare"
sys.path.insert(0, str(PREP))
sys.path.insert(0, str(PREP.parent / "install"))
sys.path.insert(0, str(PREP.parent))

import lidar_prepare as lp
import lidar_backup_set as backup
from amonet_adapter import Identity

live = HERE / "live-read"
gpt = (live / "gpt.bin").read_bytes()
gpt_backup = (live / "gpt_backup.bin").read_bytes()

geometry = lp.parse_gpt(gpt, gpt_backup)
print(f"gpt primary+backup parse: OK, {len(geometry)} partitions")
for name in ("boot_a", "boot_b", "lk_a", "lk_b", "tee1", "tee2", "expdb",
             "misc", "persist", "userdata"):
    off, size = geometry[name]
    print(f"  {name:9s} offset=0x{off:x} size=0x{size:x}")

identity = Identity(hwcode=0x8167, flash_bytes=backup.FLASH_BYTES,
                    boot_area_bytes=backup.BOOT_AREA_BYTES, sector_bytes=512)
lp.check_geometry(identity, geometry)
print("check_geometry: OK (target partitions, backup-set offsets, userdata bound)")
