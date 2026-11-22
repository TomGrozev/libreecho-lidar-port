#!/usr/bin/env bash
# Run RebuildRekey's host-adapted product toolchain script under the single
# owner lock, with the curl shim and an optional pre-seeded source directory.
set -euo pipefail
ROOT=/workspace/libreecho
R=$ROOT/experiments/phase-06/hw-20261121/step37-rekey
exec 9>/tmp/libreecho-toolchain.lock
flock 9
export RUNNER_TEMP=$ROOT/artifacts/phase-05/toolchains/runner-tmp
export JOBS=12
export PATH="$ROOT/artifacts/phase-05/toolchains/bin:$PATH"
if [ -d /tmp/toolchain-sources ]; then export PRESEED=/tmp/toolchain-sources; fi
bash "$R/build-public-toolchain-host.sh" "$ROOT/artifacts/phase-05/toolchains/musl"
