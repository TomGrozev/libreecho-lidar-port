#!/usr/bin/env bash
# Phase 1 read-only boot-chain inventory (PLAN.md Phase 1).
# Uses the owner's existing mtkclient checkout at mtkclient/ and its venv.
# Syntax comes from mtk.py --help and the mtkclient read implementation:
#   r <partitionname,...> <filename,...> [--parttype user|boot1|boot2]
# eMMC boot areas are addressed by parttype: boot1 = MTK BOOT0 area, boot2 = MTK BOOT1 area.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT="$ROOT/dumps/20261110-lidar-readback"
PY="$ROOT/mtkclient/.venv/bin/python"
MTK="$ROOT/mtkclient/mtk.py"
cd "$ROOT/mtkclient" || exit 1

echo "== GPT table (read-only) =="
"$PY" "$MTK" printgpt

echo "== GPT raw =="
"$PY" "$MTK" r gpt "$OUT/gpt.bin"

echo "== GPT partitions (order matches filenames) =="
"$PY" "$MTK" r tee1,expdb,lk_a,lk_b,boot_a,boot_b,misc \
  "$OUT/tee1.bin","$OUT/expdb.bin","$OUT/lk_a.bin","$OUT/lk_b.bin" \
  "$OUT/boot_a.bin","$OUT/boot_b.bin","$OUT/misc.bin"

echo "== BOOT0 (eMMC boot1 area) =="
"$PY" "$MTK" r boot0 "$OUT/boot0.bin" --parttype boot1

echo "== BOOT1 (eMMC boot2 area) =="
"$PY" "$MTK" r boot1 "$OUT/boot1.bin" --parttype boot2
