#!/usr/bin/env bash
# Export the ARM32 Linux UAPI tree that adbd, wpa_supplicant and the wireless tools build
# against. Mirrors private/forks/LibreEcho/.github/workflows/build-release.yml "Export Linux UAPI
# headers" (ARCH=arm). This host has no rsync, so instead of `headers_install` it runs
# `make headers` and copies only *.h files, which is what headers_install's rsync copies.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/../../../.." && pwd -P)"
KSRC="$ROOT/forks/LibreEcho-Linux"
TC="$ROOT/artifacts/phase-05/toolchains"
OUT="$TC/kernel-uapi"
KB="$TC/kbuild-uapi-arm"

rm -rf -- "$OUT" "$KB"
make -C "$KSRC" O="$KB" ARCH=arm headers
mkdir -p "$OUT"
(cd "$KB/usr" && find include -name '*.h' -exec cp --parents {} "$OUT/" \;)
rm -rf -- "$KB"

for tree in linux asm asm-generic; do
  [[ -d "$OUT/include/$tree" ]] || { echo "ERROR: exported UAPI subtree is missing: $tree" >&2; exit 1; }
done
if grep -q '__uint128_t' "$OUT/include/asm/sigcontext.h"; then
  echo "ERROR: asm/sigcontext.h is not the ARM32 variant" >&2; exit 1
fi
printf 'uapi headers: %s files in %s\n' "$(find "$OUT/include" -name '*.h' | wc -l)" "$OUT/include"
