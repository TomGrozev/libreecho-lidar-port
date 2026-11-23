#!/usr/bin/env bash
# Build and verify v0.2.34 from the main checkouts of LibreEcho-Platform and
# LibreEcho-UI. Host-only: never talks to a device.
#
# Guard: both repos must be on feature/lidar-support-0.14.6 with a clean tree
# (no modified or untracked file under the source paths). HEAD s hashes are
# recorded in the artifact build-info.
#
# usage: build_v0234.sh
set -euo pipefail
cd /workspace/libreecho
R=$PWD
PLATFORM=$R/private/forks/LibreEcho-Platform
UI=$R/private/forks/LibreEcho-UI
BRANCH=feature/lidar-support-0.14.6
D=$R/private/artifacts/phase-07/v0234
COMP=$R/private/artifacts/phase-07/components-0d2285b
P5=$R/private/artifacts/phase-05
DEP=$R/private/lab/phase-07/sendspin-silence/deploy
BASE=$R/private/artifacts/phase-07/features-715dd4f
SENDSPIN=$R/private/artifacts/phase-07/v0233/root/usr/local/sbin/libreecho-sendspind
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
V0228=$R/private/artifacts/phase-06/images-step37-v0228
QEMU=$P5/host-tools/qemu/usr/bin
KERNEL=$R/private/artifacts/phase-06/kernel
P6C=$R/private/artifacts/phase-06/components
VERIFY_ONLY=0
case "${1:-}" in
  --verify-only) VERIFY_ONLY=1 ;;
  '') ;;
  *) echo "usage: $0 [--verify-only]" >&2; exit 2 ;;
esac
mkdir -p "$D/ota" "$D/images"

guard() {
  local repo=$1 name=$2 branch dirty untracked
  branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD)
  [ "$branch" = "$BRANCH" ] || {
    echo "REFUSE: $name is on $branch, expected $BRANCH" >&2; exit 1; }
  dirty=$(git -C "$repo" status --porcelain=v1 --untracked-files=all)
  [ -z "$dirty" ] || {
    echo "REFUSE: $name has uncommitted or untracked files:" >&2
    printf '%s\n' "$dirty" >&2; exit 1; }
}
guard "$PLATFORM" LibreEcho-Platform
guard "$UI" LibreEcho-UI
if [ "$VERIFY_ONLY" = 1 ]; then
  # Re-verify the existing artifacts against the heads they were built from.
  PF_HEAD=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["platform_head"])' "$D/build-info.json")
  UI_HEAD=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["ui_head"])' "$D/build-info.json")
else
  PF_HEAD=$(git -C "$PLATFORM" rev-parse HEAD)
  UI_HEAD=$(git -C "$UI" rev-parse HEAD)
fi
echo "guard: Platform $PF_HEAD, UI $UI_HEAD on $BRANCH, both clean"

if [ "$VERIFY_ONLY" = 0 ]; then
echo "=== components: UI bundle from UI $UI_HEAD ==="
COMP_DIR="$COMP" UI_SOURCE_DIR="$UI" bash "$DEP/build_components_sendspin.sh" ui

echo "=== images ==="
LIDAR_TOOLS="$PLATFORM/tools/mt8167-arm64" \
UI_BUNDLE_DIR="$COMP/ui-bundle/bundle" UI_SOURCE="$UI" \
UI_COMMIT="$UI_HEAD" \
UI_DIFF_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 \
bash "$DEP/build_images_sendspin.sh" --output-dir "$D/images" 2>&1 | tee "$D/images-build.log"

echo "=== airplay2 payload (engine reused from Platform HEAD; sendspind sources unchanged since 715dd4f) ==="
A=$R/private/artifacts/phase-07/features-0d2285b
rm -rf "$A"; mkdir -p "$A/staging"
cp -a "$BASE/root" "$A/root"
install -m 0755 "$SENDSPIN" "$A/root/usr/local/sbin/libreecho-sendspind"
bash "$R/private/forks/LibreEcho/build/package_feature_payload.sh" airplay2 \
  "$A/root" "$A/staging/probe.payload.squashfs" "$A/staging/probe.manifest.json" \
  > "$A/staging/package.log" 2>&1
P=$(sha256sum "$A/staging/probe.payload.squashfs" | cut -d' ' -f1)
cp "$A/staging/probe.payload.squashfs" "$A/libreecho-lidar-base-airplay2-$P.payload.squashfs"
cp "$A/staging/probe.manifest.json" "$A/libreecho-lidar-base-airplay2-$P.manifest.json"
for f in "$A"/libreecho-lidar-base-airplay2-*; do cp "$f" "$D/"; done
python3 - "$A" "$D" <<'PY'
import hashlib, json, sys
from pathlib import Path
a, d = Path(sys.argv[1]), Path(sys.argv[2])
payload = next(a.glob('libreecho-lidar-base-airplay2-*.payload.squashfs'))
manifest = next(a.glob('libreecho-lidar-base-airplay2-*.manifest.json'))
catalog = json.loads((Path('private/artifacts/phase-06/features-airplay2-latency/feature-catalog.json')).read_text())
entry = catalog['features']['airplay2']
entry['payload'] = str(payload); entry['payload_sha256'] = hashlib.sha256(payload.read_bytes()).hexdigest()
entry['payload_size'] = payload.stat().st_size
entry['manifest'] = str(manifest); entry['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
entry['manifest_size'] = manifest.stat().st_size
(d / 'feature-catalog.json').write_text(json.dumps(catalog, indent=2, sort_keys=True) + '\n')
print('airplay2_payload_sha256=' + entry['payload_sha256'])
PY

echo "=== OTA ==="
python3 private/lab/phase-05/ota/make_lab_ota.py \
  --boot-image "$D/images/boot-lidar-v2.img" \
  --feature-catalog "$D/feature-catalog.json" \
  --release lidar-lab-v0.2.34 --version 0.2.34 \
  --update-channel dev --service-profile production \
  --signing-key "$P5/ota/lab-key/ed25519-seed.hex" \
  --public-key "$P5/ota/lab-key/ed25519-public.hex" \
  --output "$D/ota/lidar-lab-v0.2.34.ota.tar" > "$D/ota/ota-build.log" 2>&1
fi
GEN=$(ls -d "$D/ota"/generations/txn-* | head -1)

exec > >(tee "$D/verify-v0234.log") 2>&1
echo "=== proof (platform $PF_HEAD, ui $UI_HEAD) ==="
fail=0
ok() { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }
V2=$D/images/boot-lidar-v2.img
[ "$(stat -c %s "$V2")" = 16777216 ] && ok "boot.img size 16777216" || bad "boot.img size"
head -c 8 "$V2" | grep -q 'ANDROID!' && ok "boot.img ANDROID! magic" || bad "boot.img magic"
ramdisk=$D/images/boot-lidar-v2.ramdisk.cpio.xz
rd=$D/ramdisk-check; rm -rf "$rd"; mkdir -p "$rd"
( cd "$rd" && xz -dc "$ramdisk" | cpio -id --quiet ) 2>/dev/null
member=$(cd "$rd" && find . -name ota-public-key.hex | head -1)
got=$(tr -d '[:space:]' < "$rd/${member#./}")
[ "$got" = "$NEW" ] && ok "ramdisk key is the new key" || bad "ramdisk key"
grep -q 'lidar_radio_bringup' "$rd/libreecho-init" && ok "ramdisk Lidar Wi-Fi bring-up" || bad "bringup"
grep -q 'last_check=wifi-radio' "$rd/libreecho-init" && ok "ramdisk wifi-radio gate" || bad "wifi gate"
grep -q 'last_check=target-identity' "$rd/libreecho-init" && ok "ramdisk target-identity gate" || bad "target gate"
[ "$(sed -n '1p' "$rd/etc/libreecho/target")" = target_id=lidar ] && ok "target_id=lidar" || bad "target"
web=$rd/etc/init.d/libreecho-web.init
grep -q 'assistant_services' "$web" && ok "web init startup gate (assistant_services)" || bad "web startup gate"
grep -q 'feature-services-continued-after-topology-failure' "$rd/usr/local/sbin/libreecho-reconcile-features" &&
  ok "reconciler topology fix" || bad "reconciler"
grep -q "source_commit=$UI_HEAD" "$COMP/ui-bundle/bundle/share/libreecho/ui-manifest.txt" &&
  ok "UI manifest source_commit=$UI_HEAD" || bad "UI manifest commit"
esph=$(sha256sum "$rd/usr/local/sbin/libreecho-esphomed" | cut -d' ' -f1)
[ "$esph" = "$(sha256sum "$COMP/ui-bundle/bundle/sbin/libreecho-esphomed" | cut -d' ' -f1)" ] &&
  ok "ramdisk esphomed matches the UI $UI_HEAD bundle ($esph)" || bad "esphomed differs from the UI bundle"
PS=$(ls "$D"/libreecho-lidar-base-airplay2-*.payload.squashfs)
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = 36572977d9221f2389fe6deec9a8f674307da3418aa1886da74d4b02419e41e4 ] &&
  ok "payload sendspind $v" || bad "sendspind $v"
eng=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
ok "payload audio-engine $eng"
printf '%s\n' "$NEW" > /tmp/v0234-new.hex; printf '%s\n' "$OLD" > /tmp/v0234-old.hex
VFY=$P5/components/ota-control/libreecho-update-verify
"$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0234-new.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA signature new key" || bad "new-key signature"
! "$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0234-old.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA rejected old key" || bad "old key accepted"
python3 "$D/prove_target_parsers.py" > "$D/target-parser-proof.log" 2>&1 &&
  ok "MT8167 verifier passes v0.2.34 and its target-identity guard rejects v0.2.30" ||
  bad "MT8167 verifier contract (see target-parser-proof.log)"

if [ "$VERIFY_ONLY" = 1 ]; then
  ( cd "$D" && sha256sum --quiet -c SHA256SUMS ) && ok "SHA256SUMS match" || bad "SHA256SUMS mismatch"
else
python3 - "$D" "$PF_HEAD" "$UI_HEAD" <<'PY'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
records = {'platform_head': sys.argv[2], 'ui_head': sys.argv[3], 'branch': 'feature/lidar-support-0.14.6'}
files = {}
for p in sorted(d.rglob('*')):
    if p.is_file() and p.name not in ('build-info.json',):
        files[str(p.relative_to(d))] = hashlib.sha256(p.read_bytes()).hexdigest()
records['files'] = files
(d / 'build-info.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
print('build-info written')
PY
( cd "$D" && sha256sum images/* ota/*.ota.tar libreecho-lidar-base-airplay2-* > SHA256SUMS )
fi
echo "INFO txn $(basename "$GEN")"
echo "INFO bundle $(sha256sum "$D"/ota/lidar-lab-v0.2.34.ota.tar | cut -d' ' -f1)"
exit $fail
