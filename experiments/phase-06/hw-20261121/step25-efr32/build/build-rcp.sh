#!/bin/bash
# Build the OpenThread RCP GBL natively (no container), replaying
# reference/lidar-mainline efr32/build.sh with /tmp/efr32 paths.
# Inputs come from build/fetch.sh; nothing here is committed.
set -euo pipefail

ROOT=/tmp/efr32
SRC=$ROOT/src
TOOLS=$ROOT/tools
S=$SRC/gsdk
R=$S/extension/ot-efr32
X=$S/extension/lidar
OUT=$ROOT/out
EXT=${EXT:-/workspace/libreecho/reference/lidar-mainline/efr32/extension}

export PATH=$TOOLS/gcc-arm/bin:$TOOLS/java21/bin:$TOOLS/java21/jre/bin:$TOOLS/slc:$PATH
export STUDIO_PYTHON3_PATH=$TOOLS/python
export ARM_GCC_DIR=$TOOLS/gcc-arm
export HOME=$ROOT/home
mkdir -p "$HOME"

data=$ROOT/build/slc.data
gen=$ROOT/build/gen
rm -rf "$X" "$gen" && cp -r "$EXT" "$X"
mkdir -p "$gen" "$ROOT/build"

slc --daemon -v 1 signature trust --sdk "$S" -data "$data" >/dev/null
slc --daemon -v 1 signature trust --sdk "$S" -extpath "$R" -data "$data" >/dev/null
slc --daemon -v 1 signature trust --sdk "$S" -extpath "$X" -data "$data" >/dev/null
slc --daemon -v 1 generate -data "$data" --sdk="$S" \
	--project-file="$X/projects/lidar-rcp-uart.slcp" --project-name=openthread-efr32-rcp-uart \
	--output-type=makefile --no-copy \
	--export-templates="$R/third_party/silabs/slc/exporter_templates/yaml" \
	--export-destination="$gen"
mv "$gen/openthread-efr32-rcp-uart.Makefile" "$gen/slc_vars.yaml"
rm -f "$gen/openthread-efr32-rcp-uart.project.mak"
"$R/script/generate_cmake.py" "$gen/slc_vars.yaml" "$gen" >/dev/null

b=$ROOT/build/rcp
rm -rf "$b" && mkdir -p "$b"
cmake -S "$R" -B "$b" -GNinja \
	-DCMAKE_TOOLCHAIN_FILE=src/efr32mg12/arm-none-eabi.cmake \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
	-DEFR32_PLATFORM=efr32mg12 -DBOARD=lidar \
	-DOT_PLATFORM_LIB_DIR="$gen" \
	-DOT_FTD=OFF -DOT_MTD=OFF -DOT_RCP=ON \
	-DOT_APP_CLI=OFF -DOT_APP_NCP=OFF -DOT_APP_RCP=ON \
	-DOT_DIAGNOSTIC=ON -DOT_EXTERNAL_HEAP=ON -DOT_SLAAC=ON \
	-DOT_COMPILE_WARNING_AS_ERROR=ON > "$b/cmake.log" 2>&1 ||
	{ tail -20 "$b/cmake.log"; exit 1; }
ninja -C "$b" ot-rcp > "$b/ninja.log" 2>&1 ||
	{ awk '/error|FAILED/' "$b/ninja.log" | head -20; exit 1; }
mkdir -p "$OUT"
cp "$b/bin/ot-rcp" "$OUT/lidar-ot-rcp.elf"
arm-none-eabi-objcopy -O binary "$b/bin/ot-rcp" "$b/ot-rcp.bin"
python3 /workspace/libreecho/experiments/phase-06/hw-20261121/step25-efr32/mkgbl.py \
	"$b/ot-rcp.bin" "$OUT/lidar-ot-rcp.gbl"
arm-none-eabi-size "$OUT/lidar-ot-rcp.elf"
