#!/usr/bin/env bash
# Rebuild the airplay2 feature payload with the sendspind built from UI
# feature/lidar-support-0.14.6 (715dd4f). Host-only.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/../../../.." && pwd -P)"
A="$ROOT/artifacts/phase-07/features-715dd4f"
SENDSPIN="${1:?usage: $0 <sendspind-output-dir>}"
mkdir -p "$A/staging"
cp -a "$ROOT/artifacts/phase-07/features-sendspin-fix/root" "$A/root"
install -m 0755 "$SENDSPIN/libreecho-sendspind" \
  "$A/root/usr/local/sbin/libreecho-sendspind"
cp -a "$SENDSPIN/licenses/libreecho-sendspin/." \
  "$A/root/usr/local/share/licenses/libreecho-sendspin/"
bash "$ROOT/repos/LibreEcho/build/package_feature_payload.sh" airplay2 \
  "$A/root" "$A/staging/probe.payload.squashfs" \
  "$A/staging/probe.manifest.json" >"$A/staging/package.log" 2>&1
P=$(sha256sum "$A/staging/probe.payload.squashfs" | cut -d' ' -f1)
cp "$A/staging/probe.payload.squashfs" \
  "$A/libreecho-lidar-base-airplay2-$P.payload.squashfs"
cp "$A/staging/probe.manifest.json" \
  "$A/libreecho-lidar-base-airplay2-$P.manifest.json"
printf 'payload_sha=%s\n' "$P"
sha256sum "$A/libreecho-lidar-base-airplay2-$P.manifest.json"
printf '{"airplay2":{"payload":"%s","manifest":"%s"}}\n' \
  "$A/libreecho-lidar-base-airplay2-$P.payload.squashfs" \
  "$A/libreecho-lidar-base-airplay2-$P.manifest.json" \
  >"$A/staging/catalog-entry.json"
cat "$A/staging/catalog-entry.json"
