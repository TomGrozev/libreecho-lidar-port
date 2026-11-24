#!/usr/bin/env bash
# Build and verify the Lidar loudness lab OTA (v0.2.36) from the working tree
# of LibreEcho-Platform. Host-only: never talks to a device.
#
# Why 0.2.36 and not 0.2.35: v0.2.35 is already installed and confirmed
# (private/lab/phase-07/v0235/result.md, slot b, 2026-11-23 21:34). PLAN.md's
# Wi-Fi dev-update step requires a bundle "whose version is above the installed
# one", so this build takes the next version. The v0.2.35 build predates the
# loudness change and is otherwise the same base.
#
# Differences from build_v0235.sh:
# - Platform is deliberately dirty: the Lidar loudness change is uncommitted
#   (tools/mt8167-arm64/libreecho_platform_targets.py and
#   tools/mt8163-arm32/airplay/audio_engine.c, plus their README/test edits).
#   The guard allows exactly those four modified paths, refuses anything else,
#   and records the `git diff` hash in the artifact build-info.
# - The UI bundle is reused from components-470eb36 (UI HEAD 470eb36, built
#   clean on 2026-11-23). The UI checkout now carries unrelated uncommitted work,
#   so it is *not* rebuilt; the image builder only validates the bundle manifest.
# - Verification checks the built audio profile (lo_driver_gain=6,
#   hp_driver_gain=6) and that the payload engine is a fresh build that differs
#   from both v0.2.34's and v0.2.35's engine binaries.
#
# usage: build_v0236.sh [--verify-only]
set -euo pipefail
cd /workspace/libreecho
R=$PWD
PLATFORM=$R/private/forks/LibreEcho-Platform
UI=$R/private/forks/LibreEcho-UI
BRANCH=feature/lidar-support-0.14.6
VER=0.2.36
D=$R/private/artifacts/phase-07/v0236
COMP=$R/private/artifacts/phase-07/components-470eb36
P5=$R/private/artifacts/phase-05
DEP=$R/private/lab/phase-07/sendspin-silence/deploy
BASE=$R/private/artifacts/phase-07/features-715dd4f
SENDSPIN=$R/private/artifacts/phase-07/v0233/root/usr/local/sbin/libreecho-sendspind
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
ENG_V0234_SHA=84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35  # features-715dd4f, shipped by v0.2.34
ENG_V0235_SHA=9334df030810136e9c0c5413d90aa4e54c46d0d0b4d83e767c8f1756ca3d1ea5
QEMU=$P5/host-tools/qemu/usr/bin
export PATH="$QEMU:$PATH"
KERNEL=$R/private/artifacts/phase-06/kernel-step36-thermal
WANT_DTB=a8e1957314334d9a03aa6c96082a6d82a1202ee02729cdc2097d8355d6bd5bc7
WANT_IMAGE=f444f4d0cc63da2a204720dfde560020c9addf3a36910ceb71d29fecf28e3c75
CC=$P5/toolchains/armhf-cc/arm-linux-gnueabihf-gcc
STRIP=$P5/toolchains/armhf-root/usr/bin/arm-linux-gnueabihf-strip
TINY=$R/private/artifacts/phase-06/features-airplay2-lidar/work/tinyalsa-e43025bbf702eb7dd8edd48c1eb50530c60f1de8
P6C=$R/private/artifacts/phase-06/components
VERIFY_ONLY=0
case "${1:-}" in
  --verify-only) VERIFY_ONLY=1 ;;
  '') ;;
  *) echo "usage: $0 [--verify-only]" >&2; exit 2 ;;
esac
mkdir -p "$D/ota" "$D/images"

# Exactly the loudness change, nothing else. The audio_engine.c edit is the
# Lidar ceiling; the targets edit is the codec driver gain. README and test
# edits document/cover the same two lines.
ALLOWED_DIRTY='^ M tools/mt8163-arm32/airplay/README.md$|^ M tools/mt8163-arm32/airplay/audio_engine.c$|^ M tools/mt8163-arm32/airplay/test_airplay_session_dsp.py$|^ M tools/mt8167-arm64/libreecho_platform_targets.py$'
# Another agent's in-progress boot-chain backup tooling sits untracked under
# tools/mt8167-arm64/install/; the image builder does not import it. Record it,
# do not refuse on it.
ALLOWED_UNTRACKED='^\?\? tools/mt8167-arm64/install/[A-Za-z0-9_.-]+$'

guard() {
  local repo=$1 name=$2 branch dirty unexpected
  branch=$(git -C "$repo" rev-parse --abbrev-ref HEAD)
  [ "$branch" = "$BRANCH" ] || {
    echo "REFUSE: $name is on $branch, expected $BRANCH" >&2; exit 1; }
  dirty=$(git -C "$repo" status --porcelain=v1 --untracked-files=all)
  if [ -n "$dirty" ]; then
    unexpected=$(printf '%s\n' "$dirty" |
      grep -Ev "$ALLOWED_DIRTY" | grep -Ev "$ALLOWED_UNTRACKED" || true)
    [ -z "$unexpected" ] || {
      echo "REFUSE: $name has unexpected uncommitted or untracked files:" >&2
      printf '%s\n' "$unexpected" >&2; exit 1; }
    echo "guard: $name carries the expected loudness edit:" >&2
    printf '%s\n' "$dirty" >&2
  fi
}
guard "$PLATFORM" LibreEcho-Platform
UI_HEAD=$(git -C "$UI" rev-parse HEAD)
[ "$UI_HEAD" = 470eb363ca1f64758fe45817351770e51d84e499 ] || {
  echo "REFUSE: UI is at $UI_HEAD, the pinned bundle is 470eb36" >&2; exit 1; }
[ -f "$COMP/ui-bundle/bundle/share/libreecho/ui-manifest.txt" ] || {
  echo "REFUSE: missing pinned UI bundle under $COMP" >&2; exit 1; }
grep -qx 'source_commit=470eb363ca1f64758fe45817351770e51d84e499' \
  "$COMP/ui-bundle/bundle/share/libreecho/ui-manifest.txt" || {
  echo "REFUSE: UI bundle was not built from UI 470eb36" >&2; exit 1; }
PLATFORM_DIFF_SHA=$(git -C "$PLATFORM" diff | sha256sum | cut -d' ' -f1)
PLATFORM_DIRTY=$(git -C "$PLATFORM" status --porcelain=v1 --untracked-files=all)
UI_DIRTY_AT_BUILD=$(git -C "$UI" status --porcelain=v1 --untracked-files=all | wc -l)

if [ "$VERIFY_ONLY" = 1 ]; then
  PF_HEAD=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["platform_head"])' "$D/build-info.json")
else
  PF_HEAD=$(git -C "$PLATFORM" rev-parse HEAD)
fi
echo "guard: Platform $PF_HEAD (working tree), UI bundle $UI_HEAD, version $VER"

if [ "$VERIFY_ONLY" = 0 ]; then
echo "=== images (audio profile from the working-tree platform tools) ==="
KERNEL_DIR="$KERNEL" \
LIDAR_TOOLS="$PLATFORM/tools/mt8167-arm64" \
UI_BUNDLE_DIR="$COMP/ui-bundle/bundle" UI_SOURCE="$UI" \
UI_COMMIT="$UI_HEAD" \
UI_DIFF_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 \
bash "$DEP/build_images_sendspin.sh" --output-dir "$D/images" 2>&1 | tee "$D/images-build.log"

echo "=== audio engine from the working-tree Platform sources ==="
SRC=$PLATFORM/tools/mt8163-arm32/airplay
mkdir -p "$D/engine"
"$CC" -O2 -std=c99 -Wall -I"$SRC" -I"$TINY/include" -o "$D/engine/libreecho-audio-engine" \
  "$SRC/audio_engine.c" "$SRC/aec_reference.c" "$SRC/audio_sink.c" "$SRC/audio_timing.c" \
  "$SRC/audio_visualizer.c" "$SRC/playback_status.c" -L"$TINY/src" -ltinyalsa -ldl -lm \
  2>&1 | tee "$D/engine/build.log"
LD_LIBRARY_PATH=$P5/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
  "$STRIP" --strip-unneeded "$D/engine/libreecho-audio-engine"
sha256sum "$SRC/audio_engine.c" "$SRC/test_airplay_session_dsp.py" \
  > "$D/engine/sources.sha256"

echo "=== airplay2 payload (engine from the working tree; sendspind unchanged) ==="
A=$R/private/artifacts/phase-07/features-loudness-${PF_HEAD:0:9}
rm -rf "$A"; mkdir -p "$A/staging"
cp -a "$BASE/root" "$A/root"
install -m 0755 "$SENDSPIN" "$A/root/usr/local/sbin/libreecho-sendspind"
install -m 0755 "$D/engine/libreecho-audio-engine" "$A/root/usr/local/sbin/libreecho-audio-engine"
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
  --release "lidar-lab-v$VER" --version "$VER" \
  --update-channel dev --service-profile production \
  --signing-key "$P5/ota/lab-key/ed25519-seed.hex" \
  --public-key "$P5/ota/lab-key/ed25519-public.hex" \
  --output "$D/ota/lidar-lab-v$VER.ota.tar" > "$D/ota/ota-build.log" 2>&1
fi
GEN=$(ls -d "$D/ota"/generations/txn-* | head -1)

exec > >(tee "$D/verify-v0236.log") 2>&1
echo "=== proof (platform $PF_HEAD working tree, ui $UI_HEAD, version $VER) ==="
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
grep -qx 'lo_driver_gain=6' "$rd/etc/libreecho/audio-profile" &&
  ok "image audio profile lo_driver_gain=6" || bad "image audio profile lo_driver_gain=6"
grep -qx 'hp_driver_gain=6' "$rd/etc/libreecho/audio-profile" &&
  ok "image audio profile hp_driver_gain=6" || bad "image audio profile hp_driver_gain=6"
grep -qx 'speaker_chain=lidar' "$rd/etc/libreecho/audio-profile" &&
  ok "image audio profile speaker_chain=lidar" || bad "image audio profile speaker_chain"
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
[ "$eng" = "$(sha256sum "$D/engine/libreecho-audio-engine" | cut -d' ' -f1)" ] &&
  ok "payload audio-engine is the working-tree build ($eng)" || bad "payload audio-engine $eng"
[ "$eng" != "$ENG_V0235_SHA" ] &&
  ok "audio-engine differs from the v0.2.35 engine $ENG_V0235_SHA" || bad "audio-engine unchanged from v0.2.35"
[ "$eng" != "$ENG_V0234_SHA" ] &&
  ok "audio-engine differs from the v0.2.34 engine $ENG_V0234_SHA" || bad "audio-engine unchanged from v0.2.34"
[ "$(sha256sum "$PLATFORM/tools/mt8163-arm32/airplay/audio_engine.c" | cut -d' ' -f1)" = \
  "$(sed -n 's/^\([0-9a-f]*\)  .*audio_engine.c$/\1/p' "$D/engine/sources.sha256")" ] &&
  ok "engine source hash recorded for the working-tree audio_engine.c" || bad "engine source hash"
M=$D/images/boot-lidar-v2.manifest.json
[ "$(jq -r .inputs.dtb.sha256 "$M")" = "$WANT_DTB" ] && ok "image DTB is kernel-step36-thermal" || bad "image DTB $(jq -r .inputs.dtb.sha256 "$M")"
[ "$(jq -r .inputs.kernel_image.sha256 "$M")" = "$WANT_IMAGE" ] && ok "image kernel is kernel-step36-thermal" || bad "image kernel"
strings "$KERNEL/libreecho-lidar.dtb" | grep -qx board-thermal && ok "DTB carries the board-thermal zone" || bad "DTB thermal zone"
printf '%s\n' "$NEW" > /tmp/v0236-new.hex; printf '%s\n' "$OLD" > /tmp/v0236-old.hex
VFY=$P5/components/ota-control/libreecho-update-verify
"$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0236-new.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA signature new key" || bad "new-key signature"
! "$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0236-old.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA rejected old key" || bad "old key accepted"
grep -q "^version=$VER$" "$GEN/target.manifest" && ok "OTA manifest version=$VER" || bad "OTA manifest version"

if [ "$VERIFY_ONLY" = 1 ]; then
  ( cd "$D" && sha256sum --quiet -c SHA256SUMS ) && ok "SHA256SUMS match" || bad "SHA256SUMS mismatch"
else
python3 - "$D" "$PF_HEAD" "$UI_HEAD" "$PLATFORM_DIFF_SHA" "$PLATFORM_DIRTY" "$UI_DIRTY_AT_BUILD" "$VER" <<'PY'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
records = {
    'version': sys.argv[7],
    'platform_head': sys.argv[2],
    'platform_working_tree_diff_sha256': sys.argv[4],
    'platform_working_tree_dirty': sys.argv[5].splitlines(),
    'ui_head': sys.argv[3],
    'branch': 'feature/lidar-support-0.14.6',
    'note': 'Platform built from the working tree (loudness edit uncommitted); '
            'UI bundle reused from components-470eb36 because the UI checkout '
            'carried unrelated uncommitted work (' + sys.argv[6] + ' paths).',
}
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
echo "INFO bundle $(sha256sum "$D"/ota/lidar-lab-v$VER.ota.tar | cut -d' ' -f1)"
exit $fail
