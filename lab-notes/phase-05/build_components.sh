#!/usr/bin/env bash
# Build the ARM32 userspace components the Platform image builder consumes,
# from the same pinned sources and with the same invocations as Product
# `build/build.sh`. Host-only: never talks to a device.
#
# usage: build_components.sh [all|toolchain|musl-loader|busybox|libsodium|
#                             bootctl|update-verify|adbd|mdns|ui]
# Default `all` builds every component this experiment needs. Each target is
# rerunnable: outputs are replaced atomically per component.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "$0")" && pwd -P)"
ROOT="$(cd -- "$HERE/../.." && pwd -P)"
PRODUCT="$ROOT/forks/LibreEcho"
PLATFORM="$ROOT/forks/LibreEcho-Platform"
TOOLS="$PLATFORM/tools/mt8163-arm32"
ART="$ROOT/artifacts/phase-05"
TC="$ART/toolchains"
SRC="$TC/sources"
COMP="$ART/components"
LOGS="$COMP/logs"
HOSTBIN="$ART/host-tools/root/usr/bin"

MUSL_ROOT="$TC/musl"
MUSL_PREFIX="$MUSL_ROOT/usr/bin/armv7-alpine-linux-musleabihf-"
MUSL_CC="${MUSL_PREFIX}gcc"
ARMHF_ROOT="$TC/armhf-root"
ARMHF_CROSS="$ARMHF_ROOT/usr/bin/arm-linux-gnueabihf-"
ARMHF_LIBS="$ARMHF_ROOT/usr/lib/x86_64-linux-gnu"
ARMHF_SYSROOT="$ARMHF_ROOT/usr/arm-linux-gnueabihf"
UAPI="$TC/kernel-uapi/include"

JOBS="${JOBS:-$(nproc)}"
TARGET="${1:-all}"

mkdir -p "$COMP" "$LOGS" "$TC"

log() { printf '%s\n' "$*" >&2; }
need_file() { [[ -f "$1" ]] || { log "ERROR: missing input: $1"; exit 1; }; }
need_exec() { [[ -x "$1" ]] || { log "ERROR: missing tool: $1"; exit 1; }; }

verify_pin() {
  local file=$1 expected=$2 actual
  actual="$(sha256sum "$file" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || {
    log "ERROR: hash mismatch for $file: $actual != $expected"
    exit 1
  }
}

# --------------------------------------------------------------------------
# Toolchains
# --------------------------------------------------------------------------
build_toolchain() {
  # The Product script runs unmodified at its musl-cross-make pin; three host
  # differences from its Ubuntu CI runner are bridged here:
  # - ftp.gnu.org is unreachable, so a curl shim rewrites GNU dist URLs to
  #   mirrors.kernel.org; musl-cross-make still checks its committed hashes.
  # - Host GCC 16 defaults to C23 and C++20, which the pinned binutils and
  #   GCC sources predate, so the host compilers get the older dialects.
  # - The script copies host libraries from Debian multiarch paths, which do
  #   not exist on Arch. bwrap mounts a /usr/lib that adds those paths as
  #   links to the Arch copies. GCC finds its headers and startfiles relative
  #   to the physical /usr/lib/gcc path, so the real /usr/lib and /usr/include
  #   are mounted as siblings named lib and include.
  mkdir -p "$TC/bin"
  need_file "$TC/bin/curl"
  local hostroot="$TC/host-usr-lib" entry
  local reallib="$hostroot/lib" shimlib="$hostroot/shim"
  rm -rf "$hostroot"
  mkdir -p "$reallib" "$hostroot/include" "$shimlib/x86_64-linux-gnu"
  for entry in /usr/lib/* /usr/lib/.[!.]*; do
    [[ -e "$entry" || -L "$entry" ]] || continue
    ln -s "$reallib/${entry##*/}" "$shimlib/${entry##*/}"
  done
  for entry in libgmp.so.10 libmpfr.so.6 libmpc.so.3 libisl.so.23 libz.so.1 \
      libzstd.so.1 libjansson.so.4; do
    need_file "/usr/lib/$entry"
    ln -s "$reallib/$entry" "$shimlib/x86_64-linux-gnu/$entry"
  done
  bwrap --dev-bind / / \
    --ro-bind /usr/lib "$reallib" \
    --ro-bind /usr/include "$hostroot/include" \
    --bind "$shimlib" /usr/lib \
    env PATH="$TC/bin:$PATH" RUNNER_TEMP="$TC/runner-tmp" JOBS="$JOBS" \
      CC="gcc -std=gnu11" CXX="g++ -std=gnu++14" \
      bash "$PRODUCT/build/ci/build-public-toolchain.sh" "$MUSL_ROOT" \
    > "$LOGS/musl-toolchain-build.log" 2>&1
  log "musl toolchain: $MUSL_ROOT"
}

stage_armhf_toolchain() {
  # The committed lock plus the pinned archive set; no live apt resolution.
  local archives="$TC/armhf-archives"
  mkdir -p "$archives"
  python3 "$PRODUCT/build/ci/armhf_toolchain.py" stage \
    --lock "$PRODUCT/build/inputs/armhf-cross-toolchain.lock.json" \
    --archives "$archives" --prefix "$ARMHF_ROOT" \
    > "$LOGS/armhf-toolchain-stage.log" 2>&1
  python3 "$PRODUCT/build/ci/armhf_toolchain.py" verify \
    --lock "$PRODUCT/build/inputs/armhf-cross-toolchain.lock.json" \
    --archives "$archives" --prefix "$ARMHF_ROOT" \
    >> "$LOGS/armhf-toolchain-stage.log" 2>&1
  log "armhf toolchain: $ARMHF_ROOT"
}

# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
build_musl_loader() {
  need_exec "$MUSL_CC"
  rm -rf "$COMP/musl"
  "$TOOLS/musl/build_musl.sh" \
    --archive "$SRC/musl-1.2.5.tar.gz" --output "$COMP/musl" \
    --cc "$MUSL_CC" | tee "$LOGS/musl-loader-build.log"
}

build_busybox() {
  need_exec "${MUSL_PREFIX}gcc"
  rm -rf "$COMP/busybox"
  "$TOOLS/busybox/build_busybox.sh" \
    --archive "$SRC/busybox-1.37.0.tar.bz2" --output "$COMP/busybox" \
    --cross-prefix "$MUSL_PREFIX" --sysroot "$MUSL_ROOT" \
    | tee "$LOGS/busybox-build.log"
}

build_libsodium() {
  need_exec "$MUSL_CC"
  rm -rf "$COMP/libsodium"
  "$TOOLS/ota/build_libsodium.sh" \
    --archive "$SRC/libsodium-1.0.18.tar.gz" --output "$COMP/libsodium" \
    --cc "$MUSL_CC" --ar "${MUSL_PREFIX}ar" --ranlib "${MUSL_PREFIX}ranlib" \
    --sysroot "$MUSL_ROOT" --native-root "$MUSL_ROOT" \
    | tee "$LOGS/libsodium-build.log"
}

build_bootctl() {
  # Fast single-file rebuild: the Lidar layout lands in the shared source.
  need_exec "$MUSL_CC"
  mkdir -p "$COMP/ota-control"
  env LD_LIBRARY_PATH="$MUSL_ROOT/usr/lib" \
    "$MUSL_CC" --sysroot="$MUSL_ROOT" \
    -Os -ffunction-sections -fdata-sections -Wl,--gc-sections,-s \
    -Wall -Wextra -Werror \
    -o "$COMP/ota-control/libreecho-bootctl" "$TOOLS/ota/libreecho_bootctl.c"
  log "bootctl: $COMP/ota-control/libreecho-bootctl"
}

build_update_verify() {
  need_exec "$MUSL_CC"
  need_file "$COMP/libsodium/lib/libsodium.a"
  mkdir -p "$COMP/ota-control"
  env LD_LIBRARY_PATH="$MUSL_ROOT/usr/lib:$MUSL_ROOT/lib" \
    "$MUSL_CC" --sysroot="$MUSL_ROOT" \
    -Os -ffunction-sections -fdata-sections -static -no-pie \
    -Wl,--gc-sections,-s -Wall -Wextra -Werror \
    -I"$COMP/libsodium/include" \
    -o "$COMP/ota-control/libreecho-update-verify" \
    "$TOOLS/ota/libreecho_update_verify.c" \
    "$COMP/libsodium/lib/libsodium.a" -lpthread
  log "update-verify: $COMP/ota-control/libreecho-update-verify"
}

build_adbd() {
  need_exec "${ARMHF_CROSS}gcc"
  [[ -d "$UAPI/linux" ]] || { log "ERROR: exported UAPI tree missing: $UAPI"; exit 1; }
  mkdir -p "$COMP/adbd"
  env LD_LIBRARY_PATH="$ARMHF_LIBS" \
    bash "$TOOLS/adbd/build_adbd.sh" \
    --source "$SRC/aosp-system-core" --output "$COMP/adbd" \
    --cc "${ARMHF_CROSS}gcc" --sysroot "$ARMHF_SYSROOT" \
    --kernel-headers "$UAPI" --tcp-port 5555 \
    | tee "$LOGS/adbd-build.log"
}

build_mdns() {
  need_file "$PRODUCT/build/inputs/mdns-packages.lock.json"
  # The Platform builder unpacks debs with dpkg-deb; this host does not
  # install dpkg, so the verified host-tools copy supplies it.
  need_exec "$HOSTBIN/dpkg-deb"
  [[ -d "$COMP/mdns-packages" ]] || {
    log "ERROR: mDNS package archives are missing: $COMP/mdns-packages"
    exit 1
  }
  python3 "$PRODUCT/build/ci/mdns_runtime.py" verify \
    --lock "$PRODUCT/build/inputs/mdns-packages.lock.json" \
    --archives "$COMP/mdns-packages" > "$LOGS/mdns-verify.log" 2>&1
  rm -rf "$COMP/mdns-runtime"
  PATH="$HOSTBIN:$PATH" python3 -B "$TOOLS/mdns/build_runtime.py" \
    --archives "$COMP/mdns-packages" \
    --lock "$PRODUCT/build/inputs/mdns-packages.lock.json" \
    --output "$COMP/mdns-runtime" | tee "$LOGS/mdns-build.log"
  sha256sum "$COMP/mdns-runtime/manifest.json" | awk '{print $1}' \
    > "$COMP/mdns-runtime/manifest.sha256"
  python3 -B "$TOOLS/mdns/verify_runtime.py" \
    --runtime "$COMP/mdns-runtime" \
    --manifest-sha256 "$(cat "$COMP/mdns-runtime/manifest.sha256")" \
    | tee -a "$LOGS/mdns-build.log"
  ( cd "$COMP/mdns-runtime" && find . -type f ! -name SHA256SUMS -printf '%P\n' \
      | LC_ALL=C sort | xargs -d '\n' sha256sum > SHA256SUMS )
}

# Product builds the UI with a system cross compiler whose sysroot is built in.
# The staged Debian compiler is relocated, and its libc.so linker script names
# absolute /usr/arm-linux-gnueabihf paths, so it needs the staged root as its
# sysroot. These wrappers make that prefix behave like the system compiler for
# configure scripts that call the compiler without extra flags.
make_armhf_wrappers() {
  local dir="$TC/armhf-cc" tool real
  rm -rf "$dir"
  mkdir -p "$dir"
  for real in "${ARMHF_CROSS}"*; do
    tool="${real##*/}"
    case "$tool" in
      arm-linux-gnueabihf-gcc|arm-linux-gnueabihf-g++|arm-linux-gnueabihf-cpp)
        printf '#!/bin/sh\nLD_LIBRARY_PATH=%q exec %q --sysroot=%q "$@"\n' \
          "$ARMHF_LIBS" "$real" "$ARMHF_ROOT" > "$dir/$tool"
        chmod 0755 "$dir/$tool" ;;
      *) ln -s "$real" "$dir/$tool" ;;
    esac
  done
}

build_ui() {
  # Product build/build.sh builds the pinned ARM32 mbedTLS prefix first and
  # hands its path to the UI bundle builder, which also builds the pinned Opus
  # stack itself from the locked archives. The mbedTLS interpreter is the
  # reviewed CPython 3.11 wheel closure; the absolute --output matters because
  # the builder runs `ar x` after chdir.
  local venv="$TC/mbedtls-build-venv"
  local py="$venv/bin/python"
  local archives="$SRC/opus"
  make_armhf_wrappers
  local ui_cross="$TC/armhf-cc/arm-linux-gnueabihf-"
  need_exec "${ui_cross}gcc"
  need_exec "${ui_cross}ar"
  need_exec "$py"
  need_exec "$MUSL_CC"
  need_file "$SRC/mbedtls-3.6.7.tar.bz2"
  local archive
  for archive in libogg-1.3.5.tar.gz opus-1.4.tar.gz opusfile-0.12.tar.gz; do
    need_file "$archives/$archive"
  done
  rm -rf "$COMP/mbedtls-arm32" "$COMP/ui-bundle"
  env LD_LIBRARY_PATH="$ARMHF_LIBS" \
    "$TOOLS/mbedtls/build_mbedtls.sh" \
      --archive "$SRC/mbedtls-3.6.7.tar.bz2" \
      --output "$COMP/mbedtls-arm32" \
      --cc "${ARMHF_CROSS}gcc" --python "$py" --jobs "$JOBS" \
    | tee "$LOGS/mbedtls-build.log"
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
    "$TOOLS/ui/build_ui_bundle.sh" "$SRC/libreecho-ui" \
      "$COMP/ui-bundle/bundle" | tee "$LOGS/ui-build.log"
  ( cd "$COMP/ui-bundle" && find bundle -type f -print0 \
      | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS )
  log "ui-bundle: $COMP/ui-bundle/bundle"
}

case "$TARGET" in
  all)
    build_musl_loader
    build_busybox
    build_libsodium
    build_bootctl
    build_update_verify
    build_adbd
    build_mdns
    ;;
  toolchain) build_toolchain ;;
  armhf-toolchain) stage_armhf_toolchain ;;
  musl-loader) build_musl_loader ;;
  busybox) build_busybox ;;
  libsodium) build_libsodium ;;
  bootctl) build_bootctl ;;
  update-verify) build_update_verify ;;
  adbd) build_adbd ;;
  mdns) build_mdns ;;
  ui) build_ui ;;
  *) log "ERROR: unknown target: $TARGET"; exit 2 ;;
esac
