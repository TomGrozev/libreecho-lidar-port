#!/bin/bash
# Single-owner wrapper so a duplicate launch cannot clobber the shared
# runner-tmp tree (two concurrent builds previously raced and corrupted it).
set -euo pipefail
exec 9>/tmp/libreecho-toolchain.lock
flock -n 9 || { echo "toolchain build already running" >&2; exit 3; }
cd /workspace/libreecho
JOBS=12 bash experiments/phase-05/build_components.sh toolchain
