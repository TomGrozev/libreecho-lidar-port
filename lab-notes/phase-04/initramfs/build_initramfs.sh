#!/usr/bin/env bash
# Build the LibreEcho Lidar (Echo Plus 2nd Gen) ARM32 test initramfs.
#
# Host-only. Downloads are pinned by sha256 and verified; a mismatch aborts.
# Toolchain: stock Arch clang/lld/llvm-ar 23 (no ARM gcc, no sudo), musl 1.2.5
# built from source for armv7a-linux-musleabihf, and compiler-rt builtins built
# from the llvm-project 23.1.5 source release that matches the installed clang.
#
#   ./build_initramfs.sh            # full build, writes private/artifacts/phase-04/initramfs
#   LIDAR_INITRAMFS_WORK=/path      # reusable work dir (default /tmp/lidar-initramfs-build)
#
# Nothing here touches private/forks/: the kernel tree is read only for gen_init_cpio.c.

set -euo pipefail

HERE=$(cd -- "$(dirname -- "$0")" && pwd -P)
ROOT=$(cd -- "$HERE/../../.." && pwd -P)
OUT="$ROOT/artifacts/phase-04/initramfs"
KERNEL="$ROOT/forks/LibreEcho-Linux"
WORK=${LIDAR_INITRAMFS_WORK:-/tmp/lidar-initramfs-build}

MUSL_VERSION=1.2.5
MUSL_URL="https://musl.libc.org/releases/musl-$MUSL_VERSION.tar.gz"
MUSL_SHA256=a9a118bbe84d8764da0ea0d28b3ab3fae8477fc7e4085d90102b8596fc7c75e4

LLVM_VERSION=23.1.5
LLVM_URL="https://github.com/llvm/llvm-project/releases/download/llvmorg-$LLVM_VERSION/llvm-project-$LLVM_VERSION.src.tar.xz"
LLVM_SHA256=fb50b1eac93ddeb3aa8dab4cfe324dff74f4a9c2bdee6160c9e36188f8d06a6e

BUSYBOX_VERSION=1.37.0
BUSYBOX_URL="https://busybox.net/downloads/busybox-$BUSYBOX_VERSION.tar.bz2"
BUSYBOX_SHA256=3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4

TARGET=armv7a-linux-musleabihf
ARCH_FLAGS="-march=armv7-a -mtune=cortex-a53 -mfpu=vfpv3-d16 -mfloat-abi=hard"
SYSROOT="$WORK/sysroot"
WRAPPERS="$WORK/wrappers"
BUILTINS_DIR="$WORK/builtins-arm"
BUILTINS="$BUILTINS_DIR/lib/linux/libclang_rt.builtins-armhf.a"

mkdir -p "$WORK/dl" "$WORK/src" "$OUT" "$WRAPPERS"

fetch() {
    local url=$1 file=$2 sha=$3
    if [[ -f "$WORK/dl/$file" ]] && [[ "$(sha256sum "$WORK/dl/$file" | cut -d' ' -f1)" == "$sha" ]]; then
        return 0
    fi
    curl -fL --retry 3 -o "$WORK/dl/$file.part" "$url"
    local got
    got=$(sha256sum "$WORK/dl/$file.part" | cut -d' ' -f1)
    [[ "$got" == "$sha" ]] || {
        echo "ERROR: sha256 mismatch for $url: got $got want $sha" >&2
        rm -f "$WORK/dl/$file.part"
        exit 1
    }
    mv "$WORK/dl/$file.part" "$WORK/dl/$file"
}

echo "== sources (pinned)"
fetch "$MUSL_URL" "musl-$MUSL_VERSION.tar.gz" "$MUSL_SHA256"
fetch "$LLVM_URL" "llvm-project-$LLVM_VERSION.src.tar.xz" "$LLVM_SHA256"
fetch "$BUSYBOX_URL" "busybox-$BUSYBOX_VERSION.tar.bz2" "$BUSYBOX_SHA256"

# ------------------------------------------------------------------- musl
if [[ ! -f "$SYSROOT/usr/lib/libc.a" ]]; then
    echo "== musl $MUSL_VERSION -> $SYSROOT"
    [[ -d "$WORK/src/musl-$MUSL_VERSION" ]] || tar xzf "$WORK/dl/musl-$MUSL_VERSION.tar.gz" -C "$WORK/src"
    (
        cd "$WORK/src/musl-$MUSL_VERSION"
        make distclean >/dev/null 2>&1 || true
        # clang is the only C compiler here; musl's configure accepts a CC with flags.
        CC="clang --target=$TARGET $ARCH_FLAGS" AR=llvm-ar RANLIB=llvm-ranlib \
            ./configure --target=armv7-linux-musleabihf \
            --prefix="$SYSROOT/usr" --disable-shared --enable-static >/dev/null
        make -j"$(nproc)" >/dev/null
        make install >/dev/null
    )
fi

# --------------------------------------------------- compiler-rt builtins
# The Arch compiler-rt package ships only x86 builtins, so __aeabi_* and the
# 64-bit integer helpers must be built for ARM. Only lib/builtins is needed.
if [[ ! -f "$BUILTINS" ]]; then
    echo "== compiler-rt $LLVM_VERSION builtins (armv7)"
    LLVM_SRC="$WORK/src/llvm-project-$LLVM_VERSION.src"
    if [[ ! -f "$LLVM_SRC/compiler-rt/lib/builtins/CMakeLists.txt" ]]; then
        tar xf "$WORK/dl/llvm-project-$LLVM_VERSION.src.tar.xz" -C "$WORK/src" \
            "llvm-project-$LLVM_VERSION.src/compiler-rt" \
            "llvm-project-$LLVM_VERSION.src/cmake" \
            "llvm-project-$LLVM_VERSION.src/llvm/cmake"
    fi
    cmake -G Ninja -S "$LLVM_SRC/compiler-rt" -B "$BUILTINS_DIR" \
        -DLLVM_COMMON_CMAKE_UTILS="$LLVM_SRC/cmake" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_SYSROOT="$SYSROOT" \
        -DCMAKE_C_COMPILER=clang -DCMAKE_C_COMPILER_TARGET="$TARGET" \
        -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_CXX_COMPILER_TARGET="$TARGET" \
        -DCMAKE_ASM_COMPILER=clang -DCMAKE_ASM_COMPILER_TARGET="$TARGET" \
        -DCMAKE_C_FLAGS="$ARCH_FLAGS -ffreestanding" \
        -DCMAKE_ASM_FLAGS="$ARCH_FLAGS" \
        -DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY \
        -DCMAKE_AR=/usr/bin/llvm-ar -DCMAKE_RANLIB=/usr/bin/llvm-ranlib -DCMAKE_NM=/usr/bin/llvm-nm \
        -DCOMPILER_RT_DEFAULT_TARGET_ONLY=ON \
        -DCOMPILER_RT_BUILD_BUILTINS=ON -DCOMPILER_RT_BUILD_SANITIZERS=OFF \
        -DCOMPILER_RT_BUILD_XRAY=OFF -DCOMPILER_RT_BUILD_LIBFUZZER=OFF \
        -DCOMPILER_RT_BUILD_PROFILE=OFF -DCOMPILER_RT_BUILD_MEMPROF=OFF \
        -DCOMPILER_RT_BUILD_ORC=OFF -DCOMPILER_RT_BUILD_CTX_PROFILE=OFF \
        -DCOMPILER_RT_BUILD_GWP_ASAN=OFF -DCOMPILER_RT_INCLUDE_TESTS=OFF >/dev/null
    ninja -C "$BUILTINS_DIR" >/dev/null
fi

# --------------------------------------------------------------- wrappers
# One driver for compile and link. musl gives us no GCC installation and no
# libgcc, so executable links are driven with -nostdlib plus explicit musl crt
# objects, libc.a and compiler-rt builtins. -r/-shared builds must not get them.
cat > "$WRAPPERS/armv7-gcc" <<EOF
#!/bin/sh
SYS=$SYSROOT
BUILTINS=$BUILTINS
FLAGS="--target=$TARGET $ARCH_FLAGS --sysroot=\$SYS -fuse-ld=lld -idirafter /usr/include"
link=1
for a in "\$@"; do
  case "\$a" in
    -c|-E|-S|-M|-MM|-MMD|-MD|-r|-shared) link=0 ;;
  esac
done
if [ "\$link" = 1 ]; then
  exec clang \$FLAGS -nostdlib \\
    "\$SYS/usr/lib/crt1.o" "\$SYS/usr/lib/crti.o" "\$@" \\
    "\$SYS/usr/lib/libc.a" -lm "\$BUILTINS" "\$SYS/usr/lib/crtn.o"
fi
exec clang \$FLAGS "\$@"
EOF
chmod +x "$WRAPPERS/armv7-gcc"
printf '#!/bin/sh\nexec ld.lld -m armelf_linux_eabi "$@"\n' > "$WRAPPERS/armv7-ld"
chmod +x "$WRAPPERS/armv7-ld"
for t in ar ranlib nm strip objcopy objdump readelf size as; do
    ln -sf "/usr/bin/llvm-$t" "$WRAPPERS/armv7-$t"
done

# --------------------------------------------------------------- busybox
# BusyBox 1.37.0, static, from the platform config plus CONFIG_STATIC,
# CONFIG_CTTYHACK and CONFIG_DEVMEM (the image needs setsid/cttyhack shells and
# devmem for register pokes). SOURCE.lock pins the tarball; the copy below is
# verified against the same hash.
BB_SRC="$WORK/src/busybox-$BUSYBOX_VERSION"
BB_OUT="$WORK/busybox-out"
if [[ ! -f "$BB_SRC/Makefile" ]]; then
    tar xjf "$WORK/dl/busybox-$BUSYBOX_VERSION.tar.bz2" -C "$WORK/src"
fi
if [[ ! -x "$BB_OUT/busybox" ]]; then
    echo "== busybox $BUSYBOX_VERSION (static, armv7)"
    mkdir -p "$BB_OUT"
    cp "$HERE/busybox-1.37.0.config" "$BB_OUT/.config"
    PATH="$WRAPPERS:$PATH" make -C "$BB_SRC" O="$BB_OUT" HOSTCC=/usr/bin/gcc \
        CROSS_COMPILE=armv7- oldconfig </dev/null >/dev/null
    PATH="$WRAPPERS:$PATH" make -C "$BB_SRC" O="$BB_OUT" HOSTCC=/usr/bin/gcc \
        CROSS_COMPILE=armv7- -j"$(nproc)" >/dev/null
fi

# --------------------------------------------------------------- packaging
echo "== package"
STAGE="$WORK/root"
rm -rf "$STAGE"
mkdir -p "$STAGE/bin" "$STAGE/dev"
install -m 0755 "$BB_OUT/busybox" "$STAGE/bin/busybox"
install -m 0755 "$HERE/init" "$STAGE/init"
# gen_init_cpio takes the mtime and ownership from the source paths; both are
# fixed so repeated builds produce the same archive bytes.
touch -d @0 "$STAGE/init" "$STAGE/bin/busybox"

# The kernel tree's own cpio generator, built for the host.
hostcc=${HOSTCC:-/usr/bin/cc}
$hostcc -O2 -o "$WORK/gen_init_cpio" "$KERNEL/usr/gen_init_cpio.c"

( cd "$STAGE" && "$WORK/gen_init_cpio" -t 0 "$HERE/initramfs.list" ) > "$WORK/initramfs.cpio"
gzip -n -9 -c "$WORK/initramfs.cpio" > "$OUT/lidar-test-initramfs.cpio.gz"

# ------------------------------------------------------------------ checks
echo "== checks"
llvm-readelf -h "$BB_OUT/busybox" | grep -q 'ARM' || { echo "busybox is not ARM" >&2; exit 1; }
llvm-readelf -h "$BB_OUT/busybox" | grep -q '0x5000400' || { echo "busybox is not EABI5 hard-float" >&2; exit 1; }
llvm-readelf -l "$BB_OUT/busybox" | grep -qi 'interp' && { echo "busybox has an interpreter" >&2; exit 1; }
# Applets are verified from the built .config: the ARM binary cannot be
# executed on the x86 host, so this check never tries to run it.
: > "$WORK/applets.txt"
for a in $(sed -n 's/^CONFIG_\([A-Z0-9_]*\)=y$/\1/p' "$BB_OUT/.config"); do
    printf '%s\n' "${a,,}" >> "$WORK/applets.txt"
done
for a in sh mount umount mkdir ln cat echo ls cp mv rm sleep dmesg uname ip ifconfig \
         ping ping6 setsid cttyhack getty hexdump devmem sync reboot poweroff ps kill grep \
         sed tail head find xargs md5sum sha256sum chmod mknod stty env printf test true \
         false dd tr cut wc stat df free uptime nproc; do
    case "$a" in
        sh) sym=ash ;;
        *) sym=$a ;;
    esac
    grep -qx "$sym" "$WORK/applets.txt" || { echo "ERROR: applet $a missing" >&2; exit 1; }
done

archive_sha=$(sha256sum "$OUT/lidar-test-initramfs.cpio.gz" | cut -d' ' -f1)
bb_sha=$(sha256sum "$BB_OUT/busybox" | cut -d' ' -f1)
bb_cfg_sha=$(sha256sum "$BB_OUT/.config" | cut -d' ' -f1)
cat > "$OUT/MANIFEST.txt" <<EOF
name=lidar-test-initramfs
target=armv7a hard-float (EABI5), static busybox, musl 1.2.5
archive=lidar-test-initramfs.cpio.gz
archive_sha256=$archive_sha
archive_bytes=$(stat -c %s "$OUT/lidar-test-initramfs.cpio.gz")
busybox_version=$BUSYBOX_VERSION
busybox_sha256=$bb_sha
busybox_config_sha256=$bb_cfg_sha
musl_source_url=$MUSL_URL
musl_source_sha256=$MUSL_SHA256
busybox_source_url=$BUSYBOX_URL
busybox_source_sha256=$BUSYBOX_SHA256
llvm_source_url=$LLVM_URL
llvm_source_sha256=$LLVM_SHA256
EOF
cat "$OUT/MANIFEST.txt"
printf 'archive_sha256=%s\n' "$archive_sha"
