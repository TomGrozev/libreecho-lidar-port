# Artifact cleanup, 2026-11-22

Host only; owner-approved list. Freed 1.3 GB. Sizes before deletion are in
`artifact-cleanup-du.txt`; bundle and image hashes are in `artifact-cleanup-sha256.txt`.

## Deleted

| Path under `artifacts/phase-06/` | What | Why it was safe |
| --- | --- | --- |
| `ota-step33-fixes/`, `ota-step35-als/` | v0.2.26 and v0.2.27 OTA bundles and generation trees | Signed with the lost lab key (fail against `phase-05/ota/lab-key/ed25519-public.hex`), so the device rejects them. Every payload and manifest is byte-identical to a kept copy in `phase-05/ota/assets/` or `features-airplay2-latency/` |
| `features-airplay2-lidar/ota/`, `features-airplay2-lidar/ota-0.2.16/`, `features-airplay2-drain/ota/` | v0.2.15, v0.2.16 and v0.2.17 OTA bundles and generation trees | Same two checks |
| `images-step35-als/` | v0.2.27 boot images | No builder reads them. Both slots hold v0.2.28 `a7b266b7…` (`../phase-06/hw-20261121/step37-rekey/build.md:191`) |
| `acm/` | USB-ACM probe boot image | No builder reads it |
| `components/ui-bundle-c09551f/`, `components-step35-als/`, `components-step36-v0228/` | Superseded UI bundles | No builder default or script names them. Each one rebuilds from its UI commit |

`artifacts/tmp-probe/` and `artifacts/tmp-verify/` were empty and are removed.

Method: a walk of `artifacts/`, `experiments/`, `keys/` and the Platform, product and UI
repositories found no symlink into the deleted paths. The remaining text references are in
step logs and install scripts of steps 20-22, 34 and 35. Those scripts cannot run against the
current key anyway.

After deletion, every path in `features-airplay2-latency/feature-catalog.json` resolves and
matches its sha256. The installed v0.2.28 bundle, its generation tree, both lab-key copies, the
current kernels and UI bundles, and `images-step37-v0228/boot-lidar-v2.img` (`a7b266b7…`)
are present.

## Kept on purpose

- `ota-step37-v0228/generations/*/features/`: `step37-rekey/install_ota.sh:41` pushes
  the generation tree to the device, so the payloads stay with it.
- `latency/`: `latency/engine/root` is the staging tree that the current AirPlay payload was
  built from (`features-airplay2-latency/staging/mksquashfs.log:4`).
- `features-airplay2-lidar/{work,root,staging}` and `features-airplay2-drain/{work,root}`:
  the engine build uses the tinyalsa source in `work/` (`step33-latency-fix/engine.md:69`).
- `kernel-base/`: `kernel/README.md:14` points at `kernel-base/README.md` for the record of
  which commits were carried over.
- `phase-05/toolchains/musl-cross-make-sources/`: the seven musl-cross-make source
  tarballs with `SHA256SUMS`, copied out of `runner-tmp` and checked against it. They are
  the default `PRESEED` input of `step37-rekey/run_toolchain_host.sh`.

## runner-tmp removal

`phase-05/toolchains/runner-tmp/` (2.3 GB, the musl-cross-make build tree) was deleted
once a UI bundle build passed with it moved aside: `build_components_step37.sh ui`, run
from a copy with `COMP=/tmp/rt-check/comp` and `UI_SOURCE` set to the Lidar UI branch
(`0b1bb52`), exited 0 and wrote `ui-manifest.txt`. The tree is rebuilt if a toolchain
rebuild ever runs, because `run_toolchain_host.sh` sets `RUNNER_TEMP` to it.
