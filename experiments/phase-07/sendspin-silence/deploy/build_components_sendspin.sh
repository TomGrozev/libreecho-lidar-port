#!/usr/bin/env bash
# Sendspin-silence deploy: UI bundle only. Copy of the step-37 component builder
# with COMP repointed to artifacts/phase-07/components-sendspin-fix so the
# phase-06 component tree is untouched. UI source is repos/LibreEcho-UI at
# d63a58a (f43dade plus the Sendspin fix). Host-only: never talks to a device.
#
# usage: build_components_sendspin.sh [ui|reuse-check]
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(cd -- "$HERE/../../../.." && pwd -P)"
PLATFORM="$ROOT/repos/LibreEcho-Platform"
TOOLS="$PLATFORM/tools/mt8163-arm32"
ART="$ROOT/artifacts/phase-06"
P5="$ROOT/artifacts/phase-05"
TC="$P5/toolchains"
SRC="$TC/sources"
COMP="${COMP_DIR:-$ROOT/artifacts/phase-07/components-sendspin-fix}"
LOGS="$COMP/logs"
UI_SOURCE="${UI_SOURCE_DIR:-$ROOT/repos/LibreEcho-UI}"

MUSL_ROOT="$TC/musl"
MUSL_PREFIX="$MUSL_ROOT/usr/bin/armv7-alpine-linux-musleabihf-"
MUSL_CC="${MUSL_PREFIX}gcc"
ARMHF_ROOT="$TC/armhf-root"
ARMHF_CROSS="$ARMHF_ROOT/usr/bin/arm-linux-gnueabihf-"
ARMHF_LIBS="$ARMHF_ROOT/usr/lib/x86_64-linux-gnu"

JOBS="${JOBS:-$(nproc)}"
TARGET="${1:-all}"

mkdir -p "$COMP" "$LOGS"

log() { printf '%s\n' "$*" >&2; }
need_file() { [[ -f "$1" ]] || { log "ERROR: missing input: $1"; exit 1; }; }
need_exec() { [[ -x "$1" ]] || { log "ERROR: missing tool: $1"; exit 1; }; }
sha() { sha256sum "$1" | awk '{print $1}'; }

# Phase-5 outputs as built; unchanged sources must reproduce these bytes.
P5_MUSL_SHA=47ed5c21aca427b893859aa9ee1ca7a0ce9494f4e0e7dd6ee4136d9766f9f060
P5_BUSYBOX_SHA=fed10234e996e9647d753ab5ee196d69f465ece1fe9962e401a0df7ef96cf3de
P5_ADBD_SHA=3651b39f524bd8f07f1a9b85e00ec284017b5558788a3715d8aa08132866b6e0
P5_BOOTCTL_SHA=4f19413de86355809051b316e99b6334198a5fc8ce3889b357f90fb8761b6224
P5_VERIFY_SHA=bfc00578d1006f589d257a796f688f7bdd729fe4cf7bbbe2e271dc95ff557aaf

reuse_check() {
  local pair actual
  for pair in \
      "$P5/components/musl/ld-musl-armhf.so.1:$P5_MUSL_SHA" \
      "$P5/components/busybox/busybox:$P5_BUSYBOX_SHA" \
      "$P5/components/adbd/adbd:$P5_ADBD_SHA" \
      "$P5/components/ota-control/libreecho-bootctl:$P5_BOOTCTL_SHA" \
      "$P5/components/ota-control/libreecho-update-verify:$P5_VERIFY_SHA"; do
    need_file "${pair%:*}"
    actual="$(sha "${pair%:*}")"
    [[ "$actual" == "${pair##*:}" ]] || {
      log "ERROR: reused component drifted: ${pair%:*}: $actual != ${pair##*:}"
      exit 1
    }
  done
  need_file "$P5/components/mdns-runtime/manifest.json"
  need_file "$P5/components/mdns-runtime/manifest.sha256"
  log "reuse-check: phase-05 musl, busybox, adbd, ota-control and mdns-runtime match their pins"
}

make_armhf_wrappers() {
  local dir="$TC/armhf-cc" tool real
  [[ -d "$dir" ]] && return 0
  mkdir -p "$dir"
  for real in "${ARMHF_CROSS}"*; do
    tool="${real##*/}"
    case "$tool" in
      arm-linux-gnueabihf-gcc|arm-linux-gnueabihf-g++|arm-linux-gnueabihf-cpp)
        printf '#!/bin/sh\nLD_LIBRARY_PATH=%q exec %q --sysroot=%q "$@"\n' \
          "$ARMHF_LIBS" "$real" "$ARMHF_ROOT" > "$dir/$tool"
        chmod 0755 "$dir/$tool" ;;
      *) ln -sfn "$real" "$dir/$tool" ;;
    esac
  done
}

build_bootctl() {
  need_exec "$MUSL_CC"
  mkdir -p "$COMP/ota-control"
  env LD_LIBRARY_PATH="$MUSL_ROOT/usr/lib" \
    "$MUSL_CC" --sysroot="$MUSL_ROOT" \
    -Os -ffunction-sections -fdata-sections -Wl,--gc-sections,-s \
    -Wall -Wextra -Werror \
    -o "$COMP/ota-control/libreecho-bootctl" "$TOOLS/ota/libreecho_bootctl.c"
  log "bootctl: $COMP/ota-control/libreecho-bootctl ($(sha "$COMP/ota-control/libreecho-bootctl"))"
}

build_update_verify() {
  need_exec "$MUSL_CC"
  need_file "$P5/components/libsodium/lib/libsodium.a"
  mkdir -p "$COMP/ota-control"
  env LD_LIBRARY_PATH="$MUSL_ROOT/usr/lib:$MUSL_ROOT/lib" \
    "$MUSL_CC" --sysroot="$MUSL_ROOT" \
    -Os -ffunction-sections -fdata-sections -static -no-pie \
    -Wl,--gc-sections,-s -Wall -Wextra -Werror \
    -I"$P5/components/libsodium/include" \
    -o "$COMP/ota-control/libreecho-update-verify" \
    "$TOOLS/ota/libreecho_update_verify.c" \
    "$P5/components/libsodium/lib/libsodium.a" -lpthread
  log "update-verify: $COMP/ota-control/libreecho-update-verify ($(sha "$COMP/ota-control/libreecho-update-verify"))"
}

build_ui() {
  # Product build/build.sh builds the pinned ARM32 mbedTLS prefix first and
  # hands its path to the UI bundle builder, which also builds the pinned Opus
  # stack itself from the locked archives.  Archives and the CPython wheel
  # closure are the phase-05 ones; only the UI checkout is new.
  local venv="$TC/mbedtls-build-venv"
  local py="$venv/bin/python"
  local archives="$SRC/opus"
  local archive
  make_armhf_wrappers
  local ui_cross="$TC/armhf-cc/arm-linux-gnueabihf-"
  need_exec "${ui_cross}gcc"
  need_exec "${ui_cross}ar"
  need_exec "$py"
  need_exec "$MUSL_CC"
  need_file "$SRC/mbedtls-3.6.7.tar.bz2"
  need_file "$UI_SOURCE/VERSION"
  for archive in libogg-1.3.5.tar.gz opus-1.4.tar.gz opusfile-0.12.tar.gz; do
    need_file "$archives/$archive"
  done
  rm -rf "$COMP/mbedtls-arm32" "$COMP/ui-bundle"
  env LD_LIBRARY_PATH="$ARMHF_LIBS" \
    "$TOOLS/mbedtls/build_mbedtls.sh" \
      --archive "$SRC/mbedtls-3.6.7.tar.bz2" \
      --output "$COMP/mbedtls-arm32" \
      --cc "${ARMHF_CROSS}gcc" --python "$py" --jobs "$JOBS" \
    > "$LOGS/mbedtls-build.log" 2>&1
  mkdir -p "$COMP/ui-bundle"
  env LD_LIBRARY_PATH="$ARMHF_LIBS" \
    LIBREECHO_UI_CROSS_COMPILE="$ui_cross" \
    LIBREECHO_UI_MBEDTLS_ROOT="$COMP/mbedtls-arm32" \
    LIBREECHO_OPUS_ARCHIVES_DIR="$archives" \
    LIBREECHO_OPUS_CC="${ui_cross}gcc" \
    LIBREECHO_OPUS_AR="${ui_cross}ar" \
    LIBREECHO_OPUS_HOST=arm-linux-gnueabihf \
    LIBREECHO_UI_MUSL_NATIVE_ROOT="$MUSL_ROOT" \
    LIBREECHO_UI_MUSL_SYSROOT="$MUSL_ROOT" \
    LIBREECHO_UI_MUSL_CC="$MUSL_CC" \
    LIBREECHO_UI_MUSL_NATIVE_LIB="$MUSL_ROOT/usr/lib" \
    "$TOOLS/ui/build_ui_bundle.sh" "$UI_SOURCE" \
      "$COMP/ui-bundle/bundle" > "$LOGS/ui-build.log" 2>&1
  ( cd "$COMP/ui-bundle" && find bundle -type f -print0 \
      | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS )
  log "ui-bundle: $COMP/ui-bundle/bundle ($(sha "$COMP/ui-bundle/bundle/share/libreecho/ui-manifest.txt"))"
}

case "$TARGET" in
  all)
    reuse_check
    build_ui
    ;;
  ui) build_ui ;;
  bootctl) build_bootctl ;;
  update-verify) build_update_verify ;;
  reuse-check) reuse_check ;;
  *) log "ERROR: unknown target: $TARGET"; exit 2 ;;
esac
