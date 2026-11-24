#!/usr/bin/env bash
# Build and verify the Lidar lab OTA v0.2.37 from pinned commits.
# Host-only: never talks to a device.
#
# Recipe: private/lab/phase-07/volume-quiet/build_v0236.sh (v0.2.36) and
# private/lab/phase-07/ota-v0.2.35.md. Differences from v0.2.36:
# - Kernel is the 47feddd6 build kept in
#   private/artifacts/phase-07/ota-v0.2.35/kernel (Image 272090a9, DTB
#   0e9cc4ff, no uart-has-rtscts), not kernel-step36-thermal a8e19573.
# - Platform is built from a detached worktree at 7011650f9 (the loudness
#   change is committed as 671a2caf9 on top of 02ef8ad6, and 7011650f9 is the
#   LayerNorm reduced-ORT operator list), so uncommitted peer work in the fork
#   is excluded.
# - UI bundle is freshly built from a clean worktree of UI 29a7a0a instead of
#   reusing components-470eb36. 29a7a0a contains 7f5c29a wake-word selection
#   and the service_env link fix.
# - The wakeword feature is the prebuilt qemu-verified payload
#   private/artifacts/wakeword-payload/wakeword.squashfs (3d199f8b...) with
#   waked d11ac4ec..., not the older phase-05 asset 4964fc7b....
#
# usage: ota-v0.2.37-build.sh [--verify-only]
set -euo pipefail
cd /workspace/libreecho
R=$PWD
PLATFORM=$R/private/forks/LibreEcho-Platform
UI=$R/private/forks/LibreEcho-UI
PLATFORM_WT=$R/private/artifacts/phase-07/ota-v0.2.37/src/Platform
UI_WT=$R/private/artifacts/phase-07/ota-v0.2.37/src/UI
VER=0.2.37
PLATFORM_PIN=7011650f9b246e27709a3c2298433f442d281426
UI_PIN=29a7a0ae00e955fea4bca09cb2edd640f76e77dc
D=$R/private/artifacts/phase-07/ota-v0.2.37
COMP=$D/components/ui
P5=$R/private/artifacts/phase-05
DEP=$R/private/lab/phase-07/sendspin-silence/deploy
BASE=$R/private/artifacts/phase-07/features-715dd4f
SENDSPIN=$R/private/artifacts/phase-07/v0233/root/usr/local/sbin/libreecho-sendspind
WF=$R/private/artifacts/wakeword-payload
WF_PAYLOAD_SHA=3d199f8b7805f4a499b380d414fdee63e0b6790f8e361dce06803eb4cba38af4
WF_MANIFEST_SHA=9431c19f3c175ae296acb40604dab5f16f883cbfc6f424ae6d55d459cd448980
WF_WAKED_SHA=d11ac4ecdde481fd4e45d58b385f76af01307576f98d32e5a7c5b84ecb12102b
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
ENG_V0236_SHA=951100e8b50e2752c6cee89aae9a6f5917848b32e08e7f8fef1bb3f5d3bff1d0
ENG_V0235_SHA=9334df030810136e9c0c5413d90aa4e54c46d0d0b4d83e767c8f1756ca3d1ea5
SENDSPIN_SHA=36572977d9221f2389fe6deec9a8f674307da3418aa1886da74d4b02419e41e4
EMPTY_TREE_SHA=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
QEMU=$P5/host-tools/qemu/usr/bin
export PATH="$QEMU:$PATH"
KERNEL=$R/private/artifacts/phase-07/ota-v0.2.35/kernel
WANT_DTB=0e9cc4ffd16b6ece79d5c698a15bb35aa5e252c73276f9525f9e73f64154913a
WANT_IMAGE=272090a9c38fce616f15bd1a68bf2aee3ada763e0cf93a6d8e01b526b40089d2
CC=$P5/toolchains/armhf-cc/arm-linux-gnueabihf-gcc
STRIP=$P5/toolchains/armhf-root/usr/bin/arm-linux-gnueabihf-strip
TINY=$R/private/artifacts/phase-06/features-airplay2-lidar/work/tinyalsa-e43025bbf702eb7dd8edd48c1eb50530c60f1de8
VERIFY_ONLY=0
case "${1:-}" in
  --verify-only) VERIFY_ONLY=1 ;;
  '') ;;
  *) echo "usage: $0 [--verify-only]" >&2; exit 2 ;;
esac
mkdir -p "$D/ota" "$D/images" "$D/src"

# --- input guards -----------------------------------------------------------
# The pinned commits must exist and carry the fixes this release claims.
for c in 02ef8ad6a2e0f9faa59a83f2510ed3c7cbb8be38 671a2caf9; do
  git -C "$PLATFORM" merge-base --is-ancestor "$c" "$PLATFORM_PIN" || {
    echo "REFUSE: $c is not an ancestor of Platform $PLATFORM_PIN" >&2; exit 1; }
done
if [ ! -e "$PLATFORM_WT/.git" ]; then
  git -C "$PLATFORM" worktree add --detach "$PLATFORM_WT" "$PLATFORM_PIN"
fi
[ "$(git -C "$PLATFORM_WT" rev-parse HEAD)" = "$PLATFORM_PIN" ] || {
  echo "REFUSE: Platform worktree is not at $PLATFORM_PIN" >&2; exit 1; }
[ -z "$(git -C "$PLATFORM_WT" status --porcelain=v1 --untracked-files=all)" ] || {
  echo "REFUSE: Platform worktree is not clean" >&2
  git -C "$PLATFORM_WT" status --porcelain=v1 --untracked-files=all >&2; exit 1; }
[ "$(sha256sum "$KERNEL/Image" | cut -d' ' -f1)" = "$WANT_IMAGE" ] || {
  echo "REFUSE: kernel Image is not $WANT_IMAGE" >&2; exit 1; }
[ "$(sha256sum "$KERNEL/libreecho-lidar.dtb" | cut -d' ' -f1)" = "$WANT_DTB" ] || {
  echo "REFUSE: kernel DTB is not $WANT_DTB" >&2; exit 1; }
[ "$(git -C "$UI" rev-parse HEAD)" = "$UI_PIN" ] || {
  echo "REFUSE: UI HEAD is $(git -C "$UI" rev-parse HEAD), expected $UI_PIN" >&2; exit 1; }
if [ ! -e "$UI_WT/.git" ]; then
  git -C "$UI" worktree add --detach "$UI_WT" "$UI_PIN"
fi
[ "$(git -C "$UI_WT" rev-parse HEAD)" = "$UI_PIN" ] || {
  echo "REFUSE: UI worktree is not at $UI_PIN" >&2; exit 1; }
[ "$(sha256sum "$WF/wakeword.squashfs" | cut -d' ' -f1)" = "$WF_PAYLOAD_SHA" ] || {
  echo "REFUSE: wakeword.squashfs hash mismatch" >&2; exit 1; }
[ "$(sha256sum "$WF/waked" | cut -d' ' -f1)" = "$WF_WAKED_SHA" ] || {
  echo "REFUSE: waked hash mismatch" >&2; exit 1; }
[ "$(sha256sum "$WF/wakeword.manifest.json" | cut -d' ' -f1)" = "$WF_MANIFEST_SHA" ] || {
  echo "REFUSE: wakeword manifest hash mismatch" >&2; exit 1; }
[ -z "$(git -C "$UI_WT" status --porcelain=v1 --untracked-files=all)" ] || {
  echo "REFUSE: UI worktree is not clean" >&2
  git -C "$UI_WT" status --porcelain=v1 --untracked-files=all >&2; exit 1; }

if [ "$VERIFY_ONLY" = 0 ]; then
echo "=== UI bundle from a clean UI $UI_PIN worktree ==="
COMP_DIR="$COMP" UI_SOURCE_DIR="$UI_WT" \
  bash "$DEP/build_components_sendspin.sh" ui 2>&1 | tee "$D/ui-components.log"
UI_BUNDLE=$COMP/ui-bundle/bundle
UI_MANIFEST_SHA=$(sha256sum "$UI_BUNDLE/share/libreecho/ui-manifest.txt" | cut -d' ' -f1)

echo "=== images (kernel 47feddd6 + Platform $PLATFORM_PIN tools + UI $UI_PIN) ==="
KERNEL_DIR="$KERNEL" \
LIDAR_TOOLS="$PLATFORM_WT/tools/mt8167-arm64" \
UI_BUNDLE_DIR="$UI_BUNDLE" UI_SOURCE="$UI_WT" \
UI_COMMIT="$UI_PIN" \
UI_DIFF_SHA256="$EMPTY_TREE_SHA" \
  bash "$DEP/build_images_sendspin.sh" --output-dir "$D/images" 2>&1 | tee "$D/images-build.log"

echo "=== audio engine from Platform $PLATFORM_PIN sources ==="
SRC=$PLATFORM_WT/tools/mt8163-arm32/airplay
mkdir -p "$D/engine"
"$CC" -O2 -std=c99 -Wall -I"$SRC" -I"$TINY/include" -o "$D/engine/libreecho-audio-engine" \
  "$SRC/audio_engine.c" "$SRC/aec_reference.c" "$SRC/audio_sink.c" "$SRC/audio_timing.c" \
  "$SRC/audio_visualizer.c" "$SRC/playback_status.c" -L"$TINY/src" -ltinyalsa -ldl -lm \
  2>&1 | tee "$D/engine/build.log"
LD_LIBRARY_PATH=$P5/toolchains/armhf-root/usr/lib/x86_64-linux-gnu \
  "$STRIP" --strip-unneeded "$D/engine/libreecho-audio-engine"
sha256sum "$SRC/audio_engine.c" "$SRC/test_airplay_session_dsp.py" \
  > "$D/engine/sources.sha256"

echo "=== airplay2 payload (engine from $PLATFORM_PIN; sendspind unchanged) ==="
A=$R/private/artifacts/phase-07/features-loudness-${PLATFORM_PIN:0:9}
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

echo "=== wakeword payload (prebuilt, qemu-verified) ==="
cp "$WF/wakeword.squashfs" "$D/libreecho-lidar-base-wakeword-$WF_PAYLOAD_SHA.payload.squashfs"
cp "$WF/wakeword.manifest.json" "$D/libreecho-lidar-base-wakeword-$WF_MANIFEST_SHA.manifest.json"

echo "=== feature catalog ==="
python3 - "$A" "$D" "$WF_PAYLOAD_SHA" "$WF_MANIFEST_SHA" <<'PY'
import hashlib, json, sys
from pathlib import Path
a, d = Path(sys.argv[1]), Path(sys.argv[2])
wf_payload_sha, wf_manifest_sha = sys.argv[3], sys.argv[4]
payload = next(a.glob('libreecho-lidar-base-airplay2-*.payload.squashfs'))
manifest = next(a.glob('libreecho-lidar-base-airplay2-*.manifest.json'))
catalog = json.loads((Path('private/artifacts/phase-06/features-airplay2-latency/feature-catalog.json')).read_text())
entry = catalog['features']['airplay2']
entry['payload'] = str(payload); entry['payload_sha256'] = hashlib.sha256(payload.read_bytes()).hexdigest()
entry['payload_size'] = payload.stat().st_size
entry['manifest'] = str(manifest); entry['manifest_sha256'] = hashlib.sha256(manifest.read_bytes()).hexdigest()
entry['manifest_size'] = manifest.stat().st_size
wf_payload = next(d.glob(f'libreecho-lidar-base-wakeword-{wf_payload_sha}.payload.squashfs'))
wf_manifest = next(d.glob(f'libreecho-lidar-base-wakeword-{wf_manifest_sha}.manifest.json'))
wentry = catalog['features']['wakeword']
wentry['payload'] = str(wf_payload); wentry['payload_sha256'] = hashlib.sha256(wf_payload.read_bytes()).hexdigest()
wentry['payload_size'] = wf_payload.stat().st_size
wentry['manifest'] = str(wf_manifest); wentry['manifest_sha256'] = hashlib.sha256(wf_manifest.read_bytes()).hexdigest()
wentry['manifest_size'] = wf_manifest.stat().st_size
(d / 'feature-catalog.json').write_text(json.dumps(catalog, indent=2, sort_keys=True) + '\n')
print('airplay2_payload_sha256=' + entry['payload_sha256'])
print('wakeword_payload_sha256=' + wentry['payload_sha256'])
print('wakeword_manifest_sha256=' + wentry['manifest_sha256'])
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
GEN=$(ls -dt "$D/ota"/generations/txn-* | head -1)
UI_BUNDLE=$COMP/ui-bundle/bundle
UI_MANIFEST_SHA=$(sha256sum "$UI_BUNDLE/share/libreecho/ui-manifest.txt" | cut -d' ' -f1)

exec > >(tee "$D/verify-v0237.log") 2>&1
echo "=== proof (platform worktree $PLATFORM_PIN clean, ui $UI_PIN, version $VER) ==="
fail=0
ok() { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }
[ "$(git -C "$PLATFORM_WT" rev-parse HEAD)" = "$PLATFORM_PIN" ] && ok "platform worktree HEAD $PLATFORM_PIN" || bad "platform worktree HEAD"
[ -z "$(git -C "$PLATFORM_WT" status --porcelain=v1 --untracked-files=all)" ] && ok "platform worktree clean" || bad "platform worktree dirty"
for c in 02ef8ad6a2e0f9faa59a83f2510ed3c7cbb8be38 671a2caf9; do
  git -C "$PLATFORM" merge-base --is-ancestor "$c" "$PLATFORM_PIN" && ok "platform $PLATFORM_PIN contains $c" || bad "platform missing $c"
done
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
grep -qx "source_commit=$UI_PIN" "$UI_BUNDLE/share/libreecho/ui-manifest.txt" &&
  ok "UI manifest source_commit=$UI_PIN" || bad "UI manifest commit"
grep -qx "source_diff_sha256=$EMPTY_TREE_SHA" "$UI_BUNDLE/share/libreecho/ui-manifest.txt" &&
  ok "UI manifest source_diff_sha256 is the clean tree" || bad "UI manifest diff sha"
esph=$(sha256sum "$rd/usr/local/sbin/libreecho-esphomed" | cut -d' ' -f1)
[ "$esph" = "$(sha256sum "$UI_BUNDLE/sbin/libreecho-esphomed" | cut -d' ' -f1)" ] &&
  ok "ramdisk esphomed matches the UI $UI_PIN bundle ($esph)" || bad "esphomed differs from the UI bundle"
PS=$(ls "$D"/libreecho-lidar-base-airplay2-*.payload.squashfs)
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = "$SENDSPIN_SHA" ] && ok "payload sendspind $v" || bad "sendspind $v"
eng=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
[ "$eng" = "$(sha256sum "$D/engine/libreecho-audio-engine" | cut -d' ' -f1)" ] &&
  ok "payload audio-engine is the $PLATFORM_PIN build ($eng)" || bad "payload audio-engine $eng"
# Platform 7011650f9 differs from v0.2.36's 0a4d7a6e only by the wakeword
# required_operators.config, so the engine bytes are expected to match v0.2.36
# exactly (the loudness edits were committed unchanged as 671a2caf9).
[ "$eng" = "$ENG_V0236_SHA" ] &&
  ok "audio-engine is byte-identical to the v0.2.36 engine (engine bytes unchanged; 7011650f9 only edits wakeword config)" || bad "audio-engine differs from v0.2.36 unexpectedly ($eng)"
[ "$eng" != "$ENG_V0235_SHA" ] &&
  ok "audio-engine differs from the v0.2.35 engine $ENG_V0235_SHA" || bad "audio-engine unchanged from v0.2.35"
[ "$(sha256sum "$PLATFORM_WT/tools/mt8163-arm32/airplay/audio_engine.c" | cut -d' ' -f1)" = \
  "$(sed -n 's/^\([0-9a-f]*\)  .*audio_engine.c$/\1/p' "$D/engine/sources.sha256")" ] &&
  ok "engine source hash recorded for platform audio_engine.c" || bad "engine source hash"
M=$D/images/boot-lidar-v2.manifest.json
[ "$(jq -r .inputs.dtb.sha256 "$M")" = "$WANT_DTB" ] && ok "image DTB is the 47feddd6 build 0e9cc4ff" || bad "image DTB $(jq -r .inputs.dtb.sha256 "$M")"
[ "$(jq -r .inputs.kernel_image.sha256 "$M")" = "$WANT_IMAGE" ] && ok "image kernel is the 47feddd6 build 272090a9" || bad "image kernel"
strings "$KERNEL/libreecho-lidar.dtb" > /tmp/v0237-dtb-strings.txt
grep -qx board-thermal /tmp/v0237-dtb-strings.txt && ok "DTB carries the board-thermal zone" || bad "DTB thermal zone"
grep -qx 'ti,tmp112' /tmp/v0237-dtb-strings.txt && ok "DTB carries the ti,tmp112 sensor" || bad "DTB ti,tmp112"
! grep -q uart-has-rtscts /tmp/v0237-dtb-strings.txt && ok "DTB has no uart-has-rtscts" || bad "DTB carries uart-has-rtscts"
python3 -B "$PLATFORM_WT/tools/mt8167-arm64/verify_lidar_dtb.py" "$KERNEL/libreecho-lidar.dtb" \
  > "$D/verify-lidar-dtb.log" 2>&1 &&
  ok "verify_lidar_dtb.py PASS ($(tr '\n' ' ' < "$D/verify-lidar-dtb.log"))" || bad "verify_lidar_dtb.py"
n_contract=$(grep -c 'lidar_recovery_image_contract=PASS' "$D/images-build.log" || true)
[ "$n_contract" = 3 ] && ok "lidar_recovery_image_contract=PASS for dev, v1, v2" || bad "recovery image contract ($n_contract/3 PASS)"
printf '%s\n' "$NEW" > /tmp/v0237-new.hex; printf '%s\n' "$OLD" > /tmp/v0237-old.hex
VFY=$P5/components/ota-control/libreecho-update-verify
"$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0237-new.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA signature new key" || bad "new-key signature"
! "$QEMU/qemu-arm-static" -L "$P5/toolchains/musl/usr/lib" "$VFY" /tmp/v0237-old.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/dev/null 2>&1 &&
  ok "OTA rejected old key" || bad "old key accepted"
grep -q "^version=$VER$" "$GEN/target.manifest" && ok "OTA manifest version=$VER" || bad "OTA manifest version"
# Wakeword feature: prebuilt payload, its manifest identity, and the daemon.
WFP=$GEN/features/wakeword/payload.squashfs
[ "$(sha256sum "$WFP" | cut -d' ' -f1)" = "$WF_PAYLOAD_SHA" ] && ok "OTA wakeword payload $WF_PAYLOAD_SHA" || bad "OTA wakeword payload"
[ "$(sha256sum "$GEN/features/wakeword/manifest.json" | cut -d' ' -f1)" = "$WF_MANIFEST_SHA" ] && ok "OTA wakeword manifest $WF_MANIFEST_SHA" || bad "OTA wakeword manifest"
waked=$(unsquashfs -cat "$WFP" usr/local/sbin/libreecho-waked | sha256sum | cut -d' ' -f1)
[ "$waked" = "$WF_WAKED_SHA" ] && ok "OTA wakeword waked $waked" || bad "OTA wakeword waked $waked"
jq -e --arg p "$WF_PAYLOAD_SHA" '.payload.sha256 == $p and .feature_id == "wakeword" and .schema_version == 1' \
  "$GEN/features/wakeword/manifest.json" >/dev/null && ok "wakeword manifest identifies its payload" || bad "wakeword manifest identity"
grep -q "feature_wakeword_daemon_sha256=$WF_WAKED_SHA" "$GEN/target.manifest" &&
  ok "OTA manifest wakeword daemon hash" || bad "OTA manifest wakeword daemon hash"
grep -q "feature_airplay2_daemon_sha256=$eng" "$GEN/target.manifest" &&
  ok "OTA manifest airplay2 daemon hash = engine" || bad "OTA manifest airplay2 daemon hash"
RELCHK=$R/private/forks/LibreEcho/tools/check-release-components.py
python3 -B "$RELCHK" --target lidar \
  --artifacts "$D/ota/lidar-lab-v$VER.ota.tar" \
  --artifacts "$D/images/boot-lidar-v2.img" \
  > "$D/check-release-components.log" 2>&1 &&
  ok "check-release-components --target lidar: $(tr '\n' ' ' < "$D/check-release-components.log")" ||
  bad "check-release-components --target lidar (see $D/check-release-components.log)"

if [ "$VERIFY_ONLY" = 1 ]; then
  ( cd "$D" && sha256sum --quiet -c SHA256SUMS ) && ok "SHA256SUMS match" || bad "SHA256SUMS mismatch"
else
python3 - "$D" "$PLATFORM_PIN" "$UI_PIN" "$UI_MANIFEST_SHA" "$VER" <<'PY'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
records = {
    'version': sys.argv[5],
    'platform_head': sys.argv[2],
    'platform_branch': 'feature/lidar-support-0.14.6',
    'platform_clean': True,
    'ui_head': sys.argv[3],
    'ui_bundle_manifest_sha256': sys.argv[4],
    'ui_bundle_reused_from_v0236': False,
    'wakeword_payload_sha256': '3d199f8b7805f4a499b380d414fdee63e0b6790f8e361dce06803eb4cba38af4',
    'wakeword_manifest_sha256': '9431c19f3c175ae296acb40604dab5f16f883cbfc6f424ae6d55d459cd448980',
    'wakeword_waked_sha256': 'd11ac4ecdde481fd4e45d58b385f76af01307576f98d32e5a7c5b84ecb12102b',
    'kernel': 'private/artifacts/phase-07/ota-v0.2.35/kernel (47feddd6b Image 272090a9, '
              'DTB 0e9cc4ff, no uart-has-rtscts)',
    'note': 'v0.2.37: 47feddd6 kernel, clean Platform 7011650f9 worktree (loudness '
            '671a2caf9 on 02ef8ad6 + LayerNorm reduced-ORT list), clean UI 29a7a0a '
            'bundle, prebuilt qemu-verified wakeword payload.',
}
files = {}
# Worktrees and staged inputs live under src/ and components/; the deliverable
# tree excludes them so build-info stays a record of the outputs.
skip = {'src', 'components', 'deps', 'ramdisk-check'}
for p in sorted(d.rglob('*')):
    if p.is_file() and p.name != 'build-info.json' and p.relative_to(d).parts[0] not in skip:
        files[str(p.relative_to(d))] = hashlib.sha256(p.read_bytes()).hexdigest()
records['files'] = files
(d / 'build-info.json').write_text(json.dumps(records, indent=2, sort_keys=True) + '\n')
print('build-info written')
PY
( cd "$D" && sha256sum images/* ota/*.ota.tar libreecho-lidar-base-* > SHA256SUMS )
fi
echo "INFO txn $(basename "$GEN")"
echo "INFO bundle $(sha256sum "$D"/ota/lidar-lab-v$VER.ota.tar | cut -d' ' -f1)"
exit $fail
