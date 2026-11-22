#!/usr/bin/env bash
# Build the three Phase 5 Lidar boot images from the components that
# build_components.sh produced. Host-only: never talks to a device.
#
#   dev  development + diagnostic, cmdline marker libreecho.lab=dev
#   v1   ota + production, dev channel, lab key, marker libreecho.lab=v1
#   v2   same as v1 with marker libreecho.lab=v2 (the OTA payload)
#
# The marker is only a label in /proc/cmdline, so the hardware test can tell
# which image is running in which slot.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
ART="$ROOT/artifacts/phase-05"
COMP="$ART/components"
KERNEL="$ART/kernel"
LIDAR="$ROOT/repos/LibreEcho-Platform/tools/mt8167-arm64"
OUT="$ART/images"
QEMU_DIR="$ART/host-tools/qemu/usr/bin"

UI_COMMIT=b39af308f0d32e5ae56986d4c603195ab524dbc4
UI_DIFF_SHA256=e510bcf6aef955f75f895dc1fdc0fd829d25b3d310cffbc19a9cda8f7a376ee1

sha() { sha256sum "$1" | awk '{print $1}'; }

mkdir -p "$OUT"
build() {
  local name="$1" image="$2" service="$3"
  shift 3
  rm -f "$OUT/boot-lidar-$name".*
  PATH="$QEMU_DIR:$PATH" python3 "$LIDAR/build_recovery_image.py" \
    --stock-boot "$ROOT/dumps/20261110-lidar-readback/boot_a.bin" \
    --kernel-image "$KERNEL/Image" --kernel-config "$KERNEL/.config" \
    --dtb "$KERNEL/libreecho-lidar.dtb" \
    --expected-dtb-sha256 "$(sha "$KERNEL/libreecho-lidar.dtb")" \
    --cmdline-append "libreecho.lab=$name" \
    --adbd "$COMP/adbd/adbd" --adbd-source-metadata "$COMP/adbd/adbd-source.json" \
    --busybox "$COMP/busybox/busybox" \
    --expected-busybox-sha256 "$(sha "$COMP/busybox/busybox")" \
    --musl-loader "$COMP/musl/ld-musl-armhf.so.1" \
    --expected-musl-loader-sha256 "$(sha "$COMP/musl/ld-musl-armhf.so.1")" \
    --image-profile "$image" --service-profile "$service" \
    --update-channel dev \
    --bootctl "$COMP/ota-control/libreecho-bootctl" \
    --update-verifier "$COMP/ota-control/libreecho-update-verify" \
    --ota-public-key "$ART/ota/lab-key/ed25519-public.hex" \
    "$@" \
    --output "$OUT/boot-lidar-$name.img"
}

UI=(--ui-bundle "$COMP/ui-bundle/bundle"
    --ui-source "$ART/toolchains/sources/libreecho-ui"
    --expected-ui-commit "$UI_COMMIT" --expected-ui-diff-sha256 "$UI_DIFF_SHA256")

build dev development diagnostic "${UI[@]}"
build v1 ota production "${UI[@]}" --mdns-runtime "$COMP/mdns-runtime"
build v2 ota production "${UI[@]}" --mdns-runtime "$COMP/mdns-runtime"

( cd "$OUT" && sha256sum boot-lidar-*.img > SHA256SUMS )


verify() {
  local name="$1" image="$2" service="$3"
  shift 3
  python3 "$LIDAR/verify_recovery_image.py" \
    --stock-boot "$ROOT/dumps/20261110-lidar-readback/boot_a.bin" \
    --kernel-image "$KERNEL/Image" --kernel-config "$KERNEL/.config" \
    --dtb "$KERNEL/libreecho-lidar.dtb" \
    --expected-dtb-sha256 "$(sha "$KERNEL/libreecho-lidar.dtb")" \
    --ramdisk "$OUT/boot-lidar-$name.ramdisk.cpio.xz" \
    --manifest "$OUT/boot-lidar-$name.manifest.json" \
    --boot-image "$OUT/boot-lidar-$name.img" \
    --expected-boot-sha256 "$(sha "$OUT/boot-lidar-$name.img")" \
    --cmdline-append "libreecho.lab=$name" \
    --expected-busybox-sha256 "$(sha "$COMP/busybox/busybox")" \
    --expected-musl-loader-sha256 "$(sha "$COMP/musl/ld-musl-armhf.so.1")" \
    --expected-bootctl-sha256 "$(sha "$COMP/ota-control/libreecho-bootctl")" \
    --expected-update-verifier-sha256 "$(sha "$COMP/ota-control/libreecho-update-verify")" \
    --expected-ota-public-key-sha256 "$(sha "$ART/ota/lab-key/ed25519-public.hex")" \
    --expected-ui-manifest-sha256 "$(sha "$COMP/ui-bundle/bundle/share/libreecho/ui-manifest.txt")" \
    --expected-ui-commit "$UI_COMMIT" --expected-ui-diff-sha256 "$UI_DIFF_SHA256" \
    --image-profile "$image" --service-profile "$service" \
    --feature-policy preserve --update-channel dev "$@"
}
MDNS_PIN=(--expected-mdns-runtime-manifest-sha256 "$(cat "$COMP/mdns-runtime/manifest.sha256")")
verify dev development diagnostic
verify v1 ota production "${MDNS_PIN[@]}"
verify v2 ota production "${MDNS_PIN[@]}"