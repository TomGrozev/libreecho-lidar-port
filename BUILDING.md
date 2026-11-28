# Building the Lidar port

You build the Lidar port of [LibreEcho](https://github.com/aslater3/LibreEcho) from a fresh
clone of this repository. The build runs inside a pinned container image, so the host needs
podman and a few standard tools, not a compiler toolchain.

**Status.** The clean-clone path has host evidence only. Nothing here is a support claim.
[docs/status.md](docs/status.md) gives the current state and
[docs/install-new-lidar.md](docs/install-new-lidar.md) covers the device side.

## Quickstart

From a fresh clone:

1. **Prepare the workspace.**

   ```sh
   git clone https://github.com/TomGrozev/libreecho-lidar-port && cd libreecho-lidar-port
   python3 tools/workspace.py init
   ```

   This clones the forks named by [integration.json](integration.json), rebuilds the
   integration branches and their lock, prepares the build image, and fetches the public
   build inputs into `work/inputs/`. It then builds the Amonet BROM payload
   (`work/integration/amonet/brom-payload/build/mt8167/payload.bin`), which the device
   steps load in every BROM session. The payload needs no data from the device.

   The build image comes from `build_image` in [tools/lab-build.json](tools/lab-build.json).
   With a digest it is pulled as `name@digest`. With a null digest, `init` builds the local
   tag `libreecho-build:local` from the product's
   `build/container/Containerfile`. `--build-image` forces the local build;
   `--no-image` skips this step and builds the Amonet payload with host tools. The image
   carries the Ubuntu 24.04 CI runner baseline, the host packages, and CPython 3.11.

2. **Generate the OTA signing key pair.**

   ```sh
   python3 tools/workspace.py keygen
   ```

   This writes an ed25519 key pair at the paths `private/local.json` names
   (`private/keys/ota-lab/` by default).

3. **Read the stock boot image from the device.** The build needs your unit's stock
   `boot_a`. Read it on the device side with steps 1 to 4 of
   [docs/install-new-lidar.md](docs/install-new-lidar.md): enter BROM, run `identify`, run
   [`backup`](docs/install-new-lidar.md#3-backup), then
   [read `boot_a`](docs/install-new-lidar.md#4-read-the-stock-boot-image-boot_a). The
   `backup` stage does not save `boot_a`; step 4 writes it to `<session-dir>/boot_a.bin`.
   Read it before the LibreEcho installer overwrites `boot_a`.

4. **Point `private/local.json` at the stock boot image.** `keygen` created
   `private/local.json` from [tools/local.example.json](tools/local.example.json). Set
   `stock_boot` to the path of `<session-dir>/boot_a.bin`; a relative path counts from the
   repository root. Set `device_host` too if you know the device's Wi-Fi adb address.

5. **Check the workspace.**

   ```sh
   python3 tools/workspace.py doctor
   ```

   You get one list of everything still missing: host tools, podman and the build image,
   free disk below 20 GB, clones, branches, inputs, and empty `private/local.json` entries.
   Keep running it until the list is empty.

6. **Build the lab OTA.**

   ```sh
   python3 tools/lab-build.py build
   ```

   The build runs in the pinned image and writes the deliverables under
   `work/builds/v<version>/`: the signed OTA bundle (`libreecho-*.ota.tar`), `SHA256SUMS`,
   `provenance.json`, the product run and the logs. The version defaults to the highest
   existing build plus one patch; pass `--version X.Y.Z` for the first build. The step is
   host-only and never touches a device.

7. **Build the boot-chain images (optional; needs a device backup).**

   ```sh
   python3 tools/lab-build.py boot-chain --backup-dir <session-dir>/backup --out <session-dir>/images
   ```

   This builds Kaeru and Koboreru from the `lk_a.bin` and `tee1.bin` of the `backup` stage,
   for [step 5 of the install guide](docs/install-new-lidar.md#5-build-the-boot-chain-images).
   See [What `lab-build.py boot-chain` runs](#what-lab-buildpy-boot-chain-runs).

8. **Deploy (optional; writes the device).**

   ```sh
   python3 tools/lab-build.py deploy <version> --host <device>:5555 --yes
   ```

   This installs the OTA on the device's inactive boot slot over Wi-Fi adb, reboots, and
   polls until the device reports the expected generation. Each deploy is a hardware write
   and reboot, so each one needs your approval; the command refuses without `--yes`.

## Build in CI

`.github/workflows/lab-build.yml` runs the same build on a self-hosted runner, so you do
not need a local podman. Two commands start a build and collect its result:

```sh
python3 tools/lab-build.py push
python3 tools/lab-build.py fetch          # latest successful run
```

`push` fast-forwards each fork and the port's `main`, then dispatches the workflow. The job
runs inside the pinned build image and keeps `work/` on a persistent cache volume. It builds
with a stock boot and a signing key that the runner mounts read-only, and uploads the whole
build directory as the `libreecho-lidar-ota` artifact. `fetch` downloads that artifact,
verifies every entry in `SHA256SUMS` and installs it as `work/builds/v<version>/`, so
`deploy` works unchanged.

CI artifacts are **public** and are kept for 7 days. They contain the stock-boot-derived
OTA and the product run directory (`run/`), including Amazon stock DTBs and the boot
header copied from `stock_boot`. The raw inputs themselves (`boot_a.bin` and the OTA
signing seed) never leave the runner. A workflow guard fails the upload if a file whose
sha256 matches either one appears in the build directory.

The workflow runs only on `workflow_dispatch`, never on a pull request.

## The pipeline

![Build pipeline: three inputs produce a signed OTA; deploy is approval-gated.](docs/diagrams/build-pipeline.svg)

## Host prerequisites

The build image provides the compilers, the cross toolchains and python3.11. The host needs:

- Linux x86_64; the image is amd64 only.
- `python3` and `python3.11`. The pinned mbedTLS wheel closure targets CPython 3.11.
- `git`, `curl`, `make`, `dpkg-deb` and `rsync`. `workspace.py doctor` checks each one.
- `podman`. The build runs rootless in the image.
- About 20 GB of free disk for the image, the inputs and the build output.
- `adb` over Wi-Fi for `deploy`.

Network access is needed for the first `init`: it clones the forks and fetches the inputs by
URL and sha256.

## Workspace tiers

Two gitignored directory trees sit beside the repository files:

| Tier | Holds | Why |
| --- | --- | --- |
| `work/` | `work/forks/<repo>`, `work/integration/<repo>` with `integration.lock.json`, `work/inputs/`, `work/product-build/`, `work/builds/` | Regenerable. `workspace.py init` recreates the clones, the integration worktrees, the image and the fetched inputs; a build recreates the rest. |
| `private/` | `private/local.json` (input paths), the OTA signing keys and the stock boot image | Private material. It holds Amazon firmware and private keys, so it is never published and never committed. |

`private/local.json` is created from [tools/local.example.json](tools/local.example.json)
and names `ota_signing_key`, `ota_public_key` and `stock_boot`, plus the optional
`device_host`.

## Private inputs

Two build inputs cannot come from the repository:

- **The stock boot image** (`stock_boot`): a readback of the device's `boot_a` partition.
  The `backup` stage of `lidar_prepare.py` leaves `boot_a` out; step 4 of
  [docs/install-new-lidar.md](docs/install-new-lidar.md#4-read-the-stock-boot-image-boot_a)
  reads it. The MT8167 image builder re-frames this stock image rather than synthesising
  one, and it checks the 19 stock DTBs against pinned hashes, so the bytes must come from
  the Amazon firmware version the port expects. They are Amazon firmware, not data unique
  to one unit. Redistributing them is not cleared, so they stay out of git.
- **The OTA signing key pair** (`ota_signing_key`, `ota_public_key`): generated locally by
  `python3 tools/workspace.py keygen`. The signing key is private and must never be
  committed or shared; the public key is installed into the image and travels with the
  bundle.

A build refuses to start without both. The private inputs never leave the machine that
holds them: in CI the runner mounts them read-only and a guard refuses to upload their
exact bytes. The OTA they produce is public, so a CI artifact carries Amazon stock DTBs and
the boot header copied from the stock boot.

## What `lab-build.py build` runs

`python3 tools/lab-build.py build` holds a lock on `work/builds/.build.lock`, rebuilds the
per-repo integration branches with `tools/integrate.py` and verifies the lock, then drives
the product's own build (`build/build.sh --target lidar --profile ota --no-publish`) from
the LibreEcho integration worktree inside the pinned image. It writes the signed OTA and its
provenance under `work/builds/v<version>/`.

Each build is an attempt directory named by its version and a source id. A successful
attempt with the same source id is reused on the next run; pass `--rebuild` to build again.
Failed attempts stay under `work/builds/` for inspection, and the five newest are kept. A
promoted build is `work/builds/v<version>/`.

The other options:

- `--no-integrate` skips the integration rebuild.
- `--lock PATH` reads another lock and implies `--no-integrate`.
- `--no-container` builds with the host toolchain instead of the image.
- `--stock-boot`, `--ota-signing-key` and `--ota-public-key` override
  `private/local.json`.

The full environment variable list for the product build (build roots, toolchain
variables, the stock boot and key paths, the OpenThread Border Router source) is
authoritative in the product fork's `build/README.md`, section "Building Lidar locally";
read it at `work/forks/LibreEcho/build/README.md` after `init` rather than copying values
from here.

`deploy` installs a finished build over Wi-Fi adb: it rechecks the deliverables against
`provenance.json`, seeds the device's content-addressed asset cache, has the device assemble
the generation from the signed manifest without network access, installs the OTA on the
inactive slot, reboots and polls until the device reports the expected generation. Each
deploy is a hardware write and reboot; the command refuses without `--yes`.

## What `lab-build.py boot-chain` runs

`python3 tools/lab-build.py boot-chain --backup-dir DIR --out OUT` builds the two
boot-chain stages that the `install` stage of `lidar_prepare.py` writes:

- Kaeru (`lidar-kaeru.bin`) from the stock LK in `DIR/lk_a.bin`.
- Koboreru (`tee-payload-lidar.img`) from the stock TEE in `DIR/tee1.bin`.

The command refuses when either donor file is missing. When the backup manifest is present,
it also refuses a donor file whose digest does not match the manifest.

The build copies the Kaeru and Koboreru integration worktrees to a scratch directory under
`work/` and builds there, so it leaves no files in `work/integration/`. By default it runs
in the pinned build image. The Arm GNU Toolchain releases for `arm-none-eabi` and
`arm-none-linux-gnueabihf` are fetched into `work/inputs/` by URL and sha256, like the other
public inputs. The Python packages, with `liblk` pinned to a commit, go into a venv under
`work/`. `--no-container` uses the host toolchains and Python packages instead; the
[install guide](docs/install-new-lidar.md#host) lists them.

The output directory receives `lidar-kaeru.bin`, `tee-payload-lidar.img`, `SHA256SUMS` and
`provenance.json`. The provenance records the source heads from the integration lock, the
donor digests and the toolchain digests. The images embed Amazon LK and TEE bytes, so the
command refuses an output directory inside a git checkout unless it is under that
checkout's `private/`. It ends by printing the `--kaeru`, `--kaeru-sha256`, `--koboreru` and
`--koboreru-sha256` flags for `lidar_prepare.py`, with the real paths and digests. No image
from this command has run on a device yet.

## Building is the host side

The device side, from a stock Echo Plus 2nd Gen to a running LibreEcho install, is
[docs/install-new-lidar.md](docs/install-new-lidar.md). No fresh unit has run that path end
to end yet, and the guide marks which steps are not hardware-proven.
