#!/usr/bin/env bash
# Build the true "v0.2.28 + Sendspin fix" OTA v0.2.31 and verify it on the host:
# Platform fix/lidar-efr32-nodes 32f3dbd, UI d63a58a, airplay2 payload cd5e9d60
# (sendspind 4198d62a). No hash patches. Prints PASS/FAIL per contract item.
set -uo pipefail
cd /workspace/libreecho
R=$PWD
A=$R/private/artifacts/phase-07/features-sendspin-fix
IMG=$R/private/artifacts/phase-07/images-v0231efr
OTA=$R/private/artifacts/phase-07/ota-v0231efr
V28=$R/private/artifacts/phase-06/images-step37-v0228
P5=$R/private/artifacts/phase-05
V2=$IMG/boot-lidar-v2.img
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
WANT_SENDSPIN=4198d62a6da67f05d6dac02f97c9f512d272e6803e7c2021d55ad450f5770fe0
WANT_ENGINE=84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35
WANT_INIT=0c673386fac1e9e92ca17d43d177781fdf1d2e53fae62aca327cfe139e2fb389
fail=0
ok()  { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }
mkdir -p "$OTA"

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
got=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet etc/libreecho/ota-public-key.hex 2>/dev/null | tr -d '[:space:]')
[ "$got" = "$NEW" ] && ok "ramdisk ota-public-key.hex == new key" || bad "ramdisk key $got"

initv=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet init 2>/dev/null | sha256sum | cut -d' ' -f1)
[ "$initv" = "$WANT_INIT" ] && ok "ramdisk init $initv (v0.2.28 bytes)" || bad "ramdisk init $initv"
init_text=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet init 2>/dev/null)
case "$init_text" in
  *"lidar) TARGET_SLUG=lidar ;;"*) ok "ramdisk init accepts target_id=lidar" ;;
  *) bad "ramdisk init lacks the lidar target case" ;;
esac

grep -q "source_commit=d63a58acadb78a223241ea26091778de6641c7ec" \
  "$A/../components-sendspin-fix/ui-bundle/bundle/share/libreecho/ui-manifest.txt" &&
  ok "ui-manifest source_commit=d63a58a" || bad "ui-manifest source_commit"

PS=$(ls "$A"/libreecho-lidar-base-airplay2-*.payload.squashfs)
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_SENDSPIN" ] && ok "payload libreecho-sendspind $v" || bad "payload sendspind $v"
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_ENGINE" ] && ok "payload audio-engine $v" || bad "engine $v"

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
