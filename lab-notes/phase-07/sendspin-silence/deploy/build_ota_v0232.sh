#!/usr/bin/env bash
# Build the v0.2.32 OTA (Platform 2278dedde + UI 715dd4f, sendspind 715dd4f,
# engine from Platform HEAD) and prove the ramdisk is a Lidar image on the
# host. Prints PASS/FAIL per contract item. Never talks to a device.
set -uo pipefail
cd /workspace/libreecho
R=$PWD
D=$R/private/artifacts/phase-07/v0232
IMG=$D/images
OTA=$D/ota
P5=$R/private/artifacts/phase-05
V2=$IMG/boot-lidar-v2.img
NEW=42a501c3845e3b5fcca86ffd4cd1ebfbfb44476546e6c3812754ba9a6c50ed18
OLD=25be6d6be3a2ac0e152a3caa463b6cf8aa6b5f13d2135b89f9a41f98b30a9a7d
WANT_SENDSPIN=36572977d9221f2389fe6deec9a8f674307da3418aa1886da74d4b02419e41e4
WANT_ENGINE=$(sha256sum "$D/engine/libreecho-audio-engine" | cut -d' ' -f1)
V0228=$R/private/artifacts/phase-06/images-step37-v0228
fail=0
ok()  { echo "PASS $*"; }
bad() { echo "FAIL $*"; fail=1; }

mkdir -p "$OTA"
python3 "$R/private/lab/phase-07/sendspin-silence/deploy/make_catalog_v0232.py" ||
  { echo "FAIL catalog"; exit 1; }

python3 private/lab/phase-05/ota/make_lab_ota.py \
  --boot-image "$V2" \
  --feature-catalog "$D/feature-catalog.json" \
  --release lidar-lab-v0.2.32 --version 0.2.32 \
  --update-channel dev --service-profile production \
  --signing-key "$P5/ota/lab-key/ed25519-seed.hex" \
  --public-key "$P5/ota/lab-key/ed25519-public.hex" \
  --output "$OTA/lidar-lab-v0.2.32.ota.tar" > "$OTA/ota-build.log" 2>&1 ||
  { echo "FAIL ota build"; tail -5 "$OTA/ota-build.log"; exit 1; }

size=$(stat -c %s "$V2" 2>/dev/null)
[ "$size" = 16777216 ] && ok "boot.img size 16777216" || bad "boot.img size $size"
head -c 8 "$V2" | grep -q 'ANDROID!' && ok "boot.img ANDROID! magic" || bad "boot.img magic"
echo "INFO boot-lidar-v2.img sha256 $(sha256sum "$V2" | cut -d' ' -f1)"

ramdisk=$IMG/boot-lidar-v2.ramdisk.cpio.xz
member=$(xz -dc "$ramdisk" | cpio -t --quiet 2>/dev/null | grep -i 'ota-public-key.hex' | head -1)
got=$(xz -dc "$ramdisk" | cpio -i --to-stdout --quiet "$member" 2>/dev/null | tr -d '[:space:]')
[ "$got" = "$NEW" ] && ok "ramdisk ota-public-key.hex == new key" || bad "ramdisk key $got"

grep -q "source_commit=715dd4fec03aedbf4381aa3ca4b55b840ee6da45" \
  "$R/private/artifacts/phase-07/components-715dd4f/ui-bundle/bundle/share/libreecho/ui-manifest.txt" &&
  ok "ui-manifest source_commit=715dd4f" || bad "ui-manifest source_commit"

PS=$(ls "$D"/libreecho-lidar-base-airplay2-*.payload.squashfs)
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-sendspind | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_SENDSPIN" ] && ok "payload libreecho-sendspind $v" || bad "payload sendspind $v"
v=$(unsquashfs -cat "$PS" usr/local/sbin/libreecho-audio-engine | sha256sum | cut -d' ' -f1)
[ "$v" = "$WANT_ENGINE" ] && ok "payload libreecho-audio-engine $v" || bad "engine $v"

# --- Lidar image proof, straight from the ramdisk -------------------------
rd=$D/ramdisk-check
mkdir -p "$rd"
( cd "$rd" && xz -dc "$ramdisk" | cpio -id --quiet ) 2>/dev/null

init_text=$(cat "$rd/init" 2>/dev/null)
case "$init_text" in
  *"        lidar) TARGET_SLUG=lidar ;;"*) ok "init accepts target_id=lidar" ;;
  *) bad "init lacks the lidar target case" ;;
esac

boot_init=$(cat "$rd/libreecho-init" 2>/dev/null)
case "$boot_init" in
  *"        lidar) TARGET_SLUG=lidar ;;"*) ok "libreecho-init load_image_target has the lidar case" ;;
  *) bad "libreecho-init lacks the lidar map" ;;
esac
case "$boot_init" in
  *'"${TARGET_ID:-}" = lidar'*'libreecho-vendor-import'*)
    ok "libreecho-init imports vendor assets for lidar" ;;
  *) bad "libreecho-init lacks the lidar vendor import" ;;
esac
case "$boot_init" in
  *mt7668_patch_e2_hdr.bin*mt7668pr2h.bin*) ok "libreecho-init loads the MT7668 firmware" ;;
  *) bad "libreecho-init lacks the MT7668 firmware path" ;;
esac

target=$(head -n 1 "$rd/etc/libreecho/target" 2>/dev/null)
[ "$target" = "target_id=lidar" ] && ok "/etc/libreecho/target says target_id=lidar" || bad "/etc/libreecho/target: $target"

ramdisk_member=$(cd "$rd" && find . -name 'libreecho-reconcile-features' | head -1)
grep -q 'feature-services-continued-after-topology-failure' "$rd/${ramdisk_member#./}" 2>/dev/null &&
  ok "ramdisk reconciler carries the topology fix" || bad "ramdisk reconciler fix missing"

# --- OTA signature checks -------------------------------------------------
GEN=$(ls -d "$OTA"/generations/txn-* 2>/dev/null | head -1)
QV=$P5/host-tools/qemu/usr/bin/qemu-arm-static
VFY=$P5/components/ota-control/libreecho-update-verify
LIBS=$P5/toolchains/musl/usr/lib
printf '%s\n' "$NEW" > /tmp/v0232-new-pub.hex
printf '%s\n' "$OLD" > /tmp/v0232-old-pub.hex
"$QV" -L "$LIBS" "$VFY" /tmp/v0232-new-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/v0232-sig-new.log 2>&1
[ $? -eq 0 ] && ok "OTA manifest signature verifies with new key" || { bad "new-key signature"; tail -3 /tmp/v0232-sig-new.log; }
"$QV" -L "$LIBS" "$VFY" /tmp/v0232-old-pub.hex "$GEN/target.manifest" "$GEN/target.manifest.sig" >/tmp/v0232-sig-old.log 2>&1
[ $? -ne 0 ] && ok "OTA manifest rejected with old key" || bad "old key accepted"

# --- Lidar-relevant comparison against the working v0.2.28 ramdisk --------
old=$D/ramdisk-v0228
mkdir -p "$old"
( cd "$old" && xz -dc "$V0228/boot-lidar-v2.ramdisk.cpio.xz" | cpio -id --quiet ) 2>/dev/null
( cd "$rd" && find . -type f -o -type l | LC_ALL=C sort | while read -r f; do
    printf '%s %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "${f#./}"; done ) > "$D/tree-v0232.txt"
( cd "$old" && find . -type f -o -type l | LC_ALL=C sort | while read -r f; do
    printf '%s %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "${f#./}"; done ) > "$D/tree-v0228.txt"
python3 - "$D/tree-v0228.txt" "$D/tree-v0232.txt" "$D/lidar-diff.txt" <<'PY'
import re, sys
old = dict(reversed(line.split(None, 1)) for line in open(sys.argv[1]).read().splitlines())
new = dict(reversed(line.split(None, 1)) for line in open(sys.argv[2]).read().splitlines())
pat = re.compile(r'(libreecho-init$|/init$|reconcile|target$|audio-profile|wpa|tiny(play|cap|mix)|mt7668|vendor|wifi|WIFI|libreecho-update)')
names = sorted(n for n in old.keys() | new.keys() if pat.search(n))
rows = []
for n in names:
    o, w = old.get(n), new.get(n)
    if o is None: rows.append(f'ADDED    {n}')
    elif w is None: rows.append(f'REMOVED  {n}')
    elif o != w: rows.append(f'CHANGED  {n}')
with open(sys.argv[3], 'w') as out:
    out.write('\n'.join(rows) + ('\n' if rows else 'no differences\n'))
print(len(rows))
PY
echo "INFO lidar-relevant diffs: $(wc -l < "$D/lidar-diff.txt") (see $D/lidar-diff.txt)"

echo "INFO txn id $(basename "$GEN")"
echo "INFO bundle sha256 $(sha256sum "$OTA"/lidar-lab-v0.2.32.ota.tar | cut -d' ' -f1)"
exit $fail
