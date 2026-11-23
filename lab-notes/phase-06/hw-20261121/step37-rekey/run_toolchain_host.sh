#!/usr/bin/env bash
# Run RebuildRekey's host-adapted product toolchain script under the single
# owner lock, with the curl shim and an optional pre-seeded source directory.
set -euo pipefail
ROOT=/workspace/libreecho
R=$ROOT/private/lab/phase-06/hw-20261121/step37-rekey
exec 9>/tmp/libreecho-toolchain.lock
flock 9
export RUNNER_TEMP=$ROOT/private/artifacts/phase-05/toolchains/runner-tmp
export JOBS=12
export PATH="$ROOT/private/artifacts/phase-05/toolchains/bin:$PATH"
PRESEED=$ROOT/private/artifacts/phase-05/toolchains/musl-cross-make-sources
if [ -d /tmp/toolchain-sources ]; then PRESEED=/tmp/toolchain-sources; fi
export PRESEED
bash "$R/build-public-toolchain-host.sh" "$ROOT/private/artifacts/phase-05/toolchains/musl"
