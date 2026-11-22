#!/usr/bin/env bash
# Step 37 rebuild pipeline: waits for the single-owned musl toolchain build,
# rebuilds the phase-05 components (recording hash comparisons), builds the
# f43dade UI bundle, the step-36-thermal images and the v0.2.28 OTA.
# Every stage logs to this directory; a failure is recorded and the pipeline
# stops so the evidence stays readable.
set -uo pipefail
cd /workspace/libreecho
R=experiments/phase-06/hw-20261121/step37-rekey
ART=artifacts/phase-06
P5=artifacts/phase-05

step() { printf '%s == %s\n' "$(date +%T)" "$*" | tee -a "$R/run-all.log"; }

exec 9>/tmp/libreecho-toolchain.lock
step "waiting for toolchain lock"
flock 9
step "toolchain lock acquired"

: > "$R/components-build.log"
for t in musl-loader busybox libsodium bootctl update-verify adbd mdns; do
  step "component $t"
  bash experiments/phase-05/build_components.sh "$t" >> "$R/components-build.log" 2>&1
  rc=$?
  echo "rc=$rc $t" >> "$R/components-build.log"
  [ "$rc" -eq 0 ] || { step "FAIL component $t rc=$rc"; exit 10; }
done

{
  echo "# rebuild vs experiments/phase-05/components.md (2026-11-22 step37-rekey)"
  check() { actual=$(sha256sum "$2" 2>/dev/null | cut -d' ' -f1); if [ "$actual" = "$1" ]; then echo "MATCH   $3 $actual"; else echo "MISMATCH $3 expected=$1 actual=${actual:-missing}"; fi; }
  check 47ed5c21aca427b893859aa9ee1ca7a0ce9494f4e0e7dd6ee4136d9766f9f060 "$P5/components/musl/ld-musl-armhf.so.1" musl-loader
  check fed10234e996e9647d753ab5ee196d69f465ece1fe9962e401a0df7ef96cf3de "$P5/components/busybox/busybox" busybox
  check fe2407251fcc7c89300a264d73c257cb609750ef5f7a6eec36606b0d259613ff "$P5/components/libsodium/lib/libsodium.a" libsodium
  check 4f19413de86355809051b316e99b6334198a5fc8ce3889b357f90fb8761b6224 "$P5/components/ota-control/libreecho-bootctl" bootctl
  check bfc00578d1006f589d257a796f688f7bdd729fe4cf7bbbe2e271dc95ff557aaf "$P5/components/ota-control/libreecho-update-verify" update-verify
  check 3651b39f524bd8f07f1a9b85e00ec284017b5558788a3715d8aa08132866b6e0 "$P5/components/adbd/adbd" adbd
  check e700b693905c74b768f4a2db50430a8c7bd6303c98a3e0cd367e5f6a9195ec65 "$P5/components/mdns-runtime/manifest.json" mdns
} | tee "$R/hash-compare.txt"

step "ui bundle f43dade"
bash "$R/build_components_step37.sh" ui >> "$R/ui-step37.log" 2>&1
rc=$?
step "ui rc=$rc"
[ "$rc" -eq 0 ] || exit 11

step "images (kernel-step36-thermal, ui f43dade)"
KERNEL_DIR="$ART/kernel-step36-thermal" \
UI_BUNDLE_DIR="$ART/components-step37-v0228/ui-bundle/bundle" \
UI_COMMIT=f43dadef8d6616812c53b38b1e3690491a1cacce \
UI_DIFF_SHA256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 \
  bash experiments/phase-06/build_images.sh --output-dir "$ART/images-step37-v0228" \
  >> "$R/images-step37.log" 2>&1
rc=$?
step "images rc=$rc"
[ "$rc" -eq 0 ] || exit 12

step "ota v0.2.28"
python3 experiments/phase-05/ota/make_lab_ota.py \
  --boot-image "$ART/images-step37-v0228/boot-lidar-v2.img" \
  --feature-catalog "$ART/features-airplay2-latency/feature-catalog.json" \
  --release lidar-lab-v0.2.28 --version 0.2.28 \
  --update-channel dev --service-profile production \
  --signing-key "$P5/ota/lab-key/ed25519-seed.hex" \
  --public-key "$P5/ota/lab-key/ed25519-public.hex" \
  --output "$ART/ota-step37-v0228/lidar-lab-v0.2.28.ota.tar" \
  >> "$R/ota-step37.log" 2>&1
rc=$?
step "ota rc=$rc"
[ "$rc" -eq 0 ] || exit 13
step "DONE_ALL"
