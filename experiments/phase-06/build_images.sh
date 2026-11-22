#!/usr/bin/env bash
# Build and verify the three Phase 6 Lidar boot images. Host-only: never talks
# to a device.
#
#   dev  development + diagnostic, cmdline marker libreecho.lab=p6-dev
#   v1   ota + production, dev channel, lab key, marker libreecho.lab=p6-v1
#   v2   same as v1 with marker libreecho.lab=p6-v2 (the OTA payload)
#
#   --output-dir DIR  write the images and SHA256SUMS to DIR instead of
#                     artifacts/phase-06/images (a parallel image set).
#
# Phase 6 sources: the 6.18 kernel (audio and MT7668 built in), the
# feature/lidar-support Platform builder (Lidar Wi-Fi firmware, vendor import,
# audio profile) and the feature/lidar-audio UI bundle.  Reused unchanged:
# phase-05 musl, BusyBox, adbd, the OTA helpers and the mDNS runtime.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
ART="$ROOT/artifacts/phase-06"
P5="$ROOT/artifacts/phase-05"
COMP="$ART/components"
P5COMP="$P5/components"
KERNEL="${KERNEL_DIR:-$ART/kernel}"
FIRMWARE="$ART/firmware"
LIDAR="$ROOT/repos/LibreEcho-Platform/tools/mt8167-arm64"
UI_SOURCE="$ROOT/repos/LibreEcho-UI"
UI_BUNDLE="${UI_BUNDLE_DIR:-$COMP/ui-bundle/bundle}"
OUT="$ART/images"
QEMU_DIR="$P5/host-tools/qemu/usr/bin"

UI_COMMIT="${UI_COMMIT:-e564bf56977527b5378f1b4f0e60bc16535428a5}"
UI_DIFF_SHA256="${UI_DIFF_SHA256:-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855}"

usage() { echo "usage: $0 [--output-dir DIR]" >&2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir) [[ $# -ge 2 ]] || { usage; exit 2; }; OUT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

sha() { sha256sum "$1" | awk '{print $1}'; }
need_file() { [[ -f "$1" ]] || { echo "ERROR: missing input: $1" >&2; exit 1; }; }

for input in "$KERNEL/Image" "$KERNEL/config" "$KERNEL/libreecho-lidar.dtb" \
    "$FIRMWARE/mt7668pr2h.bin" "$FIRMWARE/LICENCE.mediatek" \
    "$UI_BUNDLE/share/libreecho/ui-manifest.txt" \
    "$ROOT/dumps/20261110-lidar-readback/boot_a.bin"; do
  need_file "$input"
done

mkdir -p "$OUT"

WPA="$COMP/wpa-supplicant/wpa_supplicant"
AUDIO="$COMP/audio-tools"

build() {
  local name="$1" image="$2" service="$3"
  shift 3
  rm -f "$OUT/boot-lidar-$name".*
  PATH="$QEMU_DIR:$PATH" python3 "$LIDAR/build_recovery_image.py" \
    --stock-boot "$ROOT/dumps/20261110-lidar-readback/boot_a.bin" \
    --kernel-image "$KERNEL/Image" --kernel-config "$KERNEL/config" \
    --dtb "$KERNEL/libreecho-lidar.dtb" \
    --expected-dtb-sha256 "$(sha "$KERNEL/libreecho-lidar.dtb")" \
    --cmdline-append "libreecho.lab=p6-$name" \
    --adbd "$P5COMP/adbd/adbd" --adbd-source-metadata "$P5COMP/adbd/adbd-source.json" \
    --busybox "$P5COMP/busybox/busybox" \
    --expected-busybox-sha256 "$(sha "$P5COMP/busybox/busybox")" \
    --musl-loader "$P5COMP/musl/ld-musl-armhf.so.1" \
    --expected-musl-loader-sha256 "$(sha "$P5COMP/musl/ld-musl-armhf.so.1")" \
    --image-profile "$image" --service-profile "$service" \
    --update-channel dev \
    --bootctl "$P5COMP/ota-control/libreecho-bootctl" \
    --update-verifier "$P5COMP/ota-control/libreecho-update-verify" \
    --ota-public-key "$P5/ota/lab-key/ed25519-public.hex" \
    --wifi-patch "$FIRMWARE/mt7668pr2h.bin" \
    --wifi-licence "$FIRMWARE/LICENCE.mediatek" \
    --wpa-supplicant "$WPA" \
    --tinyplay "$AUDIO/tinyplay" --tinycap "$AUDIO/tinycap" \
    --tinymix "$AUDIO/tinymix" \
    "$@" \
    --output "$OUT/boot-lidar-$name.img"
}

UI=(--ui-bundle "$UI_BUNDLE"
    --ui-source "$UI_SOURCE"
    --expected-ui-commit "$UI_COMMIT" --expected-ui-diff-sha256 "$UI_DIFF_SHA256")

build dev development diagnostic "${UI[@]}"
build v1 ota production "${UI[@]}" --mdns-runtime "$P5COMP/mdns-runtime"
build v2 ota production "${UI[@]}" --mdns-runtime "$P5COMP/mdns-runtime"

( cd "$OUT" && sha256sum boot-lidar-*.img > SHA256SUMS )

verify() {
  local name="$1" image="$2" service="$3"
  shift 3
  python3 "$LIDAR/verify_recovery_image.py" \
    --stock-boot "$ROOT/dumps/20261110-lidar-readback/boot_a.bin" \
    --kernel-image "$KERNEL/Image" --kernel-config "$KERNEL/config" \
    --dtb "$KERNEL/libreecho-lidar.dtb" \
    --expected-dtb-sha256 "$(sha "$KERNEL/libreecho-lidar.dtb")" \
    --ramdisk "$OUT/boot-lidar-$name.ramdisk.cpio.xz" \
    --manifest "$OUT/boot-lidar-$name.manifest.json" \
    --boot-image "$OUT/boot-lidar-$name.img" \
    --expected-boot-sha256 "$(sha "$OUT/boot-lidar-$name.img")" \
    --cmdline-append "libreecho.lab=p6-$name" \
    --expected-busybox-sha256 "$(sha "$P5COMP/busybox/busybox")" \
    --expected-musl-loader-sha256 "$(sha "$P5COMP/musl/ld-musl-armhf.so.1")" \
    --expected-bootctl-sha256 "$(sha "$P5COMP/ota-control/libreecho-bootctl")" \
    --expected-update-verifier-sha256 "$(sha "$P5COMP/ota-control/libreecho-update-verify")" \
    --expected-ota-public-key-sha256 "$(sha "$P5/ota/lab-key/ed25519-public.hex")" \
    --expected-ui-manifest-sha256 "$(sha "$UI_BUNDLE/share/libreecho/ui-manifest.txt")" \
    --expected-ui-commit "$UI_COMMIT" --expected-ui-diff-sha256 "$UI_DIFF_SHA256" \
    --expected-wpa-supplicant-sha256 "$(sha "$WPA")" \
    --expected-tinyplay-sha256 "$(sha "$AUDIO/tinyplay")" \
    --expected-tinycap-sha256 "$(sha "$AUDIO/tinycap")" \
    --expected-tinymix-sha256 "$(sha "$AUDIO/tinymix")" \
    --image-profile "$image" --service-profile "$service" \
    --feature-policy preserve --update-channel dev "$@"
}

MDNS_PIN=(--expected-mdns-runtime-manifest-sha256 "$(cat "$P5COMP/mdns-runtime/manifest.sha256")")
verify dev development diagnostic
verify v1 ota production "${MDNS_PIN[@]}"
verify v2 ota production "${MDNS_PIN[@]}"
