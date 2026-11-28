# Lidar support (Echo Plus 2nd Gen): implementation plan

> This is a frozen record of the port plan as it was written and executed. It is not a live
> work queue. The current phase state and gate outcomes are in
> [docs/status.md](status.md); the boot-chain rules are in
> [boot-chain-safety.md](boot-chain-safety.md).

LibreEcho keeps Echo hardware that people already own useful, repairable and private. As of
2026-11-24, the release supported two MT8163 ARM32 models, `radar_puffin` and `biscuit`; the
product's own target list is authoritative. This plan
covers the third, the Echo Plus 2nd Gen (`Lidar`, MediaTek MT8167), and records the
implementation scope I agreed on for issue #101. No Lidar support was claimed at that date.
Every build, flash, and release step below is a future task, gated on explicit approval and
evidence.

## Accepted scope and decisions

The goal is a Lidar build with the same result you get on the shipping models: a repairable,
private assistant on hardware you already own. The issue-#101 scope below is how that gets
built.

- The deliverable of the current session is this plan, not code. A later fresh session
  executes it phase by phase.
- Use the workspace layout and session instructions in `README.md`. Run commands from the
  workspace root unless a phase names another directory.
- Initial experiments use my existing mtkclient setup and temporary local scripts. They are
  personal experimental tools. Production scripts replace them only after boot-chain
  installation and LibreEcho installation work is proven on the device.
- I work iteratively in local experimental branches across the required forks, and prepare
  PRs only after I'm satisfied with working results. No push, PR, merge, release, or hardware
  action is authorized by this plan.
- Support stays experimental and fails closed until exact live-device evidence exists.
- Start with read-only BROM/fastboot inspection. I approve each hardware write or reboot
  phase separately before it runs.
- The development Echo Plus 2nd Gen is sacrificial. USB data is available. UART is not
  required; the stock UART line (ttyS0 921600 8N1) is recorded for reference only.
- Match the installer behavior in place at that date: no full stock backup and no
  stock-system restore feature. The installer verifies identity and layout, writes the
  boot-chain payload and boot slots, formats only userdata, and verifies readback.
- The new Lidar boot-chain installation must back up BOOT0, tee1, expdb, and GPT. Before
  Kaeru is installed, it must test restoration of those partitions through a same-byte restore
  drill, readback verification, and a stock boot.
- Final support means installation, recovery, updates, networking, UI, audio playback,
  microphones, and buttons/LEDs. Full stock-system restoration is out of scope.
- Use an ARM64 kernel with the existing ARM32 userspace through `CONFIG_COMPAT`.
- Mirror the stock ARM64 MTK boot envelope and Lidar DTBs before inventing any new layout.
- Treat the supplied ZIP and the `echo-plus-2-unlock` repository as behavioral references
  only. Do not copy their code or binaries.
- Production components must carry suitable licenses and complete source. Never commit
  proprietary donor images, serials, keys, or personal data.

License constraints (they limit production redistribution, not personal experimental use):

| Component | License | Constraint |
| --- | --- | --- |
| echo-plus-2-unlock | none | Reference only; no reuse in production |
| Modified reference Kaeru | AGPL upstream; incomplete corresponding source | Reference only; do not redistribute the binary |
| Kamakiri | none | Reference only; no reuse in production |
| Koboreru | MIT | No Lidar device port exists yet; write one |
| Kaeru | AGPL | Needs a Lidar config/board port and a stock lk donor |
| mtkclient | GPL | Partition reads use a proprietary download agent; keep it out of production scripts |
| lidar-mainline (`reference/lidar-mainline`) | GPL-2.0, per-file | Copying and porting are allowed by my decision of 2026-11-21, with the license header kept and a provenance note naming the reference commit (Phase 6) |

### Preloader route decision

The Lidar chain replaces the stock 2023 preloader with the signed 2019 preloader from the
reference kit (`reference/echo-plus-2-bootchain-v0.2.1/`). It does not port Koboreru to the
stock 2023 BOOT0.

Evidence for the decision:

- The 2023 preloader verifies the PL, TEE and LK signatures, enforces RPMB anti-rollback, and
  BROM reports secure boot enabled. Its layout also differs: bss is `+0x5040` and rodata
  shifts by `+0x4a4` to `+0x6b8`, so the kit's 20 offsets do not transfer.
- Every public Echo MT8163/MT8167 port replaces the preloader with an older signed image.
  None modifies the stock preloader's stored bytes. The Koboreru mechanism is unchanged: the
  tee1 header sits outside the signature and is loaded before verification, and the LK stage
  adjusts the running preloader in RAM so the locally built LK, ATF and TEE start in place of
  the stock signed images.
- The unit's stock area 1 matches the reviewed November 2023 build string
  (`20231103_093456`). The kit's allowlist hash covers the 4 MiB composite and differs only in
  the device-unique area 2.

Write rules for the replacement:

- Write only BOOT0 area 1, the first 2 MiB of the 2019 image. Keep the unit's BOOT1 (area 2).
  The 2019 image's area 2 is all zeros, and the kit's full-4-MiB write would erase this unit's
  identity data, which has 1894 non-zero bytes. The full-4-MiB path stays a fallback and needs
  separate approval.
- Install order is expdb, then tee1, then BOOT0 area 1, with sector 0 last.

## Verified starting facts

- Product start commit: `4f5445934679d68863fc0c723b990326fc9ff3d1`.
- Issue #101 has no formal spec or acceptance criteria. This plan records the agreed scope.
- The stock dump identifies `ro.board.platform=mt8167`, an ARM64 Linux 4.4.22 kernel, a
  32-bit Android userspace, 16 MiB boot images, A/B partitions, and 19 appended DTBs
  including Lidar production variants.
- Stock UART is ttyS0 921600 8N1. The test setup is USB only.
- Action button held at power-on enters BROM mode at `0e8d:0003`. Normal boot enumerates the
  preloader at `0e8d:2000`. No eMMC short is needed.
- USB pads from issue #101: TM4 is D+, TM5 is D-, TM37 is GND. TM33 sits nearby at about
  18 V and must be insulated. The issue report did not confirm D+/D- individually; if a board
  does not enumerate, swapping the two data wires is safe.
- The existing dump lacks BOOT0, BOOT1, lk_b, boot_b, system_a, and system_b. It contains
  stock lk_a, boot_a, tee1/tee2, GPT, and other listed partitions.
- Stock tee1 SHA-256 is
  `aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e`. The reference tee1
  differs. Reference expdb is empty in my stock dump.
- At the time of writing (2026-11-24), the product schema accepted only `mt8163`/`arm32` and
  the `radar_puffin` and `biscuit` targets. Full support needs changes in LibreEcho-Linux,
  LibreEcho-Platform, LibreEcho, and LibreEcho-Installer-Web. LibreEcho-UI may need changes
  for device hardware.
- The installer at that date made no partition backups. It verifies identity and layout,
  writes the boot-chain payload and boot_a/boot_b, formats userdata, verifies readback, and
  never writes expdb on a v2 Kaeru chain.

## Boot-chain safety

The boot-chain rules bind every phase. They are in
[boot-chain-safety.md](boot-chain-safety.md).

## Repository ownership

| Repository | Responsibility |
| --- | --- |
| LibreEcho-Linux | ARM64 Lidar target, defconfig with `CONFIG_COMPAT`, DTS/DTB, drivers, CI lane |
| LibreEcho-Platform | mt8167-arm64 tools profile, image builders/verifiers, recovery, installer runtime, OTA |
| LibreEcho | Target descriptor `release/targets/lidar.json`, schema generalization, release/OTA validators, documentation |
| LibreEcho-Installer-Web | Lidar target in the hosted installer once hardware is accepted |
| LibreEcho-UI (optional) | Only if existing device-independent code cannot handle Lidar hardware |
| Kaeru fork | Lidar config/board port on upstream AGPL source, kept in my GitHub fork; no upstream PR planned |
| Koboreru fork | Lidar device definition on upstream MIT source, kept in my GitHub fork; no upstream PR planned |
| `libreecho-lidar-port` (public, my GitHub account; this workspace root) | This plan, port documentation and the generated `lab-notes/`; no code that belongs in the repositories above |

Repository structure (my decision, 2026-11-22): the boot-chain forks are referenced by
commit from the production scripts. Everything else lands as the PR stack in Phase 8.

## Safety and evidence rules

1. The original stock dump is immutable. Work on copies.
2. Sensitive data (donor images, serials, keys, personal data) stays local and never enters
   a commit, PR, or release asset.
3. Record exact hashes and commit IDs for every image and source tree used.
4. Read-only operations come first. I approve each write or reboot phase separately.
5. No hardware claim from a host test. Host, CI, image, and hardware evidence stay
   distinct.
6. No push or PR without my approval of the working results.

## Phases

Each phase ends at a gate. Do not start the next phase until the gate holds.

### Phase 0: experimental workspace

- [x] Confirm the workspace layout in `README.md` and create `experiments/phase-00/`.
- [x] Confirm the product start commit named under "Verified starting facts" and a
      clean worktree in `repos/LibreEcho/`.
- [x] Record the current main heads of each owning repository.
- [x] Clone required repositories under `repos/` and create `feature/lidar-support` branches
      locally from the verified heads. Do not require GitHub forks before local work starts.
- [x] Clone or fork external repositories only when I authorize it.
- [x] Record host dependencies in `experiments/phase-00/`: Python version, mtkclient commit,
      tools, and their versions.
- [x] Keep experiment inputs and logs under `experiments/`, device reads under `dumps/`, and
      locally built outputs under `artifacts/`. Keep them outside release assets.

Gate: the workspace matches `README.md`; required branches exist locally with recorded base
commits; no fork or push has happened.

### Phase 1: live read-only boot-chain inventory

- [x] Create `experiments/phase-01/` and a new device-read directory under `dumps/`.
- [x] Use my existing mtkclient commands that already produced the stock dump.
      Record the exact commands in `experiments/phase-01/`; do not invent new syntax.
- [x] Confirm the device enters BROM at `0e8d:0003` with the action button held at power-on.
- [x] Confirm the reported hwcode is `0x8167`.
- [x] Read BOOT0, BOOT1, a refreshed GPT, tee1, expdb, lk_a, lk_b, boot_a,
      boot_b, and misc without writing. No system or userdata dumps are required.
- [x] Save BOOT0, tee1, expdb, and GPT as the immutable stock boot-chain backup. Keep the
      other reads as local donor and reference images.
- [x] Compare refreshed images against the existing dump hashes.
- [x] Identify the BOOT0 build and any anti-rollback exposure.
- [x] Identify the production Lidar DTB among the 19 appended DTBs.
- [x] Produce a local manifest of everything read, with sizes and SHA-256 hashes.

Gate: do not treat offsets as final and do not draft a write plan until BOOT0 and the stock
LK and TEE are known from live reads.

### Phase 2: experimental boot-chain construction and restore tooling

- [x] Start from upstream Kaeru source. Derive a new Lidar config/board from the stock
      lk_a. Do not copy reference repository source or binaries.
- [x] Start from MIT Koboreru source. Derive a new Lidar device definition from the 2019
      replacement preloader, per the preloader route decision.
- [x] Extract proprietary donors locally for analysis. Never commit them.
- [x] If stock BOOT0 cannot host the chain, record the donor/preloader decision as a
      blocker. Do not silently download a replacement.
- [x] Build restore tooling before modifying anything: exact identity, size, and hash gates;
      readback verification after each write; atomic local manifests.
- [x] When BOOT0 changes, write BOOT0 sector 0 last.
- [x] Exercise restore tooling against synthetic images and fault cases on the host.

Gate: source-built experimental chain stages and restore tooling pass host checks. No
persistent modification has occurred.

Status: met. The Kaeru stage, the Koboreru image, and the restore tooling pass their host
checkers. Every patch site and every preloader function address is derived from the 2019
donor; three values with no donor literal (`PAYLOAD_ADDR`, `BDEV_ADDR`, `DRAM_BUF`) come
from the reference kit's proven image for that donor. Evidence:
`experiments/phase-02/koboreru/addresses.md`. This is not a hardware claim; Phase 3
verifies behaviour on the unit.

### Phase 3: Boot chain and fastboot

- [x] I approved the same-byte restore drill, the stock reboot, and the subsequent
      development-chain installation separately. Further separate approvals covered the
      reference-chain install, the persistence retest, and the fastboot execution test.
- [x] Preserve the stock backups taken in Phase 1. Verified against `SHA256SUMS` on 2026-11-14.
- [x] Prepare the drill and install manifests and chain-stage sources on the host, so each
      hardware session is one approved `apply`. `experiments/phase-03/notes.md` holds the
      source hashes, addresses, and commands; both manifests plan correctly without a device.
- [x] Before changing stored bytes, write each saved stock boot-chain image back to its
      unmodified source partition. Verify every readback, then reboot and confirm stock boot.
      This drills the restore path while expdb contains no Kaeru LK stage. Done 2026-11-14:
      every readback matched and the stock device booted normally. Evidence:
      `experiments/phase-03/notes.md`, Session 1.
- [x] Install the experimental Kaeru/Koboreru chain using the temporary mtkclient or custom
      scripts. Write expdb, then tee1, then BOOT0 area 1 from the 2019 preloader, with sector 0
      last. Never write BOOT1 (area 2). The full-4-MiB fallback needs separate approval.
      Done 2026-11-14 in that order; BOOT1 was never written in any session.
- [x] Decide the first hardware session's chain-image set: source-built stages, or the kit's
      hardware-proven stages for a reference-only bring-up under separate approval.
      I decided on 2026-11-14: the source-built chain's normal boot failed inconclusively
      (see the limitation below), so the first persisted chain is the kit's hardware-proven
      reference bring-up, written reference-only and under separate approval.
- [x] Verify fastboot `product`, `unlock_status`, and the Kaeru version from the live
      device. Done 2026-11-15: `product: LIDAR`, `unlock_status: true`,
      `kaeru v2.0.0-g8d24a1a-dirty`. Transcript:
      `experiments/phase-03/logs/fastboot-execution-20261115.txt`.
- [x] Verify repeated BROM and fastboot entry and fastboot readback. Done across 2026-11-14
      and 2026-11-15, including a post-power-cycle readback and the persistence retest
      (`experiments/phase-03/logs/persistence-retest-20261115/`).
- [x] Do not overwrite expdb after Kaeru installation. Confirmed: expdb never lost its Kaeru
      LK stage after the first install. Later writes replaced it with another Kaeru LK stage
      under separate approval, and no stock-expdb restore, erasure, or `FASTBOOT_PLEASE`
      write happened afterward.

Gate: the pre-install restore drill and stock boot passed, and the development chain provides
the expected fastboot interface. No LibreEcho boot or system write happens until both hold.

Gate status, 2026-11-15: normal boot on the unit looked normal, and Kaeru fastboot on
this custom boot chain is hardware-proven on the device. No LibreEcho kernel or system
boot has been attempted or achieved.

Limitation, 2026-11-15: the source-built Kaeru/Koboreru chain is not hardware-proven. Its
earlier normal-boot failure is inconclusive: it preceded the discovery of the eMMC
clean-shutdown/persistence issue (`experiments/phase-03/notes.md`, "Post-power-cycle
readback"), so the failed boot attempts may not have executed persisted bytes at all. This
limitation stands until a source-built chain is installed with a clean DA shutdown, power
removed disconnect-first, and booted to fastboot. Production source-built stage validation
remains necessary in Phase 7.

### Phase 4: LibreEcho-Linux kernel and DTB

Status: complete, 2026-11-17. The gate passed (see "Gate passed"). Device state at the
gate: `boot_a` holds `boot-lidar-lk-slot-source.img` (`7284abc5`) with `lidar.autoreboot=240`;
`boot_b` is untouched. The kernel `experiment/*` branches and both stashes are kept,
because the notes cite them.

- [x] Add an ARM64 Lidar target and defconfig with `CONFIG_COMPAT`.
- [x] Derive the production Lidar DTS from the stock DTB identified in Phase 1.
- [x] Reuse upstream MT8516/MT8167 drivers where they apply.
- [x] Bring up in this order: eMMC, USB, clocks, PMIC/regulators, console/pstore.
      I decided on 2026-11-17 that the board has no PMIC. Stock leaves `pwrap` disabled with no
      child in all 19 stock DTBs; the CPU rail is a Richtek RT5738 buck on i2c1 at `0x57`, and
      every other rail is fixed. The DTS describes this layout. Evidence:
      `experiments/phase-04/hw-20261117-k1-lk-slot-initrd/acm-memory-check.log`.
- [x] Add buttons, LEDs, Wi-Fi, and audio in later focused steps.
      Scope I set on 2026-11-17: the DTS and defconfig describe them and hardware
      proves each one probes. The MT7668 WLAN driver and the MT8167 AFE and machine driver are
      Phase 6 work, because 6.1 has neither. Done 2026-11-17; details:
      `experiments/phase-04/notes.md`, "Hardware runs".
- [x] Add an ARM64 CI lane.
- [x] Mirror the stock MTK boot wrapper, load addresses, 16 MiB envelope, and DTB
      selection from Phase 1 evidence.
- [x] Prefer fastboot boot or one-slot experiments where the device supports them. Kaeru
      rejects `fastboot boot`, so every test used the single slot `boot_a`, with each flash
      approved and read back. Details: `experiments/phase-04/notes.md`.
- [x] USB clean control: save the current uncommitted probe/PHY patches as a patch file under
      `experiments/phase-04/`, then restore upstream 6.1 USB code, drop the board `&usb0`
      compatible override, and remove all LibreEcho WDT-reset/status probe hooks from the
      bring-up image. Done 2026-11-17:
      `experiments/phase-04/pre-clean-control/full-worktree.patch`; the control runs on branch
      `experiment/lidar-usb-upstream-glue` (`a251a739`, not for merge).
- [x] Kernel cmdline: add `clk_ignore_unused` as a documented bring-up workaround. Remove it
      once every consumer is described. Keep the `bootopt=64S3,32N2,64N2` prefix.
      Done 2026-11-17 at pack time.
- [x] Defconfig (`arch/arm64/configs/mt8167_arm64_defconfig`): drop `CONFIG_MUSB_PIO_ONLY`,
      enable `CONFIG_USB_INVENTRA_DMA`, the three ACM/NCM/PSTORE config groups,
      `CONFIG_PANIC_TIMEOUT=10`, `CONFIG_INET` and `CONFIG_IPV6`. Done in `92af22e3`.
- [x] DT: end the memory node at `0x7f9c0000` (TEE carve-out), move ramoops to
      `0x43810000` size `0x60000`, add `pmu` disabled and delete `cpu-idle-states` as
      preventive hardening. Done in `92af22e3`; confirmed in the decompiled DTB and in the
      live memory node after the LK slot boot.
- [x] Test initramfs built by us (not Alpine): ARM32 userspace to keep exercising
      `CONFIG_COMPAT`; configfs gadget with acm and ncm functions, getty on ttyGS0,
      link-local address on usb0. I moved SSH out of Phase 4 on 2026-11-17.
- [x] `pack_boot.py` guards: enforce the `bootopt` prefix, cap each appended DTB at 0x80000
      bytes, and check the first root compatible is `amzn,lidar-*`. Done 2026-11-17;
      `python3 -m unittest experiments/phase-04/test_pack_boot.py` 39 OK.
- [x] Hardware sequence with the first combined image: each flash and reboot separately
      approved, true disconnect-first power cycle between steps. The first combined image
      (`2e5b4584`) never booted under LK; its successor `3b5d3d93` passed the gate captures
      from `boot_a`.

Gate, replaced 2026-11-17: a development kernel boots from a single slot, and you reach
a root shell over USB CDC ACM (or SSH over USB NCM). Capture `uname -a`, `/proc/cmdline`,
`dmesg` and `/proc/cpuinfo` through that shell, and a pstore console readback after a warm
reboot. (Previous wording, until 2026-11-17: "a development kernel boots from fastboot or a
single slot. Capture boot evidence through available USB, ADB, pstore, or persistent logs.")

I decided on 2026-11-17 that the gate passes only after the fix is in source and a rebuilt
image boots again from `boot_a` with the same captures. The source changes are the initrd
properties in `pack_boot.py` and the Lidar DTS change (uart0 disabled, ramoops moved).

Gate passed, 2026-11-17: `boot-lidar-lk-slot-source.img` (`7284abc5`, from
`experiment/lidar-lk-slot-source` `79d8d10e`) was flashed to `boot_a` (readback verified) and
cold-booted through the stock LK. Over the USB ACM root shell it gave `uname -a`,
`/proc/cmdline`, `/proc/cpuinfo`, `dmesg`, the regulator and clock summaries, and a pstore
readback of a marker after a warm reboot. Details: `experiments/phase-04/notes.md`, "Gate run
with the source-built image".

Course change, 2026-11-17 (binding decisions; full comparison in
`experiments/phase-04/lidar-mainline-comparison.md`):

- ADB is dropped as the Phase 4 verification route. The debug channel is a USB CDC ACM
  serial root shell, a USB NCM network link with SSH as a development-only service, and
  pstore/ramoops console readback after a warm reboot. Passwordless telnet is rejected.
- Phase 4 stays on Linux 6.1.178. The later move to 6.18 is my Phase 6 decision.
- Nothing from the reference project is built, flashed, or run. Only facts and settings are
  adopted; Phase 6 records my decision that allows copying particular GPL-2.0 code.
- UART correction: UART0 TX is test point TM58 at 1.8 V, 921600 8N1, output only; UART0 RX is
  on no known test point. The UART stays optional.

Handoff to Phase 5:

- Device: `boot_a` holds `boot-lidar-peripherals-3.img` (`2e387bbe`), the last Phase 4
  image; its cmdline carries `lidar.autoreboot=240`; `boot_b` is untouched. Phase 5 replaces
  it.
- Chain: stock BROM entry works with the Action button held; Kaeru provides fastboot; a
  normal boot from `boot_a` gives a root shell over USB CDC ACM. expdb carries the Kaeru LK
  stage, so the boot-chain safety rule still binds.
- Source: `repos/LibreEcho-Linux` `feature/lidar-support` carries the gate tree plus the
  peripheral fixes `2066d8c0` and `7594c578`. The gate image was built from
  `experiment/lidar-lk-slot-source` `79d8d10e`.
- Tooling: `experiments/phase-04/pack_boot.py` implements the proven 16 MiB envelope, the
  `bootopt` prefix, the appended-DTB cap, the root-compatible check and the initrd properties.
  Phase 5's image builders reproduce them.

### Phase 5: LibreEcho-Platform and recovery

Status: complete, 2026-11-21. The gate passed (see "Gate passed").

Device state at the gate, 2026-11-21: `boot_a` holds `boot-lidar-v1.img` (sha256
`9da8886ca63696c5dc13f968f356f499732c072b1dec5d991df8d025737a239a`, read back in step 7)
and `boot_b` holds `boot-lidar-v2.img` (sha256
`7e73d1b800cfa46aee50abe6cf580f8e5927d8777801c3a2fcb0339d48f8c4b0`). The BCB selects
slot b with `slot_a_success=1` and `slot_b_success=1`
(`experiments/phase-05/hw-20261118/step7-reinstall/bcb-before-reboot.out`), and the running
generation is `txn-508529626fbd711fdbf6bf1c`
(`experiments/phase-05/hw-20261118/step7-reinstall/after-state.log`).

Known limits carried out of Phase 5: the assistant and wake word stay off until the Phase 6
audio work, because the audio-profile gate keeps them off without
`/etc/libreecho/audio-profile`; after a confirmed update `libreecho-update status` still shows
the stale `restart_record=1` (`reason=ota-health-confirm-failed`) and
`ota_transaction_state=rollback` alongside the correct `state=installed`; and
`/run/libreecho/wifi-worker-failed` was seen after step 7 and is not investigated.

Boot shape, decided on 2026-11-17 after the comparison with lidar-mainline `4eac822`
(`experiments/phase-05/boot-shape-decision.md`): the product path is Platform-native. Each
LibreEcho image is one 16 MiB boot image in `boot_a` or `boot_b`, and its initramfs carries
the whole ARM32 userspace. The stock LK chooses the slot through the Amazon BCB at `misc`
0x360, which `libreecho-bootctl` already writes. The second-stage U-Boot (`repos/u-boot`
`dffcf3d8`) stays a development tool: it is flashed only during development, to RAM-boot
candidate images and read logs. It gets no flash, erase or environment support and is not part
of any product image.

- [x] Add a `tools/mt8167-arm64/` profile in LibreEcho-Platform. Done: profile exists with the
      Lidar target table; the ARM32 runtime is imported from `tools/mt8163-arm32/`
      (`experiments/phase-05/README.md`, "Profile").
- [x] Adapt image builders and verifiers to the proven stock ARM64 boot envelope. Done: the
      ARM64 builder and verifier reproduce `pack_boot.py` and pass the Lidar verifier on all
      three images (`experiments/phase-05/components.md`, "Images").
- [x] Measure the size budget: ARM64 Image.gz, DTB and the xz initramfs must fit 16 MiB.
      Record the margin. Done: 5,761,024 bytes left in 16 MiB
      (`experiments/phase-05/README.md`, "Size budget").
- [x] Verify GPT slot numbers, userdata size, misc BCB behavior, boot control, recovery,
      and update behavior from live evidence. Done: true A/B with LK tries fallback from B to
      A and `androidboot.slot_suffix` for both slots; `misc[0:32]` is inert and
      reboot-to-fastboot goes through the watchdog bit (`experiments/phase-05/README.md`,
      "Boot control").
- [x] Keep `CONFIG_LIBREECHO_DEV_RECOVERY_MARKER` out of the Lidar kernel. Done: no
      `LIBREECHO_*` symbol in the defconfig and the Lidar builder refuses it.
- [x] Design install and recovery without TWRP. Done: host formats userdata with a sparse
      `LIBREECHO_DATA` image over Kaeru fastboot (`experiments/phase-05/README.md`, "Install
      and recovery").
- [x] Never write `system_a` or `system_b`. Done: the installer flashes only `boot_a`,
      `boot_b` and `userdata` (`hw-20261118/step2-install/`,
      `hw-20261118/step7-reinstall/install.out`).
- [x] Build a development recovery and installation image. Done: dev image
      `boot-lidar-dev.img` plus `lidar_install.py` with check, install and bcb commands
      (`experiments/phase-05/components.md`, "Images").
- [x] Test boot, recovery, reinstall, and OTA transitions on the device. Done: steps 1 to 7
      recorded, step 6 PASS on run 7 and step 7 PASS
      (`experiments/phase-05/README.md`, "Hardware test procedure").

Revisit the boot shape only if the image does not fit 16 MiB or LK's BCB cannot give a safe
fallback. The alternative then is the reference layout: U-Boot in a boot slot, the OS on
`system_a`/`system_b` through extlinux, and U-Boot bootcount.

Gate: the Platform image installs, boots, recovers, and updates on the device.

Gate passed, 2026-11-21. The image installed over Kaeru fastboot (step 2), booted from slot A
with the root shell and `slot_a_success=1` (step 3), and fell back from slot B to slot A when
the development image never confirmed, proving true A/B with LK tries (step 4). Reboot to
fastboot from the running system landed in Kaeru fastboot as the recovery floor (step 5). The
OTA v1 to v2 update installed, booted and confirmed on run 7 (step 6, PASS in
`experiments/phase-05/README.md`). A reinstall from the recovery floor without a userdata
write kept `/data` intact (step 7, PASS; `experiments/phase-05/hw-20261118/step7-reinstall/`).

### Phase 6: hardware and core feature bring-up

The Phase 6 reference inventory (verified on hardware by the reference project, not by me) is
in `experiments/phase-04/lidar-mainline-comparison.md`: audio AFE/machine/TLV320 codecs and
7 mics, IS31FL3236 ring LEDs, gpio buttons, privacy latch GPIO18 and KEY_MICMUTE GPIO108,
TSL2540 light sensor, RT5738/RT5739 vproc cpufreq, MT7668 SDIO Wi-Fi/BT, EFR32 on ttyS2, and
a musb isochronous PIO fix for UAC2.

Decisions I made on 2026-11-21 (these supersede the "facts only" limits above for this project):

1. Code from `reference/lidar-mainline` (the GPL-2.0 kernel overlay and the GPL-2.0 OR
   BSD-3-Clause MT7668 Wi-Fi port of Amazon's gen4 drop) may be copied, ported or changed
   into the port's repositories. Each copied file keeps its license header and gets a provenance note
   naming the reference commit. Proprietary firmware and Fire OS blobs still stay local.
2. The Lidar kernel moves from 6.1.178 to the 6.18 LTS (projected EOL Dec 2028). Reference
   drivers are backported from 7.3. The MT8163 boards stay on 6.1 for now. The move reruns the
   Phase 4 and 5 kernel-dependent checks on the device: boot from a slot, the USB ACM shell,
   pstore, A/B fallback, reboot to fastboot and an OTA.
3. Phase 6 hardware writes and reboots are approved as a class: `boot_a`, `boot_b`,
   `userdata`, the `misc` BCB, reads of `system_a`, and reboots. BOOT0, BOOT1, expdb, tee1/2,
   lk_a/b and `system_a`/`system_b` are never written. I need to be asked only for the
   physical steps.

- [x] Kernel base: rebase the Lidar work onto 6.18 LTS and pass the rerun above.
      Done 2026-11-21 on `feature/lidar-6.18` `15e16539a61d`: slot boot, ACM shell, pstore,
      reboot to fastboot, A/B fallback and a confirmed v1→v2 OTA all passed on the unit
      (`experiments/phase-06/hw-20261121/README.md`, steps 3 to 9).
- [x] MT7668 WLAN: port the reference's gen4 driver (Amazon's GPL drop) to 6.18. The Wi-Fi
      RAM codes and per-unit calibration come from this unit's FireOS `system_a`, stay local,
      and are never committed or published. The ROM patch is the redistributable
      linux-firmware `mediatek/mt7668pr2h.bin` (sha256 `465ed634…`, with
      `LICENCE.mediatek`), staged for both WLAN and BT. Done 2026-11-21: Wi-Fi on 6.18
      (step 7), networking and BT coexistence (steps 10, 15)
      (`experiments/phase-06/hw-20261121/README.md`).
- [x] Audio: port the reference MT8516 AFE and Lidar machine drivers, with Amazon's
      crossover filters loaded into the DAC biquads. Done 2026-11-21 on
      `feature/lidar-6.18` `d70e787ff949` (step 16). Not checked separately: woofer-only and
      tweeter-only playback.
- [x] Validate networking. Step 10 (`step11-net/`): DHCP, route, DNS, reboot, link flap,
      supplicant restart.
- [x] Validate the UI. Step 10 (`step13-ui/`): setup page, bootstrap, authenticated API.
- [x] Validate audio playback. I heard volume steps, cues and the drained cue tail on the
      product path (steps 16, 20-22; `step21-cue/`, `step22-drain/result.md`).
- [x] Validate microphones. All 7 mics capture (`step17-mics/result.md`, `step19-flash/`).
- [x] Validate the voice assistant (`agentd`) and the wake word (`waked`) end to end, and
      confirm an OTA with both required. Done 2026-11-22: the audio profile ships from
      v0.2.21 and both daemons start in local mode; v0.2.21 to v0.2.24 OTAs confirmed with
      them (`step24-voice/result.md`, `step31-mic/`). The agentd reply needs its online
      provider and is recorded as blocked-internet; I decided on 2026-11-22 not to test it
      in this project. A local turn that stalled without an outcome is recorded upstream.
- [x] Validate buttons and LEDs. Volume, mute and Action keys, ring meter, mute ring, LED test,
      Action cue (`step18-buttons/`, `step19-flash/result.md`).
- [x] Validate the privacy latch. Latched capture is exactly 0 on all lanes, steady red ring
      while latched, capture back on release (`step17-mics/`, `step19-flash/result.md`).
- [x] Validate reboot and recovery entry. Software paths (step 10, `step14-recovery/`) and
      Action held at power-on into Kaeru (`step23-recovery/result.md`).
- [x] Validate updates. Steps 4, 5 and 9 on 6.18, and both Wi-Fi tests below.
- [x] Validate development updates over Wi-Fi, so development no longer needs USB. The path
      is the step-6 OTA procedure with ADB over TCP (port 5555) in place of USB; dev-channel
      images start adbd on TCP, stable images do not. ADB over TCP has no authentication, so
      use it only on a trusted LAN. Test (a): install a newer bundle from the running
      confirmed slot, reboot, confirm, reconnect over Wi-Fi. Test (b): install a bundle whose
      image fails the health confirm, and check that the unit falls back to the previous slot
      and ADB over Wi-Fi comes back. Done 2026-11-21: (a) PASS in run 1 (v0.2.18 on slot B);
      (b) PASS in run 2 (three failed boots on slot A, LK fell back to slot B)
      (`experiments/phase-06/wifi-dev-updates/README.md`).
- [x] Add LibreEcho-UI work only if the existing device-independent code cannot handle
      Lidar hardware. Needed and done on `repos/LibreEcho-UI` `fix/lidar-speaker-path`
      (`abe8d9111c`, local): speaker route, IS31FL3236 LED backend, mute-key handling, all
      four ADC PGAs, cue level.
- [x] Zigbee and Thread on the EFR32 radio (decided 2026-11-21). Done 2026-11-21 on
      hardware with lab tooling staged in `/run`
      (`experiments/phase-06/hw-20261121/step25-efr32/result.md`): the Gecko bootloader
      answers; the OpenThread RCP installed through it answers Spinel and a host `ot-cli`
      formed a network as leader; the stock Zigbee NCP answered EZSP and formed a network as
      coordinator. Firmware stays local. I decided on 2026-11-21 that the permanent Thread
      service moves to Phase 7.
- [x] Check every LibreEcho feature on Lidar (decided 2026-11-21). Done 2026-11-22
      (`experiments/phase-06/hw-20261121/step29-features/result.md`). My PASS: Bluetooth
      pairing, A2DP, AVRCP and volume (`step26-bt/owner-a2dp.md`); Home Assistant voice
      commands and a timer (`step29-features/ha-result.md`). Silent PASS: timers and alarms,
      night mode, sleep light, idle, wake word settings, diagnostics, updates, privacy state,
      mDNS, Sendspin. Blocked-internet: radio, news, NTP. N/A: USB storage, Spotify,
      GPT-Live.

Gate: every item above passes on real hardware, kept separate from host tests.

Gate passed, 2026-11-22: the feature sweep and my checks above ran on hardware, ending
with OTA v0.2.24 confirmed on slot a and my wake and Home Assistant timer retest
(`experiments/phase-06/hw-20261121/README.md`, steps 29-31).

### Phase 7: product integration and production tooling

- [x] Rebase every repository onto its current upstream main (LibreEcho 0.14.6 at the
      time; the base branches are recorded in `integration.json`) and split
      our commits into the Phase 8 branches: general fixes on their own branch from upstream
      main, Lidar work stacked on top. Drop debug-only commits; turn experiment branches into
      `archive/...` tags. Done 2026-11-22 for Platform, UI and the kernel; done 2026-11-23 for
      `LibreEcho` (fast-forwarded from the product start commit, tagged
      `archive/product-0.14.5`, to
      upstream `main` `bc167529`) and `LibreEcho-Installer-Web` (already at upstream `main`
      `c7cac7c`).
- [x] Create the `libreecho-lidar-port` docs repository and publish it under my
      GitHub account. Done 2026-11-23: the workspace root is that repository. The export
      scrubs identifiers and a pre-commit hook blocks `private/` paths and scanner hits.
- [x] Delete superseded build outputs under `private/artifacts/` only after I confirm the
      list. Keep current build inputs, the installed image and OTA, the lab key and every
      stock backup. Done 2026-11-22: I approved.
- [x] Add `release/targets/lidar.json` with `soc` `mt8167`, `arch` `arm64`, and
      `hardware_accepted` `false`. Done 2026-11-23 in `LibreEcho` `feature/lidar-support`
      `257404952` (local): userspace stays `armv7`, `layout_profiles` `kaeru`, with the
      defconfig and DTB named in the descriptor and `tools/lab-build.json`.
      `validate-targets.py --targets lidar` passes
      (`lab-notes/phase-07/target-generalization.md`).
- [ ] Generalize the target schema, registries, build, release, and OTA validators instead
      of skipping them. Code done 2026-11-24 in `LibreEcho` `feature/lidar-support` (local):
      `eefd5989` generalizes schema, registry, OTA v2/v3, manifest, release and signing tools
      from the descriptor; stable releases refuse a target without `hardware_accepted`;
      Radar and Biscuit outputs are unchanged. `737cb90` adds a pinned aarch64 cross and an
      MT8167 branch for the MT8163-only `build.sh` checks. A local kernel build with the
      pinned toolchain gave `Image` `1d81b03f…` and `libreecho-lidar.dtb` `a8e19573…`
      (`lab-notes/phase-07/arm64-ci-toolchain.md`). Open until a hosted run: the workflow
      has not executed, `build-release.yml` accepts dispatch only from `main` or `release/*`,
      and the sources are pinned to upstream. I decided on 2026-11-24 that hosted CI waits
      until after the branch cleanup. Kernel cache finding (2026-11-24): one run builds a
      single kernel and uses it for every target. Fixed 2026-11-26 in `LibreEcho`
      `be15ef05` (local): `validate-targets.py` refuses a target set whose arch, defconfig or
      DTB differ and names the differing fields; `docs/porting/README.md` shows a valid set.
      `build.tests.test_multi_target` 29 tests pass.
- [x] Extend the existing installer identity, payload pin, geometry, state, and readback
      gates for Lidar. Done 2026-11-24 (local). CLI: `LibreEcho` `7f0d5c6`; web:
      `LibreEcho-Installer-Web` `3e189f57`. Both read
      `lab-notes/phase-07/installer-lidar-contract.json`: product `LIDAR`, an "already
      converted" pin rule, userdata 9647071 sectors, `boot_a`/`boot_b` readback, arm64 v3 OTA
      plan. Tests pass, mocked device responses only; no hardware run. A web install cannot
      finish yet: no Lidar recovery route, no `lidar-v*` tag, and no release producer emits
      the empty Amonet record.
- [ ] Preserve the installer's current backup behavior and userdata-only format.
      Partly done 2026-11-24 (local). Both installers keep the userdata-only format and take
      no backups; tests show the Lidar path writes only `userdata`, `boot_a` and `boot_b`.
      The Lidar backup set is defined as data with a size and sha256 verifier and has no
      device I/O (Platform `55941f9d0`, `tools/mt8167-arm64/lidar_backup_set.py`;
      `lab-notes/phase-07/lidar-backup-set.md`). The preparation command that reads these
      areas from the device now exists: `lidar_prepare.py` `backup` reads every backup-set
      area twice and verifies the second read (Platform `83e9caae7`;
      `lab-notes/phase-07/prep-command.md`). Not run on hardware yet.
- [ ] Never write expdb after Kaeru installation. Partly done 2026-11-24 (local). Both
      installers read `expdb[0:16]` with Kaeru's `fetch:expdb:0:16` and refuse every flash
      write unless it starts with the MTK magic `88 16 88 58` (rule: Platform
      `AGENTS.md`, "Boot-chain safety" rule 2). Platform `82958b7320` and `LibreEcho`
      `9631fee` + `ca80410`; tests
      pass. The expdb guard is now hardware-read: on 2026-11-26 the live unit's `expdb[0:16]`
      read as `88 16 88 58 …` and `check_expdb_prefix` returned `kaeru-v2`
      (`lab-notes/phase-07/hw-2026-11-26/08-expdb-magic.log`,
      `09-expdb-guard-verdict.log`), and `lidar_prepare.py` `install` calls
      `check_expdb_prefix` before its boot0/LK writes (Platform `83e9caae7`). Open: the
      guard's refuse path has not fired on hardware (`lab-notes/phase-07/expdb-guard.md`).
- [ ] Replace the experimental mtkclient and reference steps with reviewed production
      scripts that use licensed components and source-built chain stages. In progress.
      Platform `83e9caae7` added `tools/mt8167-arm64/prepare/lidar_prepare.py`; Platform
      `c10b2b455` then removed the mtkclient device path, so the command reaches a unit only
      through Amonet (`--amonet <checkout>` names the checkout). The preloader comes from the
      verified backup's boot0 and must match the reviewed 2019 digest; Kaeru and Koboreru are
      source-built inputs with pinned digests. The command refuses without a verified backup
      and drill report, never writes BOOT1, and checks expdb before the tee1 and boot0 writes.
      Host tests pass. On 2026-11-26 `identify` and `backup` ran only as `--dry-run`
      (`lab-notes/phase-07/hw-2026-11-26/notes.md`, "Check 3"); BROM identify, backup and
      drill still need a hardware run, and each stage needs separate approval
      (`lab-notes/phase-07/prep-command.md`).
- [ ] Lidar Thread service (decided 2026-11-21, moved from Phase 6): upload the RCP
      through the EFR32 bootloader when needed and run a host Thread stack on `ttyS2`. The
      RCP GBL links Silicon Labs code under the MSLA (`gsdk/License.txt:1-12`), so it stays a
      local-only payload. Choose Thread or Zigbee per unit. Host side done 2026-11-24
      (Platform `ca8c09f18`, `3617d6650`, `02ef8ad6a`, `40bf6f0b69`; UI `81aaae3`,
      `947841ea9`; Product `73508b6`; Linux `47feddd6`); on-device run deferred by me
      until a second unit arrives (`lab-notes/phase-07/thread-service.md`).
- [ ] Generate any proprietary donor-derived artifact locally from my dump; never
      distribute it. Host side done 2026-11-24: Platform `f9ac5cd9ab` builds the preloader
      and tee1 stages from a verified backup into ignored local paths, and
      `capture_stock_gbls.py` copies stock Zigbee GBLs into `local-firmware/`. Product
      `f449b3f339` + `8e0d52f43c` refuse generator-manifest digests and MTK/`EMMC_BOOT`
      headers. Synthetic fixtures only (`lab-notes/phase-07/donor-generator.md`).
- [x] Keep Lidar out of the normal web installer until hardware acceptance. Done 2026-11-24
      in `LibreEcho-Installer-Web` `5b6477e` (local). Each profile carries
      `hardwareAccepted` (Lidar `false`); an unaccepted board is not listed or offered and is
      refused if forced. `node --test` 397 pass, 2 skipped; the browser check shows only
      Radar and Biscuit (`lab-notes/phase-07/web-acceptance-gate.md`).
- [ ] Make the port buildable from a fresh clone (decided 2026-11-26). The
      product fork's own build (`build.sh --target lidar` plus its OTA pipeline) is the
      one Lidar build; `tools/lab-build.py` shrinks to integrate, product build and deploy.
      The workspace splits what is not committed by why: `work/` (gitignored, regenerable:
      fork clones, integration worktrees, fetched inputs, caches, build output) and
      `private/` (gitignored, not published: raw lab notes, dumps, stock backups, signing key,
      scrub map, reference archives, device address). `tools/workspace.py init` clones the
      forks from URLs in `integration.json` and fetches every public build input by URL and
      sha256; components the lab built once get build recipes in the owning fork; the
      signing key comes from a `keygen` command. Gate: `init` and `build` succeed from a
      clean clone with only the private inputs supplied (host or CI evidence only).

Open items (2026-11-26):

- Lab OTA build and deploy history from v0.2.38 onward: see the phase record in
  [`lab-notes/phase-07/`](../lab-notes/phase-07/) and the device checks in
  [`lab-notes/phase-07/hw-2026-11-26/`](../lab-notes/phase-07/hw-2026-11-26/).
- Announce bug (pink LED, then no audio): fixed on the host. The 0.14.6 branch replaced
  `dechunk()` with the `unframe()` state machine, and the remaining defect (chunk
  extensions were rejected) is fixed in UI `0cc5507` with regression tests
  (`tests/test_esphomed_http.c`). Device check pending
  (`lab-notes/phase-07/announce-bug/notes.md`, "On-device check (UNVERIFIED)").
- Hosted CI is blocked on me: Actions is not enabled on my forks
  (`gh api repos/TomGrozev/LibreEcho/actions/workflows` returns `total_count: 0`), and the
  `gh` identity has no write access to them. The dispatch plan and the reauth detail are in
  `lab-notes/phase-07/hosted-ci.md`.
- I decided on 2026-11-24 that hardware checks for the Phase 7 scripts wait for a second
  unit. The remaining unchecked items are host-complete and stay open only for their device
  runs and the hosted CI run.
- On 2026-11-24 I decided: one topic per change, topics on current upstream, a rebuilt
  integration branch, and no `private/lab/...` citations in fork code.

Decisions, 2026-11-23:

- The gate's step 4 means the product installer `tools/libreecho-install.py` (and the web
  installer) extended for Lidar; Platform's `lidar_install.py` stays as the device-side tool
  underneath.
- "Source-built chain stages" means Kaeru and Koboreru built from source, with the stock
  signed preloader taken from my own dump. This needs a hardware proof of the
  source-built Kaeru and Koboreru (install, power-cycle, readback), each step approved.
- Rebase the product repo `LibreEcho` and `LibreEcho-Installer-Web` onto 0.14.6 before
  the schema, validator and installer work.

Desired final user flow (target design, not current behavior):

1. Prepare the USB connection.
2. Hold the action button and apply power to enter BROM.
3. Run the reviewed Lidar preparation command. It takes the backups, performs the pre-install
   restore drill and stock-boot check, installs the custom boot chain, and confirms fastboot.
4. Run the normal LibreEcho installer (`tools/libreecho-install.py`) with `--target lidar`.
5. Validate and confirm the installation.

No manual offsets, no eMMC short, and no reference ZIP step appear in this path. The manual
`gpt_backup` offset and the reference-ZIP chain binaries are still part of today's install.

Gate: the documented one-command path works end to end on the device with
`hardware_accepted` still `false`.

### Phase 8: validation and PR preparation

- [ ] Run each owning repository's focused and required checks. Product CI includes
      `python -m unittest tools.test_release_tools` and the release-gate workflow's
      documented steps. Target descriptors validate with
      `python3 build/ci/validate-targets.py --targets lidar`.
- [x] Run the prose gate on docs.
- [x] Record the exact tested commit for each repository; each PR body records the tested
      tree, which the re-author pass preserves.
- [ ] Complete real-hardware acceptance for the full checklist below.
- [ ] After my approval, open the PR stack below (decided 2026-11-22). A
      general-fix PR exists only so those fixes reach MT8163 units without waiting for
      Lidar, and wake-word model support gets its own PRs (decided 2026-11-24);
      otherwise each repository gets one PR. Branch heads and merge order are in
      [integration.json](../integration.json).

      | Repository | Branch → base | Merged first |
      | --- | --- | --- |
      | LibreEcho-Linux | `fix/general-fixes-from-lidar-port` → maintainer's `feature/linux-6.18`: the 6.18 general fixes (serial, musb, ASoC, cfg80211, ambient light) | maintainer's 6.18 branch |
      | LibreEcho-Linux | `feature/lidar-support` → Linux general fixes: DTS, drivers with provenance notes, defconfig, `lidar` target row | Linux general fixes |
      | LibreEcho-UI | `fix/general-fixes-from-lidar-port` → `main` | none |
      | LibreEcho-UI | `fix/config-import` → `main`: keep the integrations running after a configuration restore | none |
      | LibreEcho-UI | `feat/wake-word-selection` → `main` | none |
      | LibreEcho-UI | `feature/lidar-support` → UI general fixes | UI general fixes |
      | LibreEcho-Platform | `fix/general-fixes-from-lidar-port` → `main` | none |
      | LibreEcho-Platform | `feat/wake-layernorm-ops` → `main` | none |
      | LibreEcho-Platform | `feature/lidar-support` → Platform general fixes | Platform general fixes, Linux and UI Lidar PRs |
      | LibreEcho | `feat/wakeword-convert` → `main` | Platform wake-ops PR |
      | LibreEcho | `feature/lidar-support` → `main`: `lidar.json`, schema and validator generalization | Platform Lidar PR |
      | LibreEcho-Installer-Web | `feature/lidar-support` → `main` | Product PR and hardware acceptance |
- [ ] Give each PR evidence that distinguishes host, CI, image, and hardware tests.

**Status (2026-11-25).** The 12 product branches in the rewrite manifest have PR bodies
drafted; the fork re-author and push tooling now lives in the maintainer's private
workspace (`private/tools/reauth.py`, `private/tools/push.py`), not this repository. The last
dry run passed for all branches. I must still re-author with my signing key, push, and open
the PRs; nothing is pushed. The Linux branches now include two further `usb: musb` fixes, and
the rebased `feature/lidar-support` builds an ARM64 `Image` and DTB. The Platform AirPlay
end-contract regression is fixed and re-run PASS; the remaining Platform arm32/image/install
failures are missing host tools (`busybox`, `fakeroot`, `dtc`) and also occur on `main`.
The UI targeted tests pass; the unchanged watchdog contract test still hangs locally. CI has
not run on any PR and hardware acceptance is open, so the gate stays open.

Gate: I have approved the working result and authorized each PR. Every published PR has
green CI on its exact head. Nothing is pushed, merged, released, or run on hardware without
separate approval.

## Final acceptance checklist

- [ ] Installation from BROM through the documented one-command path.
- [ ] Boot-chain backups of BOOT0, tee1, expdb, and GPT with a passing pre-install restore drill.
- [ ] Recovery and reinstall.
- [ ] OTA updates.
- [ ] Networking.
- [ ] UI.
- [ ] Audio playback.
- [ ] Microphones.
- [ ] Buttons and LEDs, including the privacy latch.
- [ ] All evidence separated into host, CI, image, and hardware categories.
- [ ] No proprietary donor images, serials, keys, or personal data in any commit or asset.
- [ ] Production scripts use licensed components with complete source.

## Open questions (evidence-gated)

These are tasks for the phases that own them, not questions to ask me now.

- BOOT0 version and whether the stock build can host the chain (Phase 1/2).
- Preloader compatibility and RPMB state (Phase 1/2).
- Kaeru and Koboreru offsets for this board (Phase 2).
- Userdata geometry after install (Phase 5).
- BCB and boot-control behavior on this chain (Phase 5).
- Audio hardware path and codec identity (Phase 6).
- Kernel base for Phase 6: I decided on 2026-11-21 to use the 6.18 LTS.
- Whether an ARM32 SSH daemon is available for the USB NCM development link (Phase 5).
  LibreEcho-Platform ships a pinned ARM32 dropbear bundle (`tools/mt8163-arm32/ssh/`); it is
  not yet tested under `CONFIG_COMPAT` on this unit.
- Copying reference driver code: allowed by my decision of 2026-11-21 (Phase 6, "My
  decisions").
