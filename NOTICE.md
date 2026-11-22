# Notices

This file records third-party and derived material in the repository and the
license that covers each item. `LICENSE` covers original material written for
this port.

## lidar-mainline

Source: https://github.com/LeagueRaINi/lidar-mainline

The kernel and U-Boot porting work compares against this mainline effort.
License is per file: most code is GPL-2.0, device tree files are GPL-2.0+ OR
MIT, and Wi-Fi driver files are GPL-2.0 OR BSD-3-Clause. The comparison is
recorded in `experiments/phase-04/lidar-mainline-comparison.md`. Several files under
`experiments/phase-06/hw-20261121/step25-efr32/` derive from it: `8250_mtk.diff`
patches its serial driver, `mkgbl.py` comes from its `efr32/` tools, and the shell
scripts whose header names lidar-mainline mirror its `tools/lidar-efr32.sh` and
`efr32/build.sh`. Those files, and every file there with a GPL-2.0-only SPDX
header, are GPL-2.0-only. Elsewhere the notes record facts from the comparison;
kernel patches that carry lidar-mainline code fall under the GPL-2.0 rule below.

## Kaeru and Koboreru

The owner-access boot chain is built on Kaeru (upstream AGPL) and the amonet /
Koboreru loader (upstream MIT). This repository carries no source from either
project, only logs and notes of building and installing them. The upstream
licenses apply to the built artifacts, which are not distributed here.

## mtkclient

The MediaTek flash tool used in phase 1. Its upstream license is GPL. This
repository carries a small patch (`experiments/phase-01/mtkclient-da-logframes.patch`)
written against mtkclient; that patch is GPL, derived from the tool. Notes and
logs are unaffected.

## LibreEcho, LibreEcho-UI, LibreEcho-Platform

LibreEcho (https://github.com/aslater3/LibreEcho) and LibreEcho-UI are MIT.
LibreEcho-Platform is GPL-2.0. Two consequences for this repository:

- Code under `experiments/phase-07/sendspin-silence/` that includes or copies
  Platform sources stays GPL-2.0. Confirmed cases: `last_loop.c` and
  `scratch/test_audio_engine_loop.c`, which both include `audio_engine.c` from
  the Platform checkout. In `deploy/diffs/`, `libreecho-*.diff`, `mdnsd.init.diff`
  and `init.diff` patch Platform init scripts and are GPL-2.0 for the same reason.
  `scratch/include/tinyalsa/` is a reduced local interface, not an upstream
  copy; unconfirmed against the tinyalsa upstream.
- Kernel patches and kernel-derived files elsewhere under `experiments/` stay
  GPL-2.0. Confirmed cases:
  `experiments/phase-04/hw-20261117-wdt-diag/kernel-diag-worktree-final.patch`,
  `experiments/phase-04/pre-clean-control/full-worktree.patch`, and the
  `experiments/phase-06/hw-20261121/step26-bt/btd-*.patch` Bluetooth patches.

## Stock firmware material

The decompiled stock device tree
`experiments/phase-06/hw-20261121/step36-thermal-trips/stock-pvt.dts` and the
short quotes of stock firmware strings and logs throughout the notes are
Amazon and MediaTek material. They are quoted here for interoperability
research. This repository does not license them.

## Warranty

This repository is an experiment record. It carries no support claim and no
warranty. Each license text applies without modification.
