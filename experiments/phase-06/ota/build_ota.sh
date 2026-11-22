#!/usr/bin/env bash
# Build the Phase 6 lab OTA pair (v1 generation, then v2 payload) from the
# verified images. Host-only: signs with the lab key, never talks to a device.
#
# The phase-05 maker needs no edits: it reads the image, the feature catalog
# and the key, and writes the bundle plus its generation tree.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(cd -- "$HERE/../../.." && pwd -P)"
ART="$ROOT/artifacts/phase-06"
P5="$ROOT/artifacts/phase-05"
MAKER="$ROOT/experiments/phase-05/ota/make_lab_ota.py"
CATALOG="$P5/ota/lab-run/feature-catalog.json"
KEY="$P5/ota/lab-key"
OUT="$ART/ota"

[[ -f "$ART/images/boot-lidar-v1.img" && -f "$ART/images/boot-lidar-v2.img" ]] || {
  echo "ERROR: build_images.sh must produce verified v1 and v2 images first" >&2
  exit 1
}

mkdir -p "$OUT/lab-v1" "$OUT/lab-v2"
for pair in v1:0.2.13 v2:0.2.14; do
  name="${pair%%:*}" version="${pair##*:}"
  python3 "$MAKER" \
      --boot-image "$ART/images/boot-lidar-$name.img" \
      --feature-catalog "$CATALOG" \
      --release "lidar-lab-v$version" --version "$version" \
      --update-channel dev --service-profile production \
      --signing-key "$KEY/ed25519-seed.hex" \
      --public-key "$KEY/ed25519-public.hex" \
      --output "$OUT/lab-$name/lidar-lab-v$version.ota.tar"
done
