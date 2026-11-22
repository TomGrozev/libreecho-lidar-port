#!/usr/bin/env bash
# Host-only verification of the sendspin-fix image, payload and OTA. Prints
# PASS/FAIL lines per contract item; exits nonzero on any failure.
set -uo pipefail
cd /workspace/libreecho
IMG=artifacts/phase-07/images-sendspin-fix
OTA=artifacts/phase-07/ota-sendspin-fix
PAY=artifacts/phase-07/features-sendspin-fix
P5=artifacts/phase-05
V2=$IMG/boot-lidar-v2.img
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
WANT_SENDSPIN=4198d62a6da67f05d6dac02f97c9f512d272e6803e7c2021d55ad450f5770fe0
WANT_ENGINE=84e5ae9bbf6135acd076aeec013c1370f75f6cb9b07e96c9a14b07c5cdeb2c35
fail=0
ok()  { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }

size=$(stat -c %s "$V2" 2>/dev/null)
[ "$size" = 16777216 ] && ok "boot.img size 16777216" || bad "boot.img size $size"
head -c 8 "$V2" | grep -q 'ANDROID!' && ok "boot.img ANDROID! magic" || bad "boot.img magic"
echo "INFO boot-lidar-v2.img sha256 $(sha256sum "$V2" | cut -d' ' -f1)"

ramdisk=$IMG/boot-lidar-v2.ramdisk.cpio.xz
member=$(xz -dc "$ramdisk" | cpio -t --quiet 2>/dev/null | grep -i 'ota-public-key.hex' | head -1)
got=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet "$member" 2>/dev/null | tr -d '[:space:]')
[ "$got" = "$NEW" ] && ok "ramdisk ota-public-key.hex == new key" || bad "ramdisk key $got"

policy=$IMG/boot-lidar-v2.img
echo "INFO ui-manifest sha256 $(sha256sum artifacts/phase-07/components-sendspin-fix/ui-bundle/bundle/share/libreecho/ui-manifest.txt | cut -d' ' -f1)"
grep -q "source_commit=d63a58acadb78a223241ea26091778de6641c7ec" \
  artifacts/phase-07/components-sendspin-fix/ui-bundle/bundle/share/libreecho/ui-manifest.txt &&
  ok "ui-manifest source_commit=d63a58a" || bad "ui-manifest source_commit"

PS=$(ls "$PAY"/libreecho-lidar-base-airplay2-*.payload.squashfs)
[ "$(sha256sum "$PS" | cut -d' ' -f1)" = cd5e9d60b6482cf09db024b7fb5477dae320b8dcd8dae8a9bd6cb08a7d6c09eb ] &&
  ok "payload squashfs sha256 cd5e9d60" || bad "payload squashfs hash"
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_SENDSPIN" ] && ok "payload libreecho-sendspind $v" || bad "payload sendspind $v"
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_ENGINE" ] && ok "payload audio-engine unchanged $v" || bad "engine $v"

GEN=$(ls -d "$OTA"/generations/txn-* 2>/dev/null | head -1)
QV=$P5/host-tools/qemu/usr/bin/qemu-arm-static
VFY=$P5/components/ota-control/libreecho-update-verify
LIBS=$P5/toolchains/musl/usr/lib
printf '%s\n' "$NEW" > /tmp/ss-new-pub.hex
printf '%s\n' "$OLD" > /tmp/ss-old-pub.hex
"$QV" -L "$LIBS" "$VFY" /tmp/ss-new-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/ss-sig-new.log 2>&1
[ $? -eq 0 ] && ok "OTA manifest signature verifies with new key" || { bad "new-key signature"; cat /tmp/ss-sig-new.log; }
"$QV" -L "$LIBS" "$VFY" /tmp/ss-old-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/ss-sig-old.log 2>&1
[ $? -ne 0 ] && ok "OTA manifest rejected with old key" || bad "old key accepted"
echo "INFO txn id $(basename "$GEN")"
echo "INFO bundle sha256 $(sha256sum "$OTA"/lidar-lab-v0.2.29.ota.tar | cut -d' ' -f1)"
exit $fail
