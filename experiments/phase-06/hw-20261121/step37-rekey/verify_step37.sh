#!/usr/bin/env bash
# Step 37 verification, host-only. Prints PASS/FAIL lines for each contract
# item; exits nonzero if any check fails.
set -uo pipefail
cd /workspace/libreecho
IMG=artifacts/phase-06/images-step37-v0228
OTA=artifacts/phase-06/ota-step37-v0228
P5=artifacts/phase-05
V2=$IMG/boot-lidar-v2.img
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
fail=0
ok()   { echo "PASS $*"; }
bad()  { echo "FAIL $*"; fail=1; }

size=$(stat -c %s "$V2" 2>/dev/null)
[ "$size" = 16777216 ] && ok "boot.img size 16777216" || bad "boot.img size $size"
head -c 8 "$V2" | grep -q 'ANDROID!' && ok "boot.img ANDROID! magic" || bad "boot.img magic"
echo "INFO boot-lidar-v2.img sha256 $(sha256sum "$V2" | cut -d' ' -f1)"

# ota-public-key.hex inside the boot ramdisk
keyfile=$IMG/boot-lidar-v2.ramdisk.cpio.xz
if [ -f "$keyfile" ]; then
  member=$(xz -dc "$keyfile" | cpio -t --quiet 2>/dev/null | grep -i 'ota-public-key.hex' | head -1)
  if [ -n "$member" ]; then
    got=$(xz -dc "$keyfile" | cpio -i --to-stdout --quiet "$member" 2>/dev/null | tr -d '[:space:]')
    [ "$got" = "$NEW" ] && ok "ramdisk ota-public-key.hex == new key" || bad "ramdisk key $got"
  else
    bad "ota-public-key.hex not found in ramdisk"
  fi
else
  bad "missing $keyfile"
fi

# Boot kernel = 512-byte MediaTek "KERNEL" header + Image.gz + appended DTBs (19). Check the
# gunzipped Image equals the step-36-thermal Image and the Lidar DTB carries board-thermal.
python3 - "$V2" artifacts/phase-06/kernel-step36-thermal/Image <<'PY'
import hashlib, struct, sys, zlib
img = open(sys.argv[1], 'rb').read()
want = open(sys.argv[2], 'rb').read()
ksize, = struct.unpack_from('<I', img, 8)
page, = struct.unpack_from('<I', img, 36)
kernel = img[page:page + ksize]
assert kernel[:4] == bytes.fromhex('88168858'), 'missing MTK header'
n, = struct.unpack_from('<I', kernel, 4)
d = zlib.decompressobj(31)
plain = d.decompress(kernel[512:512 + n]) + d.flush()
dtbs, o, tail = [], 0, d.unused_data
while tail[o:o + 4] == b'\xd0\x0d\xfe\xed':
    size, = struct.unpack_from('>I', tail, o + 4); dtbs.append(tail[o:o + size]); o += size
ok = plain == want
print("PASS" if ok else "FAIL", f"boot.img kernel Image {hashlib.sha256(plain).hexdigest()} "
      f"want {hashlib.sha256(want).hexdigest()}")
thermal = sum(b'board-thermal' in x for x in dtbs)
print("PASS" if thermal == 1 else "FAIL", f"appended DTBs {len(dtbs)}, with board-thermal {thermal}")
sys.exit(0 if ok and thermal == 1 else 1)
PY
[ $? -eq 0 ] || fail=1

# DTB board-thermal trips
DTC=/tmp/lidar-618/scripts/dtc/dtc
if [ -x "$DTC" ]; then
  "$DTC" -I dtb -O dts artifacts/phase-06/kernel-step36-thermal/libreecho-lidar.dtb > /tmp/step37-lidar.dts 2>/dev/null
  if grep -q 'board-thermal' /tmp/step37-lidar.dts; then
    ok "DTB has board-thermal node"
    grep -A6 'board-thermal' /tmp/step37-lidar.dts | sed 's/^/INFO /' | head -40
  else
    bad "DTB lacks board-thermal node"
  fi
else
  bad "no dtc at $DTC"
fi

# OTA signature: new key accepts, old key rejects
GEN=$(ls -d "$OTA"/generations/txn-* 2>/dev/null | head -1)
QV=$P5/host-tools/qemu/usr/bin/qemu-arm-static
VFY=$P5/components/ota-control/libreecho-update-verify
LIBS=$P5/toolchains/musl/usr/lib
if [ -n "$GEN" ] && [ -x "$VFY" ]; then
  printf '%s\n' "$NEW" > /tmp/step37-new-pub.hex
  printf '%s\n' "$OLD" > /tmp/step37-old-pub.hex
  "$QV" -L "$LIBS" "$VFY" /tmp/step37-new-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/step37-sig-new.log 2>&1
  [ $? -eq 0 ] && ok "OTA manifest signature verifies with new key" || { bad "new-key signature rejected"; cat /tmp/step37-sig-new.log; }
  "$QV" -L "$LIBS" "$VFY" /tmp/step37-old-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/step37-sig-old.log 2>&1
  [ $? -ne 0 ] && ok "OTA manifest signature rejected with old key" || bad "old key accepted the signature"
  echo "INFO txn id $(basename "$GEN")"
else
  bad "missing generation tree or verifier"
fi

# micd provenance from the UI bundle
UM=artifacts/phase-06/components-step37-v0228/ui-bundle/bundle/share/libreecho/ui-manifest.txt
if [ -f "$UM" ]; then
  ok "ui-manifest present ($(sha256sum "$UM" | cut -d' ' -f1))"
  grep -E 'micd' "$UM" | sed 's/^/INFO /' | head -5
else
  bad "missing ui-manifest"
fi
exit $fail
