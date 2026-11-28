#!/usr/bin/env bash
# In Kaeru fastboot: read the ramoops window the installed LK maps (0x43810000, 0x60000),
# which is only useful for a kernel that places ramoops there or for a warm reset that kept
# DRAM. Kept separate so the fetch runs before any flash on the next boot cycle.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
out=$root/lab/phase-06/hw-20261121/step4-ramoops
mkdir -p "$out"
{
  date -u +%FT%TZ
  fastboot getvar product
  fastboot getvar kaeru-version
  fastboot oem fetch-enable
  fastboot getvar max-fetch-size
  fastboot getvar partition-size:ramoops
  fastboot fetch ramoops "$out/ramoops.bin"
  sha256sum "$out/ramoops.bin"
  stat -c '%s bytes' "$out/ramoops.bin"
} 2>&1 | tee "$out/fetch.log"
