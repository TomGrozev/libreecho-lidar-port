# Installing LibreEcho on a new Echo Plus 2nd Gen (Lidar)

You start with a stock Echo Plus 2nd Gen (codename `lidar`, MediaTek MT8167) and
finish with a running LibreEcho install: prepare the boot chain with
`lidar_prepare.py`, run the product installer
(`tools/libreecho-install.py --target lidar`), then validate the result. The
plan for this flow is [docs/plan.md](plan.md), Phase 7, "Desired final user
flow". How the port itself was built is [BUILDING.md](../BUILDING.md).

> [!WARNING]
> This port is experimental and not released. Nothing here is a support claim.
> The installer path (the product installer writing `boot_a`, `boot_b` and
> `userdata` over Kaeru fastboot) is hardware-proven on one development unit in
> Phases 5 and 6. Everything before it is not: `lidar_prepare.py` has passed
> host tests only and has never run on a device, and no fresh unit has gone
> through this guide end to end. Treat every unproven step as a first run,
> record what happened, and stop at any refusal instead of working around it.
> The preparation command refuses a stage on a failed check (exit code 2 is a
> refusal); a refusal means the unit state or the inputs are not what the
> reviewed procedure expects.

Safety rules that apply throughout (see [boot-chain-safety.md](boot-chain-safety.md)):

- Every hardware write or reboot needs your approval. The `drill` and
  `install` stages refuse without `--yes` for exactly this reason.
- Never write BOOT1 (eMMC boot area 2). The preparation command reads it before
  and after `install` and refuses if it changed.
- Never write or erase `expdb` except through the preparation command's
  `install` stage, which writes only the reviewed Kaeru LK stage and checks the
  partition's first 16 bytes first. After Kaeru is installed, never restore
  `expdb` alone.
- Keep the stock backup. If a preparation stage fails after `backup`, the
  backup directory is the only way back to stock.

The product fork documents the same flow on its side at
[docs/install/lidar.md](https://github.com/TomGrozev/LibreEcho/blob/feature/lidar-support/docs/install/lidar.md).
The usage, stage list and safety rules of the preparation command are in its
[prepare README](https://github.com/TomGrozev/LibreEcho-Platform/blob/feature/lidar-support/tools/mt8167-arm64/prepare/README.md).

## The whole journey

![Install flow with recovery paths](diagrams/install-flow.svg)

## What changes on the device

A stock unit boots this chain: the BROM (boot ROM) hands off to the preloader
in BOOT0 area 1, the preloader loads `tee1` (ATF plus OP-TEE), then LK, and LK
verifies and loads the kernel from `boot_a` or `boot_b`.

The `install` stage replaces three links:

1. `expdb` receives the source-built Kaeru LK stage, padded with zeros to
   0x40000. Kaeru becomes the bootloader the chain reaches after tee1; it
   provides fastboot and picks the A/B slot through the BCB record in `misc`.
2. `tee1` receives the source-built Koboreru image followed by the stock
   `tee1` tail from the verified backup. The tee1 header sits outside the
   preloader's signature, which is how Koboreru is loaded first and patches
   the chain in RAM.
3. BOOT0 area 1 receives the signed 2019 preloader, taken from the verified
   backup's `boot0` file and written bytes 512..end first, sector 0 last. The
   backup's preloader must hash to the reviewed 2019 signed image; any other
   preloader is refused.

BOOT1 (area 2) is never written. The unit's BOOT1 holds device-unique data,
and the command reads it before and after `install` to prove it stayed
unchanged. `boot_a` and `boot_b` are not touched at this point; the LibreEcho
installer writes them later, over Kaeru fastboot.

![Boot chain before and after: preloader, tee1 and LK are replaced](diagrams/boot-chain-before-after.svg)

## Before you start

### Host

You need a Linux host with Python 3, `git`, `curl`, `make`, `dpkg-deb`, `adb`,
`fastboot`, `e2fsprogs` (`mke2fs`, `dumpe2fs`), and `pyusb` for the Lidar
fastboot reads (`python3 -m pip install pyusb`; on Debian the package is
`python3-usb`). The installer refuses to start the Lidar chain check without
`pyusb`. Check them with `command -v adb fastboot mke2fs dumpe2fs`.

### Hardware

- You need a data-capable USB cable and a way to reach the Lidar's USB pads.
  Your unit has no external USB port; the pads sit on the base board. Per the
  Phase 1 evidence in [docs/plan.md](plan.md), TM4 is D+, TM5 is D- and TM37 is
  GND; TM33 sits nearby at about 18 V and must be insulated. If the board does
  not enumerate, swapping the two data wires is safe. The Echo 2nd Gen's
  [connect procedure](https://github.com/aslater3/LibreEcho/blob/main/docs/install/README.md#2-connect-the-device)
  shows the same kind of pad work.
- Unplug the power adapter before you touch the pads. Never probe a powered
  board.

### Build inputs

The preparation command takes the Amonet checkout and two built images, and the
installer also needs a lab build bundle. You build them from the forks the
workspace clones; nothing comes from a reference ZIP, and the command pins the
image digests and refuses others.

From a fresh clone of this repository:

```sh
git clone https://github.com/TomGrozev/libreecho-lidar-port && cd libreecho-lidar-port
python3 tools/workspace.py init
```

`init` clones the forks into `work/forks/` (see [BUILDING.md](../BUILDING.md)
for what it fetches). Then build the two source-built stages:

- **The Kaeru LK stage** (`lidar-kaeru.bin`): build the Kaeru fork with its
  Lidar config:
  `./build.sh lidar <stock-lk-image>` in `work/forks/kaeru/`, which writes
  `lidar-kaeru.bin` (the usage, and the Lidar defconfig
  `configs/amazon/lidar_defconfig`, are in the fork). The stage is patched
  from a stock LK donor, so the donor bytes must be your own readback.
- **The Koboreru image** (`tee-payload-lidar.img`): run
  `./build.sh lidar` in `work/forks/amonet-koboreru/`, which composes
  `build/lidar/payload.bin` with the donor TEE into `tee-payload-lidar.img`.
- **The Amonet checkout**: the `work/forks/amonet` clone with
  `modules/lidar_brom.py` (the Lidar BROM adapter), on branch
  `mt8167-lidar`. `workspace.py init` creates it; you only pass its path as
  `--amonet`.
- **The lab OTA release directory**: the LibreEcho installer still needs a lab
  build bundle (`--release-dir`) because no `lidar-v*` release exists. Build
  one with `python3 tools/lab-build.py build`, which writes the signed OTA and
  its provenance under `work/builds/v<version>/` (see
  [BUILDING.md](../BUILDING.md)).

Hash the two images and keep the digests for the commands below:

```sh
sha256sum <path-to>/lidar-kaeru.bin <path-to>/tee-payload-lidar.img
```

### Session directory

Keep one directory per unit, for example `<session-dir>/`, and put everything
the flow produces in it:

```text
<session-dir>/
  backup/                  # backup output, manifest and drill-report.json
  stock-boot-report.json   # written by stock-boot
  prepare.jsonl            # the run log, when you use run
  donor-artifacts/         # generated by install from the verified backup
```

Keep this directory. It holds the only copy of the stock boot chain and the
reports later steps require.

## The steps

Each step has the same structure. Run the stages in order and review each
stage's output before the next. If you prefer one command, the `run` subcommand
chains them (step 9); use it only after you have walked the stages once, and
read its dry run first.

| Step | Command | Writes to the unit? | Proven on hardware? |
| --- | --- | --- | --- |
| 1. Enter BROM | (buttons and USB) | no | yes |
| 2. Dry run | `lidar_prepare.py --dry-run run ...` | no | no |
| 3. Identify | `lidar_prepare.py identify` | no | no |
| 4. Back up | `lidar_prepare.py backup` | no | no |
| 5. Drill | `lidar_prepare.py drill --yes` | yes, identical bytes | no |
| 6. Stock boot check | `lidar_prepare.py stock-boot` | no (reboot only) | no |
| 7. Install chain | `lidar_prepare.py install --yes` | yes: expdb, tee1, BOOT0 | no |
| 8. Confirm | `lidar_prepare.py confirm` | no | no |
| 9. All-in-one (optional) | `lidar_prepare.py run` | as steps 3 to 8 | no |
| 10. Install LibreEcho | `libreecho-install.py --target lidar` | yes: userdata, boot_a, boot_b | yes, dev unit |
| 11. Validate | `adb` checks | no | yes, dev unit |

### 1. Enter BROM

**What this does.** Puts your stock unit into the MT8167 boot ROM's USB
download mode, where the Amonet adapter can talk to it.

**Run.**

1. Unplug the power adapter.
2. Connect USB to the pads.
3. Hold the action button and apply power.

**You should see.** The host sees a MediaTek preloader USB device
(`0e8d:0003`; a normal boot enumerates `0e8d:2000` instead). Check with
`lsusb`.

**If it fails.** Reseat the cable and retry; if it still does not enumerate,
swap the two data wires. Do not probe a powered board.

### 2. Dry-run the preparation command

**What this does.** Prints every Amonet and fastboot command the run would
execute, validates the local input files and their digests, and writes
nothing. Use it to check the inputs and the paths before any device access.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    --dry-run \
    run --session-dir <session-dir> \
    --kaeru <path-to>/lidar-kaeru.bin --kaeru-sha256 <hex> \
    --koboreru <path-to>/tee-payload-lidar.img --koboreru-sha256 <hex> \
    --yes --stock-boot-ok
```

`<platform-checkout>` is `work/forks/LibreEcho-Platform` after `init`, or the
Platform fork cloned on its own. The flags are the same for every stage:
`--amonet` names the Amonet checkout (`AMONET` in the environment serves the
same purpose, and there is no default), `--dry-run` prints instead of running,
and `--log` names a JSON-lines log (with `run`, the log defaults to
`<session-dir>/prepare.jsonl`).

**You should see.** Every planned command printed, and exit code 0.

**If it fails.** Fix the named input path or digest and rerun. A missing
Amonet checkout or one without `modules/lidar_brom.py` exits 1 with a message
naming `--amonet` and `AMONET`.

### 3. `identify`

**What this does.** Reads the GPT and the device identity through the Amonet
adapter and checks the hwcode (0x8167), the user-area size, the boot-area size,
the sector size, and the reviewed partition layout. It writes nothing to the
device.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> identify
```

**You should see.** The reported identity and partition layout. Check that it
matches the reviewed table in the output.

**If it fails.** Stop. A mismatch means this unit is not the layout the
reviewed procedure expects; do not continue on this unit.

### 4. `backup`

**What this does.** Reads every backup-set area (BOOT0 area 1, BOOT1, the GPT
and its backup, `lk_a`, `lk_b`, `tee1`, `tee2`, `expdb`, `misc`, `persist`)
twice, writes the first read, and requires the second read to hash
identically. It then writes and verifies a backup manifest. It never
overwrites an existing backup.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    backup --backup-dir <session-dir>/backup
```

**You should see.** A populated `<session-dir>/backup/` with one file per area
and a verified `backup-manifest.json`.

**If it fails.** Stop and keep the log. The backup is the only way back to
stock; do not run any later stage without it.

### 5. `drill` (the first write)

> [!WARNING]
> This is the first write to the unit. It needs your approval, and it refuses
> without `--yes`. The risk is unchanged by the tool: a power loss mid-write is
> the same risk the manual drill carried.

**What this does.** Re-reads each backup-set area, compares it with the
backup, then rewrites the identical bytes back and verifies the readback, in
the phase-2 order. BOOT0's body is written before its sector 0 (last). BOOT1
is read and verified but never written. The drill proves that writes work
before any real chain byte changes.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    drill --backup-dir <session-dir>/backup --yes
```

**You should see.** Per-area comparisons and verified readbacks, and a drill
report (default `<session-dir>/backup/drill-report.json`).

**If it fails.** Stop and keep the log. The unit should still be stock (the
drill wrote identical bytes), but report the failure instead of retrying.

### 6. Power-cycle and `stock-boot`

**What this does.** Proves your unit still boots stock normally after the
drill, and records your confirmation in a report file that the `install` stage
requires.

**Run.**

1. Unplug the power adapter and disconnect USB.
2. Apply power and let the unit boot stock normally.
3. Unplug the power again, then re-enter BROM (step 1).
4. Record the confirmation:

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    stock-boot --report <session-dir>/stock-boot-report.json
```

**You should see.** The unit boots stock (normal light ring, no fastboot), and
the command writes the report. Pass `--confirmed` to record a confirmation
non-interactively; otherwise the command asks.

**If it fails.** If the unit does not boot stock after the drill, stop and
report; do not run `install`.

### 7. `install`

> [!WARNING]
> This stage writes the boot chain. It needs your approval, and it refuses
> without `--yes`.

**What this does.** Installs the custom boot chain in the reviewed order: it
generates the donor-derived artifacts from the verified backup (the signed
preloader and the stock tee1 tail; the generator refuses to write inside a
checkout outside a `private`, `local` or `local-firmware` directory), requires
the backup's preloader to hash to the reviewed 2019 signed image, writes
expdb first, reads back expdb's first 16 bytes and requires the MTK magic
before touching tee1, writes the composed tee1, then writes the BOOT0 preloader
(bytes 512..end first, sector 0 last). BOOT1 is read before and after and must
be unchanged.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    install \
    --backup-dir <session-dir>/backup \
    --drill-report <session-dir>/backup/drill-report.json \
    --stock-boot-report <session-dir>/stock-boot-report.json \
    --kaeru <path-to>/lidar-kaeru.bin --kaeru-sha256 <hex> \
    --koboreru <path-to>/tee-payload-lidar.img --koboreru-sha256 <hex> \
    --yes
```

**You should see.** The donor artifact digests, the expdb write and readback,
the tee1 write, the BOOT0 write in sector-0-last order, and a final BOOT1
unchanged check.

**If it fails.** Stop and keep the log. The stage refuses on a failed check
(exit code 2); a re-run after a partial install skips the expdb write only
when expdb already holds the byte-identical expected Kaeru stage, and refuses
any other installed expdb content. See Recovery.

### 8. `confirm`

**What this does.** Requires the new Kaeru fastboot to report the Lidar
product. It writes nothing.

**Run.**

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> confirm
```

(With `--dry-run` the command prints the fastboot call instead of running it;
pass `--fastboot <path>` if `fastboot` is not on `PATH`.)

**You should see.** `fastboot getvar product` answering `LIDAR`.

**If it fails.** Do not make an identity decision from a failed or ambiguous
answer. Power-cycle into fastboot again (hold the action button at power-on
once the Kaeru chain is installed) and retry; if it still does not report
`LIDAR`, stop and report.

### 9. Alternative: one `run` command

**What this does.** Chains `identify`, `backup`, `drill`, `install` and
`confirm` from one session directory. It does not chain the power-cycle: the
`run` command stops for the stock boot, and either you confirm it
interactively or `--stock-boot-ok` records a prior confirmation. `drill` and
`install` still refuse without `--yes`.

**Run.** First a dry run (step 2), then:

```sh
python3 <platform-checkout>/tools/mt8167-arm64/prepare/lidar_prepare.py \
    --amonet <path-to-amonet-checkout> \
    run --session-dir <session-dir> \
    --kaeru <path-to>/lidar-kaeru.bin --kaeru-sha256 <hex> \
    --koboreru <path-to>/tee-payload-lidar.img --koboreru-sha256 <hex> \
    --yes --stock-boot-ok
```

**You should see.** The stage sequence with one log at
`<session-dir>/prepare.jsonl`, stopping at the stock-boot gate.

**If it fails.** The log names the stage and the check. Continue with the
individual stages from where it stopped.

### 10. Install LibreEcho (`--target lidar`)

**What this does.** Runs the product installer, which writes LibreEcho to the
boot slots over Kaeru fastboot. The Lidar target uses the "already converted"
pin rule: the installer asks `fastboot oem kaeru-version` and refuses to write
anything to a unit that does not answer as Kaeru (there is no Amonet payload
for Lidar, so the installer itself never writes a boot-chain byte). Before
every flash write it reads `expdb[0:16]` over fastboot (through Kaeru's
`fetch` with `oem fetch-enable`, over USB with `pyusb`) and refuses unless it
starts with the MTK magic `88 16 88 58`. It formats userdata, writes
`userdata`, `boot_a` and `boot_b` only, and verifies the readback of both boot
slots.

**Run.** From a checkout of the LibreEcho product fork (the integration
worktree `work/integration/LibreEcho` carries the branch the lab build came
from):

```sh
python3 tools/libreecho-install.py \
    --target lidar \
    --release-dir <path-to>/work/builds/v<version> \
    --release-tag <tag>
```

`<tag>` is the release tag recorded in the build's `provenance.json`
(`release`). No `lidar-v*` release is published, so `--release-dir` with a lab
build is the only source today.

**You should see.** The chain checks, the slot writes with verified readbacks,
and the first boot. The installer writes a per-run log.

**If it fails.** Keep the log. A refusal names the check that failed. If the
installer stopped mid-write, it archives its state and refuses to restart an
unfinished install without `continue-one-shot` (same release) or `one-shot
--reinstall` (erases userdata and rewrites both boot slots, never re-sends a
brick payload).

### 11. Validate

**What this does.** Confirms the install is healthy before you rely on the
unit.

**Run.**

```sh
adb devices
adb shell cat /etc/libreecho/target
adb shell cat /data/libreecho/update/boot-health
adb shell dmesg | grep -E 'Oops|BUG:|panic' || echo "no panic lines"
```

**You should see.**

- `adb devices` shows the unit; the web control centre answers on the unit's
  address.
- `/etc/libreecho/target` reads `target_id=lidar`, `release_slug=lidar`,
  `hw_profile=lidar@1`.
- `boot-health` (or `libreecho-update status`) reports `state=confirmed` on
  the expected slot.
- No `Oops`, `BUG:` or panic lines in `dmesg`.
- Wake word, speaker playback, the LED ring and the buttons respond as in the
  Phase 6 feature sweep ([lab-notes/phase-06/hw-20261121/](../lab-notes/phase-06/hw-20261121/)).

**If it fails.** A slot that does not boot falls back automatically: the LK
tries counter rolls back to the other slot after three failed boots (proven on
the development unit in every Phase 5 to 7 deploy). Check
`/data/libreecho/update/boot-history` for what happened, and see Recovery.

## Recovery

| Failure | Action |
| --- | --- |
| Preparation failed after `backup` | You can return the unit to stock from the backup directory with the Phase 2/3 restore tooling and the drill report. That tool reaches the unit through mtkclient. [lab-notes/phase-02/restore/README.md](../lab-notes/phase-02/restore/README.md), "mtkclient adapter", gives the setup. Never restore `expdb` alone ([boot-chain-safety.md](boot-chain-safety.md)). |
| `install` refused after a partial write | Keep the log. A re-run skips the expdb write only when expdb already holds the byte-identical expected Kaeru stage. Any other installed expdb content is refused. Report the state before any further write. |
| Installer stopped mid-write | Rerun the installer. It archives its state and refuses to restart an unfinished install without `continue-one-shot` or `one-shot --reinstall`. |
| Slot does not boot | Wait: the LK tries counter rolls back to the other slot after three failed boots. Then check `boot-history`. |
| After Kaeru: return to fastboot | Hold the action button at power-on. The Kaeru chain boots to fastboot like the other targets. |
| After Kaeru: return to stock | This guide does not authorise such a procedure. Any later stock recovery needs a separately reviewed full-chain BROM procedure. Never restore `expdb` alone. |

## What to send back

Return a directory with:

1. The preparation session directory: the `identify` output, the backup
   manifest and its hashes, the drill report, the stock-boot report and the
   `install` readback output.
2. The installer log (`tools/libreecho-install.py` writes a per-run log).
3. The OTA and boot state files: `/data/libreecho/update/boot-health`,
   `boot-history`, `installed` and `state`, pulled over adb.
4. The `SHA256SUMS` and `provenance.json` of the build that was installed.
5. A short note of what worked and what refused, with the exact commands.

Do not include device serials, MAC addresses or Wi-Fi credentials in anything
you share.
