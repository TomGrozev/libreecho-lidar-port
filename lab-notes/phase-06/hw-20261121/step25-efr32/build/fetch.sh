#!/bin/bash
# Fetch the pinned Silicon Labs build inputs for the EFR32 RCP, natively.
# Mirrors reference/lidar-mainline efr32/Containerfile + build.sh; nothing of
# the SDK, tools or output is committed.
set -euo pipefail

ROOT=/tmp/efr32
SRC=$ROOT/src
TOOLS=$ROOT/tools
mkdir -p "$SRC" "$TOOLS"

GSDK_REV=d95099f4c05b3c40cece93d8a261dd471e642086 # v4.4.3
OT_EFR32_REV=089440dc0162ca5e2c7b522e33e30a71a299d693 # 2024-07-29, last on Gecko SDK
U=https://updates.silabs.com/studio/v6/updates/update_site/archives

if [ ! -x "$TOOLS/gcc-arm/bin/arm-none-eabi-gcc" ]; then
	curl -fSL -o "$TOOLS/gcc.tar.xz" \
		https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-arm-none-eabi.tar.xz
	echo "84be93d0f9e96a15addd490b6e237f588c641c8afdf90e7610a628007fc96867  $TOOLS/gcc.tar.xz" | sha256sum -c --quiet
	mkdir -p "$TOOLS/gcc-arm"
	tar -xJf "$TOOLS/gcc.tar.xz" -C "$TOOLS/gcc-arm" --strip-components=1
	rm "$TOOLS/gcc.tar.xz"
fi

fetch_zip() { # dir url sha256
	[ -d "$1" ] && return 0
	curl -fSL -o "$1.zip" "$2"
	echo "$3  $1.zip" | sha256sum -c --quiet
	mkdir -p "$1"
	bsdtar -xf "$1.zip" --strip-components=1 -C "$1"
	rm "$1.zip"
}
fetch_zip "$TOOLS/slc" "$U/slc-cli/6.0.22/slc-cli.linux.gtk.x86_64.zip" \
	f05e078b369d7e7dbfa31bdd2ad8edf61f04a9291393deab4702137639ba7d19
fetch_zip "$TOOLS/python" "$U/python/3.10.3/python.3.10.3.gtk.linux.x86_64.zip" \
	26f56b1cfa05b2b3b7dafb2c2a5e3c19498389c34dfe68be800f71f476c86363
fetch_zip "$TOOLS/java21" "$U/java21/21.0.6/linux.x86_64_21.0.6.zip" \
	5382fa98bcc66fc3aef48792a3e84328eca16afa9bf97517527e92812516ee50

S=$SRC/gsdk
R=$S/extension/ot-efr32
if [ ! -d "$S/.git" ]; then
	git clone -q --filter=blob:none --no-checkout https://github.com/SiliconLabs/gecko_sdk.git "$S"
fi
if [ "$(git -C "$S" rev-parse HEAD 2>/dev/null)" != "$GSDK_REV" ]; then
	git -C "$S" checkout -q "$GSDK_REV"
fi
git -C "$S" lfs install --local >/dev/null
git -C "$S" lfs pull

if [ ! -d "$R/.git" ]; then
	mkdir -p "$S/extension"
	git clone -q https://github.com/openthread/ot-efr32.git "$R"
fi
if [ "$(git -C "$R" rev-parse HEAD)" != "$OT_EFR32_REV" ]; then
	git -C "$R" checkout -q "$OT_EFR32_REV"
fi
git -C "$R" submodule update -q --init --depth 1 openthread
if [ ! -L "$R/third_party/silabs/gecko_sdk" ]; then
	rm -rf "$R/third_party/silabs/gecko_sdk"
	ln -s "$S" "$R/third_party/silabs/gecko_sdk"
fi
# ot-efr32 at this revision declares SDK 4.4.0 but pins 4.4.3; slc 6 only
# loads an extension whose SDK version matches exactly
sed -i 's/^  version: 4\.4\.0$/  version: 4.4.3/' "$R/ot-efr32.slce"

echo "fetch complete"
du -sh "$S" "$R" "$TOOLS" 2>/dev/null || true
