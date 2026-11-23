#!/usr/bin/env bash
# Build the v0.2.31 OTA: v0.2.30 contents plus the load_image_target lidar case
# (Wi-Fi bring-up gate). Verifies it on the host. Prints PASS/FAIL per item.
set -uo pipefail
cd /workspace/libreecho
R=$PWD
A=$R/private/artifacts/phase-07/features-715dd4f
IMG=$R/private/artifacts/phase-07/images-v0231
OTA=$R/private/artifacts/phase-07/ota-v0231
P5=$R/private/artifacts/phase-05
V2=$IMG/boot-lidar-v2.img
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
WANT_SENDSPIN=36572977d9221f2389fe6deec9a8f674307da3418aa1886da74d4b02419e41e4
WANT_ENGINE=84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35
WANT_INIT=b7703690f6fb1dadfcd1406f1336803c2f48c97983df48bcb24a49dd24d09cb5
fail=0
ok()  { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }
mkdir -p "$OTA"

python3 "$R/private/lab/phase-07/sendspin-silence/deploy/make_catalog_715dd4f.py" ||
  { echo "FAIL catalog"; exit 1; }

python3 private/lab/phase-05/ota/make_lab_ota.py \
  --boot-image "$V2" \
  --feature-catalog "$A/feature-catalog.json" \
  --release lidar-lab-v0.2.31 --version 0.2.31 \
  --update-channel dev --service-profile production \
  --signing-key "$P5/ota/lab-key/ed25519-seed.hex" \
  --public-key "$P5/ota/lab-key/ed25519-public.hex" \
  --output "$OTA/lidar-lab-v0.2.31.ota.tar" > "$OTA/ota-build.log" 2>&1 ||
  { echo "FAIL ota build"; tail -5 "$OTA/ota-build.log"; exit 1; }

size=$(stat -c %s "$V2" 2>/dev/null)
[ "$size" = 16777216 ] && ok "boot.img size 16777216" || bad "boot.img size $size"
head -c 8 "$V2" | grep -q 'ANDROID!' && ok "boot.img ANDROID! magic" || bad "boot.img magic"
echo "INFO boot-lidar-v2.img sha256 $(sha256sum "$V2" | cut -d' ' -f1)"

ramdisk=$IMG/boot-lidar-v2.ramdisk.cpio.xz
member=$(xz -dc "$ramdisk" | cpio -t --quiet 2>/dev/null | grep -i 'ota-public-key.hex' | head -1)
got=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet "$member" 2>/dev/null | tr -d '[:space:]')
[ "$got" = "$NEW" ] && ok "ramdisk ota-public-key.hex == new key" || bad "ramdisk key $got"

initv=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet init 2>/dev/null | sha256sum | cut -d' ' -f1)
[ "$initv" = "$WANT_INIT" ] && ok "ramdisk init $initv" || bad "ramdisk init $initv"
init_text=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet init 2>/dev/null)
case "$init_text" in
  *"        lidar) TARGET_SLUG=lidar ;;"*)
    ok "ramdisk init accepts target_id=lidar" ;;
  *)
    bad "ramdisk init lacks the lidar target case" ;;
esac

grep -q "source_commit=715dd4fec03aedbf4381aa3ca4b55b840ee6da45" \
  "$R/private/artifacts/phase-07/components-715dd4f/ui-bundle/bundle/share/libreecho/ui-manifest.txt" &&
  ok "ui-manifest source_commit=715dd4f" || bad "ui-manifest source_commit"

PS=$(ls "$A"/libreecho-lidar-base-airplay2-*.payload.squashfs)
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_SENDSPIN" ] && ok "payload libreecho-sendspind $v" || bad "payload sendspind $v"
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_ENGINE" ] && ok "payload audio-engine unchanged $v" || bad "engine $v"

ramdisk_member=$(xz -dc "$ramdisk" | cpio -t --quiet 2>/dev/null | grep -E 'libreecho-reconcile-features' | head -1)
xz -dc "$ramdisk" | cpio -i --to-stdout --quiet "$ramdisk_member" 2>/dev/null |
  grep -q 'feature-services-continued-after-topology-failure' &&
  ok "ramdisk reconciler carries the topology fix" || bad "ramdisk reconciler fix missing"

GEN=$(ls -d "$OTA"/generations/txn-* 2>/dev/null | head -1)
QV=$P5/host-tools/qemu/usr/bin/qemu-arm-static
VFY=$P5/components/ota-control/libreecho-update-verify
LIBS=$P5/toolchains/musl/usr/lib
printf '%s\n' "$NEW" > /tmp/ss-new-pub.hex
printf '%s\n' "$OLD" > /tmp/ss-old-pub.hex
"$QV" -L "$LIBS" "$VFY" /tmp/ss-new-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/ss-sig-new.log 2>&1
[ $? -eq 0 ] && ok "OTA manifest signature verifies with new key" || { bad "new-key signature"; tail -3 /tmp/ss-sig-new.log; }
"$QV" -L "$LIBS" "$VFY" /tmp/ss-old-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/ss-sig-old.log 2>&1
[ $? -ne 0 ] && ok "OTA manifest rejected with old key" || bad "old key accepted"
echo "INFO txn id $(basename "$GEN")"
echo "INFO bundle sha256 $(sha256sum "$OTA"/lidar-lab-v0.2.31.ota.tar | cut -d' ' -f1)"
exit $fail
