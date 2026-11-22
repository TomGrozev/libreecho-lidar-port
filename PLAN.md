# Lidar support (Echo Plus 2nd Gen): implementation plan

> Status (2026-11-22): Phases 0-6 complete, Phase 7 in progress, Phase 8 not started.
> Current phase state and gate outcomes: see [README.md](README.md), "Status".

LibreEcho keeps Echo hardware that people already own useful, repairable and private. The
current release supports two MT8163 ARM32 models, `radar_puffin` and `biscuit`. This plan
covers the third, the Echo Plus 2nd Gen (`Lidar`, MediaTek MT8167), and records the
implementation scope agreed for issue #101. No Lidar support is claimed today. Every build,
flash, and release step below is a future task, gated on explicit approval and evidence.

## Accepted scope and decisions

The goal is a Lidar build with the same owner-facing result as the shipping models: a
repairable, private assistant on hardware the owner already has. The issue-#101 scope below
is how that gets built.

- The deliverable of the current session is this plan, not code. A later fresh session
  executes it phase by phase.
- Use the workspace layout and session instructions in `README.md`. Run commands from the
  workspace root unless a phase names another directory.
- Initial experiments use the owner's existing mtkclient setup and temporary local scripts.
  They are personal experimental tools. Production scripts replace them only after boot-chain
  installation and LibreEcho installation work is proven on the device.
- Work happens iteratively in local experimental branches across the required forks. PRs are
  prepared only after the user is satisfied with working results. No push, PR, merge,
  release, or hardware action is authorized by this plan.
- Support stays experimental and fails closed until exact live-device evidence exists.
- Start with read-only BROM/fastboot inspection. Each hardware write or reboot phase needs a
  separate user approval before it runs.
- The development Echo Plus 2nd Gen is sacrificial. USB data is available. UART is not
  required; the stock UART line (ttyS0 921600 8N1) is recorded for reference only.
- Match current installer behavior: no full stock backup and no stock-system restore feature.
  Current installation verifies identity and layout, writes the boot-chain payload and boot
  slots, formats only userdata, and verifies readback.
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
| lidar-mainline (`reference/lidar-mainline`) | GPL-2.0, per-file | Reference for facts and settings only; do not build, run, or copy code. Code copying needs an explicit owner decision because AGENTS.md forbids copying from `reference/` |

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
  18 V and must be insulated. The requester did not confirm D+/D- individually; if a board
  does not enumerate, swapping the two data wires is safe.
- The existing dump lacks BOOT0, BOOT1, lk_b, boot_b, system_a, and system_b. It contains
  stock lk_a, boot_a, tee1/tee2, GPT, and other listed partitions.
- Stock tee1 SHA-256 is
  `aa2b92914cf3dc8dcfebc958b99d752cb98bb20a79bf48570639587c838ad75e`. The reference tee1
  differs. Reference expdb is empty in the owner's stock dump.
- Current product schema accepts only `mt8163`/`arm32` and the `radar_puffin` and `biscuit`
  targets. Full support needs changes in LibreEcho-Linux, LibreEcho-Platform, LibreEcho, and
  LibreEcho-Installer-Web. LibreEcho-UI may need changes for device hardware.
- The current installer makes no partition backups. It verifies identity and layout, writes
  the boot-chain payload and boot_a/boot_b, formats userdata, verifies readback, and never
  writes expdb on a v2 Kaeru chain.

## Boot-chain safety

After Kaeru is installed, expdb holds the Kaeru LK stage (MTK magic
`88 16 88 58` at offset 0). The fastboot marker lives in `misc[0:16]`, not expdb. Never
erase expdb and never write `FASTBOOT_PLEASE` there on a v2 chain. Use Kaeru's own reboot
flow and preserve expdb. This rule binds every phase below.

The live restore drill runs before Kaeru installation, while expdb still has its stock contents.
After Kaeru installation, this plan does not authorize a stock expdb restore. Any later stock
recovery needs a separately reviewed full-chain BROM procedure. Never restore expdb alone.

## Repository ownership

| Repository | Responsibility |
| --- | --- |
| LibreEcho-Linux | ARM64 Lidar target, defconfig with `CONFIG_COMPAT`, DTS/DTB, drivers, CI lane |
| LibreEcho-Platform | mt8167-arm64 tools profile, image builders/verifiers, recovery, installer runtime, OTA |
| LibreEcho | Target descriptor `release/targets/lidar.json`, schema generalization, release/OTA validators, documentation |
| LibreEcho-Installer-Web | Lidar target in the hosted installer once hardware is accepted |
| LibreEcho-UI (optional) | Only if existing device-independent code cannot handle Lidar hardware |
| Kaeru fork | Lidar config/board port on upstream AGPL source, kept in the owner's GitHub fork; no upstream PR planned |
| Koboreru fork | Lidar device definition on upstream MIT source, kept in the owner's GitHub fork; no upstream PR planned |
| u-boot fork | Lidar fastboot stage, kept in the owner's GitHub fork; no upstream PR planned |
| `libreecho-lidar-port` (public, owner's GitHub account) | This plan, port documentation, experiment notes and scripts; no code that belongs in the repositories above |

Repository structure (owner decision, 2026-11-22): the boot-chain forks are referenced by
commit from the production scripts. Everything else lands as the PR stack in Phase 8.

## Safety and evidence rules

1. The original stock dump is immutable. Work on copies.
2. Sensitive data (donor images, serials, keys, personal data) stays local and never enters
   a commit, PR, or release asset.
3. Record exact hashes and commit IDs for every image and source tree used.
4. Read-only operations come first. Each write or reboot phase waits for separate user
   approval.
5. No hardware claim from a host test. Host, CI, image, and hardware evidence stay
   distinct.
6. No push or PR without user approval of the working results.

## Phases

Each phase ends at a gate. Do not start the next phase until the gate holds.

### Phase 0: experimental workspace

- [x] Confirm the workspace layout in `README.md` and create `experiments/phase-00/`.
- [x] Confirm the product start commit `4f5445934679d68863fc0c723b990326fc9ff3d1` and a
      clean worktree in `repos/LibreEcho/`.
- [x] Record the current main heads of each owning repository.
- [x] Clone required repositories under `repos/` and create `feature/lidar-support` branches
      locally from the verified heads. Do not require GitHub forks before local work starts.
- [x] Clone or fork external repositories only when the user authorizes it.
- [x] Record host dependencies in `experiments/phase-00/`: Python version, mtkclient commit,
      tools, and their versions.
- [x] Keep experiment inputs and logs under `experiments/`, device reads under `dumps/`, and
      locally built outputs under `artifacts/`. Keep them outside release assets.

Gate: the workspace matches `README.md`; required branches exist locally with recorded base
commits; no fork or push has happened.

### Phase 1: live read-only boot-chain inventory

- [x] Create `experiments/phase-01/` and a new device-read directory under `dumps/`.
- [x] Use the owner's existing mtkclient commands that already produced the stock dump.
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

Gate: no offsets are treated as final and no write plan is drafted until BOOT0 and the
stock LK and TEE are known from live reads.

### Phase 2: experimental boot-chain construction and restore tooling

- [x] Start from upstream Kaeru source. Derive a new Lidar config/board from the stock
      lk_a. Do not copy reference repository source or binaries.
- [x] Start from MIT Koboreru source. Derive a new Lidar device definition from the 2019
      replacement preloader, per the preloader route decision. All device addresses and the
      four patch sites are donor-derived and agree with the reference kit's proven chain
      for the same donor; evidence is in `experiments/phase-02/koboreru/addresses.md`.
- [x] Extract proprietary donors locally for analysis. Never commit them.
- [x] If stock BOOT0 cannot host the chain, record the donor/preloader decision as a
      blocker. Do not silently download a replacement.
- [x] Build restore tooling before modifying anything: exact identity, size, and hash gates;
      readback verification after each write; atomic local manifests.
- [x] When BOOT0 changes, write BOOT0 sector 0 last.
- [x] Exercise restore tooling against synthetic images and fault cases on the host.

Gate: source-built experimental chain stages and restore tooling pass host checks. No
persistent modification has occurred. Status: met. The Kaeru stage, the Koboreru image, and the
restore tooling pass their host checkers. Every patch site and every preloader function
address is derived from the 2019 donor; three values with no donor literal (`PAYLOAD_ADDR`,
`BDEV_ADDR`, `DRAM_BUF`) come from the reference kit's proven image for that donor, as
`experiments/phase-02/koboreru/addresses.md` records. This
is not a hardware claim; Phase 3 verifies behaviour on the unit.

### Phase 3: owner access and fastboot

- [x] Get specific user approval for the same-byte restore drill, stock reboot, and subsequent
      development-chain installation. Further separate approvals covered the reference-chain
      install, the persistence retest, and the fastboot execution test.
- [x] Preserve the stock backups taken in Phase 1. Verified against `SHA256SUMS` on 2026-11-14.
- [x] Prepare the drill and install manifests and chain-stage sources on the host, so each
      hardware session is one approved `apply`. `experiments/phase-03/notes.md` holds the source
      hashes, addresses, and commands; both manifests plan correctly without a device.
- [x] Before changing stored bytes, write each saved stock boot-chain image back to its
      unmodified source partition. Verify every readback, then reboot and confirm stock boot.
      This drills the restore path while expdb contains no Kaeru LK stage.
      Done 2026-11-14: the same-byte drill passed with every readback matching, and the stock
      device booted normally afterwards. Evidence: `experiments/phase-03/notes.md`, Session 1.
- [x] Install the experimental Kaeru/Koboreru chain using the temporary mtkclient or custom
      scripts. Write expdb, then tee1, then BOOT0 area 1 from the 2019 preloader, with sector 0
      last. Never write BOOT1 (area 2). The full-4-MiB fallback needs separate approval.
      Done: the source-built chain was written in this order (2026-11-14), and the full-4-MiB
      fallback path was separately approved and used for the reference-chain install, including
      a clean DA shutdown and disconnect-first power removal. BOOT1 was never written in any
      session. Evidence: `experiments/phase-03/logs/` and the notes' persistence retest.
- [x] Decide the first hardware session's chain-image set: source-built stages, or the kit's
      hardware-proven stages for a reference-only bring-up under separate approval.
      Decided 2026-11-14: the source-built chain's normal boot failed inconclusively (see the
      limitation below), so the first persisted chain is the kit's hardware-proven reference
      bring-up, written reference-only and under separate approval.
- [x] Verify fastboot `product`, `unlock_status`, and the Kaeru version from the live
      device. Done 2026-11-15 on the persisted reference chain: `product: LIDAR`,
      `unlock_status: true`, `kaeru v2.0.0-g8d24a1a-dirty`. Transcript:
      `experiments/phase-03/logs/fastboot-execution-20261115.txt`.
- [x] Verify repeated BROM and fastboot entry and fastboot readback. Done: repeated BROM entry
      and readback are verified across 2026-11-14 and 2026-11-15 sessions, including the
      post-power-cycle readback and the persistence retest that proved all three reference
      images survived a true power cycle (`logs/persistence-retest-20261115/`).
- [x] Do not overwrite expdb after Kaeru installation. Post-install stock recovery is not
      authorized without the separately reviewed procedure described above. Confirmed: expdb
      never lost its Kaeru LK stage after the first install. Later writes replaced it with
      another Kaeru LK stage (the reference chain) under separate approval, and no stock-expdb
      restore, erasure, or `FASTBOOT_PLEASE` write happened afterward.

Gate: the pre-install restore drill and stock boot passed, and the development chain provides
the expected fastboot interface. No LibreEcho boot or system write happens until both hold.

Gate status, 2026-11-15: normal boot on the unit looked normal, and Kaeru fastboot on
this owner-access chain is hardware-proven on the device. No LibreEcho kernel or system
boot has been attempted or achieved.

Limitation, 2026-11-15: the source-built Kaeru/Koboreru chain is not hardware-proven. Its
earlier normal-boot failure is inconclusive: it preceded the discovery of the eMMC
clean-shutdown/persistence issue (`experiments/phase-03/notes.md`, "Post-power-cycle
readback"), so the failed boot attempts may not have executed persisted bytes at all. This
limitation stands until a source-built chain is installed with a clean DA shutdown, power
removed disconnect-first, and booted to fastboot. Production source-built stage validation
remains necessary in Phase 7.

### Phase 4: LibreEcho-Linux kernel and DTB

Status: complete, 2026-11-17. Every item below is checked, and the gate passed (see "Gate
passed"). Cleanup before Phase 5: all seven repos are clean. Kaeru `0cbe64d` (fastboot fetch
and peek), amonet-koboreru `5642513` (proven preloader patch sites) and u-boot `dffcf3d8`
(stage-2 fastboot candidate, untested on hardware) are local commits; nothing was pushed.
The kernel `experiment/*` branches and both stashes are kept, because the notes cite them.
Device state: `boot_a` holds the Phase 4 image `boot-lidar-peripherals-3.img` with
`lidar.autoreboot=240`, so it reboots every 4 minutes under the test initramfs. Phase 5
replaces that image; it is not a recovery fallback.

- [x] Add an ARM64 Lidar target and defconfig with `CONFIG_COMPAT`.
- [x] Derive the production Lidar DTS from the stock DTB identified in Phase 1.
- [x] Reuse upstream MT8516/MT8167 drivers where they apply.
- [x] Bring up in this order: eMMC, USB, clocks, PMIC/regulators, console/pstore.
      Owner decision, 2026-11-17: the board has no PMIC. Stock leaves `pwrap` disabled with no
      child in all 19 stock DTBs; the CPU rail is a Richtek RT5738 buck on i2c1 at `0x57`, and
      every other rail is fixed. Phase 4 describes this layout in the DTS (RT5738 node, fixed
      rails, `pwrap` disabled, no MT6357 placeholder). eMMC (`mmc0` HS200, 7.13 GiB), USB and
      console/pstore work under the LK slot boot (`acm-bringup-evidence.log`). The RT5738
      driver, CPU frequency scaling and a boot without `clk_ignore_unused` move to the later
      focused steps.
- [x] Add buttons, LEDs, Wi-Fi, and audio in later focused steps.
      Scope, owner decision 2026-11-17: Phase 4 describes these in the DTS and defconfig and
      proves on hardware that each one probes. Buttons report input events, and the LED ring
      lights through `/sys/class/leds`. The MT7668 enumerates as an SDIO card on MSDC2. The
      TLV320AIC32x4 DAC and the four TLV320ADC3101 ADCs probe on I2C. A missing Bluetooth
      firmware file and the absence of an ALSA card are expected at this step. The MT7668 WLAN
      driver and the MT8167 AFE and machine driver are Phase 6 work, because 6.1 has neither.
      Done 2026-11-17: image `boot-lidar-peripherals-3.img` (`2e387bbe`) on `boot_a` shows all
      of the above on hardware. Details: `experiments/phase-04/notes.md`, "Hardware runs".
- [x] Add an ARM64 CI lane.
- [x] Mirror the stock MTK boot wrapper, load addresses, 16 MiB envelope, and DTB
      selection from Phase 1 evidence.
- [x] Prefer fastboot boot or one-slot experiments where the device supports them. Get
      approval before any flash write. Status, 2026-11-15: the base b2e01e image was
      flashed to `boot_a` under separate approval, and after the reboot no USB or ADB
      interface appeared within a 90-second wait. A separate diagnostic image
      (`artifacts/phase-04/superseded/boot-lidar-diagnostic-adb.img`, sha256 `244622b1...`) was
      then built, verified, owner-approved, and flashed to `boot_a`; fastboot
      `flash` and `reboot` both returned `OKAY` with the same zero-size AVB footer
      warning. `adb wait-for-device` again timed out after 90 seconds with no output
      and no kernel or property evidence. This rules out the stock legacy `android0`
      USB setup as the whole explanation, but not every userspace problem; an early
      kernel fault is a hypothesis, not proven. No further image flashes without new
      evidence. Next decisive diagnostic, 2026-11-15: a 3.3 V UART console. Correction,
      2026-11-17: that diagnostic is superseded. UART0 TX is the test point TM58 at 1.8 V,
      921600 8N1, output only, and UART0 RX is on no known test point (reference README
      test-point table; not verified on our unit), so a 3.3 V adapter would use the wrong
      level. The UART stays optional. Status, 2026-11-17: the ADB route is superseded; see the
      course-change block below. Details: `experiments/phase-04/notes.md`.
      Done 2026-11-17: Kaeru rejects `fastboot boot`, so every test used the single slot
      `boot_a`, with each flash approved and read back. The gate passed this way.
- [x] USB clean control: save the current uncommitted probe/PHY patches as a patch file under
      `experiments/phase-04/`, then restore upstream 6.1 USB code (`drivers/usb/musb/mediatek.c`,
      `musb_core.c`, `musb_gadget.c`, `drivers/phy/mediatek/phy-mtk-tphy.c`,
      `drivers/usb/gadget/function/f_fs.c`), drop the board `&usb0` compatible override
      `mediatek,mt8167-usb20` in favor of the inherited `mt8516.dtsi` nodes, and remove all
      LibreEcho WDT-reset/status probe hooks from the bring-up image. The reference runs on
      stock upstream USB code identical to what 6.1 has; that control has never been run on
      our board.
      Done 2026-11-17: `experiments/phase-04/pre-clean-control/full-worktree.patch`; the
      branch base already carried MT8163 glue in `mediatek.c`/`musb_gadget.c`/`f_fs.c`
      (commit `d2cb959e`), so the control runs on branch `experiment/lidar-usb-upstream-glue`
      (`a251a739`, those files equal to v6.1.178; not for merge).
- [x] Kernel cmdline: add `clk_ignore_unused` as a documented bring-up workaround (the kernel
      gates clocks no DT node claims after late init, after the pullup; matches our symptom).
      Remove it once every consumer is described. Keep the `bootopt=64S3,32N2,64N2` prefix.
      Done 2026-11-17 at pack time (`--cmdline-append clk_ignore_unused`).
- [x] Defconfig (`arch/arm64/configs/mt8167_arm64_defconfig`): drop `CONFIG_MUSB_PIO_ONLY`,
      enable `CONFIG_USB_INVENTRA_DMA`, `CONFIG_USB_CONFIGFS_ACM`, `CONFIG_USB_CONFIGFS_NCM`,
      `CONFIG_PSTORE_RAM`, `CONFIG_PSTORE_CONSOLE`, `CONFIG_PSTORE_PMSG`, and
      `CONFIG_PANIC_TIMEOUT=10`. ADB/RNDIS symbols are no longer needed for the gate.
      Done 2026-11-17 (`feature/lidar-support` `92af22e3`; also `CONFIG_INET`/`IPV6`).
- [x] DT: end the memory node at 0x7f9c0000 (TEE carve-out) after checking LK's memory fixup on
      our chain; move ramoops out of LK's boot-image load window to a region nothing in our
      chain loads into (the reference uses 0x60000000 size 0x100000, record 0x20000,
      console 0x80000, pmsg 0x20000; validate against our LK load addresses); add `pmu`
      disabled and delete `cpu-idle-states` (and later proc-supply) as preventive hardening.
      Status 2026-11-17: DT changes are in `92af22e3` and confirmed in the decompiled DTB.
      Done 2026-11-17: after the LK slot boot, the live memory node is `0x40000000` size
      `0x3f9c0000` (ends at `0x7f9c0000`), and ramoops works at `0x43810000` size `0x60000`
      (the reference's `0x60000000` is outside what Kaeru `fetch` reads). LK adds its own
      `secmon@43000000` with the same range as our `atf@43000000`; the kernel logs
      `OVERLAP DETECTED`, which is harmless. The owner chose to keep our `atf` node. Evidence:
      `experiments/phase-04/hw-20261117-k1-lk-slot-initrd/acm-memory-check.log`.
- [x] Test initramfs built by us (not Alpine): ARM32 userspace to keep exercising
      `CONFIG_COMPAT`; configfs gadget with acm and ncm functions, UDC bound after the
      functions are linked, getty on ttyGS0, link-local address on usb0, and an SSH daemon
      with an owner key as a development-only service.
      Status 2026-11-17: built (`artifacts/phase-04/initramfs/`, ramdisk `7b4a7c85...`, ACM
      shell, NCM with 169.254.42.1/16). No SSH daemon yet; the ACM shell alone meets the
      gate. Done 2026-11-17 by owner decision: SSH moves out of Phase 4 and returns when a
      later phase needs a network shell.
- [x] `pack_boot.py` guards: enforce the `bootopt` prefix, cap each appended DTB at 0x80000
      bytes (LK copies the selected DTB to 0x4e000000), and check the first root compatible is
      `amzn,lidar-*`. Do not adopt a BL31-overlap rejection: our 0x850000 kernel crosses
      0x43000000 and still completed every initcall.
      Done 2026-11-17; `python3 -m unittest experiments/phase-04/test_pack_boot.py` 39 OK.
      First combined image: `artifacts/phase-04/superseded/boot-lidar-usb-acm-clean-control.img`,
      sha256 `2e5b4584...`, pack verify OK; host evidence only.
- [x] Hardware sequence with the first combined image (a through e above): each flash and
      reboot separately approved, true disconnect-first power cycle between steps. If the host
      still sees no connect, capture clock and PHY state (`clk_summary`, TOPCKGEN, PHY
      registers) through pstore after a warm reboot.
      Done 2026-11-17 by owner decision: the first combined image (`2e5b4584`) never booted
      under LK because of two faults (no initrd from LK, uart0 idle stall). Its successor
      `3b5d3d93` carries steps a to e plus both fixes and passed the gate captures from
      `boot_a`, with each flash and reboot approved and a power cycle between steps.

Gate, replaced 2026-11-17: a development kernel boots from a single slot, and the owner reaches
a root shell over USB CDC ACM (or SSH over USB NCM). Capture `uname -a`, `/proc/cmdline`,
`dmesg` and `/proc/cpuinfo` through that shell, and a pstore console readback after a warm
reboot. (Previous wording, until 2026-11-17: "a development kernel boots from fastboot or a
single slot. Capture boot evidence through available USB, ADB, pstore, or persistent logs.")

Status, 2026-11-17: the evidence the gate lists now exists for a boot from `boot_a` through
the stock LK (`3b5d3d93`, readback verified): root shell over USB ACM, `uname -a`,
`/proc/cmdline`, `dmesg`, `/proc/cpuinfo`, and a pstore console readback of a marker after a
warm reboot (read from Kaeru, and again from `/sys/fs/pstore` inside Linux). The DTB disables
uart0 and adds the `/chosen` initrd properties, because LK passes no initrd on a normal boot.
The gate awaits owner review. Earlier, the same checks passed under a U-Boot RAM boot
(`77bcf0f3`). Details: `experiments/phase-04/notes.md`,
"LK slot boot diagnosis and ACM shell from boot_a".

Owner decision, 2026-11-17: the gate passes only after the fix is in source and a rebuilt
image boots again from `boot_a` with the same captures. In source means two changes:
`pack_boot.py` writes `linux,initrd-start` and `linux,initrd-end` from the boot image header,
and the Lidar DTS on `feature/lidar-support` disables uart0 and moves ramoops to `0x43810000`.
A bound on the `8250_mtk.c` idle wait is deferred, so uart0 stays disabled. The power domain
`MFG_ASYNC` fails with `-110` on every boot path; this is a known issue for the later display
and GPU work, not a Phase 4 item.

Gate passed, 2026-11-17: the owner's condition is met. The source-built image
`boot-lidar-lk-slot-source.img` (`7284abc5`, from `experiment/lidar-lk-slot-source` `79d8d10e`;
`feature/lidar-support` has the same tree) was flashed to `boot_a` (readback verified) and
cold-booted through the stock LK. Over the USB ACM root shell it gave `uname -a`,
`/proc/cmdline`, `/proc/cpuinfo`, `dmesg`, the regulator and clock summaries, and a pstore
readback of a marker after a warm reboot. Details: `experiments/phase-04/notes.md`, "Gate run
with the source-built image".

Course change, 2026-11-17: the owner compared LibreEcho's Phase 4 with the independent
lidar-mainline project, which boots a mainline kernel on this device. The full comparison and
its evidence table are in `experiments/phase-04/lidar-mainline-comparison.md`; the decisions
below are binding.

- ADB is dropped as the Phase 4 verification route. Our failure is below ADB: the host never
  sees any USB connect at all, so no ADB or g_serial stack can help. The debug channel is now:
  a USB CDC ACM serial root shell (getty on ttyGS0), a USB NCM network link with SSH as a
  development-only service (key auth, bound to the USB interface, never a product default),
  and pstore/ramoops console readback after a warm reboot. Passwordless telnet, as in the
  reference, is rejected for LibreEcho.
- Phase 4 stays on Linux 6.1.178 (`repos/LibreEcho-Linux`, branch `feature/lidar-support`). A
  7.3 rebase is an evidence-gated later option, evaluated when Phase 6 needs Wi-Fi, cpufreq,
  or audio.
- Nothing from the reference project is built, flashed, or run. Only its facts and settings
  (config symbols, DT values, cmdline, boot-image constraints, gadget setup approach) are
  adopted. Reference driver code is license-compatible but AGENTS.md forbids copying from
  `reference/`; any copy in Phase 6 needs an explicit owner decision.
- Adopted Phase 4 work, in order: (a) USB clean control and removal of the WDT probe hooks;
  (b) `clk_ignore_unused` on the cmdline; (c) the defconfig changes listed in the checklist;
  (d) the DT memory, ramoops, pmu and cpu-idle-states changes; (e) our own ARM32 test
  initramfs; (f) `pack_boot.py` guards; (g) the approved flash sequence. Each step is a
  checklist item above, done on 2026-11-17.
- UART correction: the earlier "3.3 V UART console" diagnostic named the wrong level and
  assumed an input path. UART0 TX is test point TM58 at 1.8 V, 921600 8N1, output only;
  UART0 RX is on no known test point (reference README test-point table; not verified on our
  unit). The UART stays optional.

Record, 2026-11-17: the running status journal this section carried during Phase 4 is frozen
in `experiments/phase-04/plan-phase-4-journal.md`. The detailed log with exact commands,
hashes and captures is `experiments/phase-04/notes.md`; `experiments/phase-04/README.md`
indexes the rest of that directory. Research reports: `lidar-mainline-comparison.md` (facts
and settings adopted from the reference project), `lk-kernel-handover-research.md`,
`usb-enumeration-research.md`, `fastboot-boot-research.md`, `no-uart-research.md`. Built
images: `artifacts/phase-04/README.md`.

Handoff to Phase 5:

- Device: `boot_a` holds `boot-lidar-peripherals-3.img` (`2e387bbe...`), the last Phase 4
  image, which probes every peripheral. Its cmdline carries `lidar.autoreboot=240`, so it
  reboots every four minutes under the test initramfs; it is not a recovery fallback. Phase 5
  replaces it. `boot_b` is untouched.
- Chain: stock BROM entry works with the Action button held at power-on, Kaeru provides
  fastboot, and a normal boot from `boot_a` gives a root shell over USB CDC ACM. expdb carries
  the Kaeru LK stage, so the boot-chain safety rule above still binds.
- Source: `repos/LibreEcho-Linux` `feature/lidar-support` carries the gate tree plus the
  peripheral fixes `2066d8c0` and `7594c578`. The gate image was built from
  `experiment/lidar-lk-slot-source` `79d8d10e`.
- Tooling: `experiments/phase-04/pack_boot.py` implements the proven 16 MiB envelope, the
  `bootopt` prefix, the appended-DTB cap, the root-compatible check and the initrd properties.
  Phase 5's image builders must reproduce them rather than re-derive them.
- Unpushed local commits at the phase boundary: Kaeru `0cbe64d`, amonet-koboreru `5642513`,
  u-boot `dffcf3d8` (a stage-2 fastboot candidate, not tested on hardware).

### Phase 5: LibreEcho-Platform and recovery

Status: complete, 2026-11-21. Every item below is checked with its evidence pointer, and the
gate passed (see "Gate passed").

Device state at the phase boundary, 2026-11-21: `boot_a` holds the v1 image
`boot-lidar-v1.img` (sha256 `9da8886ca63696c5dc13f968f356f499732c072b1dec5d991df8d025737a239a`,
read back in step 7) and `boot_b` holds the v2 image `boot-lidar-v2.img` (sha256
`7e73d1b800cfa46aee50abe6cf580f8e5927d8777801c3a2fcb0339d48f8c4b0`). The BCB selects slot b
with `slot_a_success=1` and `slot_b_success=1` (`hw-20261118/step7-reinstall/bcb-before-reboot.out`),
and the running generation is `txn-508529626fbd711fdbf6bf1c`
(`hw-20261118/step7-reinstall/after-state.log`). Source is committed locally, unpushed, on
`feature/lidar-support`: LibreEcho-Platform `620935f41d` and `76608be064` (test pins),
LibreEcho-Linux `eef1f29ab9` (reboot mode, defconfig) and `6046668bd5` (MUSB rx_kick).

Known limits carried out of Phase 5: the assistant and wake word stay off until the Phase 6
audio work, because the audio-profile gate keeps them off without `/etc/libreecho/audio-profile`;
after a confirmed update `libreecho-update status` still shows the stale
`restart_record=1` (`reason=ota-health-confirm-failed`) and `ota_transaction_state=rollback`
alongside the correct `state=installed`; and `/run/libreecho/wifi-worker-failed` was seen
after step 7 and is not investigated.

Boot shape, decided 2026-11-17 after the comparison with lidar-mainline `4eac822`
(`experiments/phase-05/boot-shape-decision.md`): the product path is Platform-native. Each
LibreEcho image is one 16 MiB boot image in `boot_a` or `boot_b`, and its initramfs carries
the whole ARM32 userspace. The stock LK chooses the slot through the Amazon BCB at `misc`
0x360, which `libreecho-bootctl` already writes. On this unit LK fell back from A to B through
that BCB (`experiments/phase-04/notes.md:471-499`) and passes `androidboot.slot_suffix`, which
`libreecho-init` already reads. The second-stage U-Boot (`repos/u-boot` `dffcf3d8`) stays a
development tool: it is flashed only during development, to RAM-boot candidate images and read
logs. It gets no flash, erase or environment support and is not part of any product image.

- [x] Add a `tools/mt8167-arm64/` profile in LibreEcho-Platform. A profile there is a tools
      directory plus a target table (`tools/mt8163-arm32/libreecho_platform_targets.py:31-45`);
      there is no registry to extend. Retain ARM32 userspace under it.
      Done: profile exists with the Lidar target table; the ARM32 runtime is imported from
      `tools/mt8163-arm32/` (`experiments/phase-05/README.md`, "Profile").
- [x] Adapt image builders and verifiers to the proven stock ARM64 boot envelope. Reproduce
      `experiments/phase-04/pack_boot.py`. Fork the ARM32-only kernel rules (zImage, kernel
      address, `bootopt` 32-bit path) and keep the ARM32 ELF rules for userspace.
      Done: the ARM64 builder and verifier reproduce `pack_boot.py` and pass the Lidar
      verifier on all three images (`experiments/phase-05/README.md`, "Profile";
      `experiments/phase-05/components.md`, "Images").
- [x] Measure the size budget: ARM64 Image.gz, DTB and the xz initramfs must fit 16 MiB.
      Record the margin.
      Done: gzip kernel 4,603,904 bytes, DTBs 1,024,374, xz initramfs 5,382,724; 5,761,024
      bytes left in 16 MiB (`experiments/phase-05/README.md`, "Size budget").
- [x] Verify GPT slot numbers, userdata size, misc BCB behavior, boot control, recovery,
      and update behavior from live evidence. Do not reuse MT8163 constants without proof.
      For the BCB, record how LK uses tries and the success bit, whether this chain is true
      A/B or `fixed-a` as on the MT8163 Kaeru chain, `androidboot.slot_suffix` for both
      slots, and Kaeru reboot-to-fastboot through the `misc[0:32]` command.
      Done: the chain is true A/B with LK tries fallback from B to A and
      `androidboot.slot_suffix` for both slots; `misc[0:32]` is inert and reboot-to-fastboot
      goes through the watchdog bit (`experiments/phase-05/README.md`, "Boot control" and
      "Reboot to fastboot"; step 3 to 5 evidence in `experiments/phase-05/hw-20261118/`).
- [x] Keep `CONFIG_LIBREECHO_DEV_RECOVERY_MARKER` out of the Lidar kernel. Its driver
      (`drivers/misc/mediatek/echo_fastboot_marker.c` in LibreEcho-Platform) resets both BCB
      slots to success=0 on every boot, which breaks A/B confirmation.
      `mt8167_arm64_defconfig` does not set it today.
      Done: no `LIBREECHO_*` symbol in the defconfig and the Lidar builder refuses it
      (`experiments/phase-05/notes.md`, "Done on the host"; `experiments/phase-05/README.md`,
      "Kernel").
- [x] Design install and recovery without TWRP. This unit has no `recovery` partition and no
      TWRP. Kaeru fastboot (Action held at power-on) is the recovery floor; it can flash but
      rejects `fastboot boot`. Decide how userdata gets its first format: from the host over
      Kaeru fastboot, or by the LibreEcho image on first boot behind a guarded check.
      Done: host formats userdata with a sparse `LIBREECHO_DATA` image over Kaeru fastboot
      (`experiments/phase-05/README.md`, "Install and recovery").
- [x] Never write `system_a` or `system_b`. `libreecho-vendor-import` and the Phase 6 Wi-Fi
      firmware read Fire OS from `system_a`. A later design that writes a system slot must
      first import that firmware into userdata.
      Done: the installer flashes only `boot_a`, `boot_b` and `userdata` and every install
      output shows only those writes (`experiments/phase-05/README.md`, "Install and
      recovery"; `hw-20261118/step2-install/`, `hw-20261118/step7-reinstall/install.out`).
- [x] Build a development recovery and installation image.
      Done: dev image `boot-lidar-dev.img` plus `lidar_install.py` with check, install and
      bcb commands (`experiments/phase-05/components.md`, "Images";
      `experiments/phase-05/notes.md`, "Done on the host").
- [x] Test boot, recovery, reinstall, and OTA transitions on the device.
      Done: steps 1 to 7 of the hardware procedure all recorded, step 6 PASS on run 7 and
      step 7 PASS (`experiments/phase-05/README.md`, "Hardware test procedure").

Revisit the boot shape only if the image does not fit 16 MiB or LK's BCB cannot give a safe
fallback. The alternative then is the reference layout: U-Boot in a boot slot, the OS on
`system_a`/`system_b` through extlinux, and U-Boot bootcount. Its preconditions are in the
decision record. The U-Boot env offset question there is resolved from source: both readings
name the same bytes at the top of `misc` (`repos/u-boot/env/mmc.c:145-146,172-183`).

Gate: the Platform image installs, boots, recovers, and updates on the device.

Gate passed, 2026-11-21. The image installed over Kaeru fastboot (step 2), booted from slot A
with the root shell and `slot_a_success=1` (step 3), and fell back from slot B to slot A when
the development image never confirmed, proving true A/B with LK tries (step 4). Reboot to
fastboot from the running system landed in Kaeru fastboot as the recovery floor (step 5). The
OTA v1 to v2 update installed, booted and confirmed on run 7 (step 6, PASS in
`experiments/phase-05/README.md`). A reinstall from the recovery floor without a userdata
write kept `/data` intact (step 7, PASS; `experiments/phase-05/hw-20261118/step7-reinstall/`).

### Phase 6: hardware and core feature bring-up

The Phase 6 reference inventory (verified on hardware by the reference project, not by us) is
in `experiments/phase-04/lidar-mainline-comparison.md`: audio AFE/machine/TLV320 codecs and
7 mics, IS31FL3236 ring LEDs, gpio buttons, privacy latch GPIO18 and KEY_MICMUTE GPIO108,
TSL2540 light sensor, RT5738/RT5739 vproc cpufreq, MT7668 SDIO Wi-Fi/BT, EFR32 on ttyS2, and
a musb isochronous PIO fix for UAC2. Since 2026-11-20 the reference also reports Wi-Fi
(2.4/5 GHz) and Bluetooth working together on a second unit (`reference/lidar-mainline`
`b8dba12`) and boots without `clk_ignore_unused` (`db8242a`).

Owner decisions, 2026-11-21 (these supersede the "facts only" limits above and in
`experiments/phase-04/lidar-mainline-comparison.md` for this project):

1. Code from `reference/lidar-mainline` (the GPL-2.0 kernel overlay and the GPL-2.0 OR
   BSD-3-Clause MT7668 Wi-Fi port of Amazon's gen4 drop) may be copied, ported or changed
   into our repositories. Each copied file keeps its license header and gets a provenance note
   naming the reference commit. Proprietary firmware and Fire OS blobs still stay local.
2. The Lidar kernel moves from 6.1.178 to the 6.18 LTS (projected EOL Dec 2028). Reference
   drivers are backported from 7.3. The MT8163 boards stay on 6.1 for now. The move reruns the
   Phase 4 and 5 kernel-dependent checks on the device: boot from a slot, the USB ACM shell,
   pstore, A/B fallback, reboot to fastboot and an OTA.
3. Phase 6 hardware writes and reboots are approved as a class: `boot_a`, `boot_b`,
   `userdata`, the `misc` BCB, reads of `system_a`, and reboots. BOOT0, BOOT1, expdb, tee1/2,
   lk_a/b and `system_a`/`system_b` are never written. The owner is asked only for physical
   steps (listening, speaking, buttons, the privacy switch).

- [x] Kernel base: rebase the Lidar work onto 6.18 LTS and pass the rerun above.
      Done 2026-11-21 on `feature/lidar-6.18` `15e16539a61d`: slot boot, ACM shell, pstore,
      reboot to fastboot, A/B fallback and a confirmed v1→v2 OTA all passed on the unit
      (`experiments/phase-06/hw-20261121/README.md`, steps 3 to 9).
- [x] MT7668 WLAN: no in-tree driver exists. Port the reference's gen4 driver (Amazon's GPL
      drop) to 6.18. The Wi-Fi RAM codes and per-unit calibration come from this unit's FireOS
      `system_a`, are imported at boot, stay local, and are never committed or published. The
      ROM patch is the redistributable linux-firmware `mediatek/mt7668pr2h.bin` (sha256
      `465ed634…`, with `LICENCE.mediatek`), staged in the image for both WLAN and BT, because
      the vendor BT blob crashes mainline `btmtksdio`.
      Done 2026-11-21: Wi-Fi on 6.18 (step 7), networking and BT coexistence (steps 10, 15) in
      `experiments/phase-06/hw-20261121/README.md`.
- [x] Audio: port the reference MT8516 AFE and Lidar machine drivers. Per the reference
      project, the speaker is two-way: the DAC drives the woofer on its left channel and
      the tweeter on its right, with Amazon's crossover filters loaded into the DAC biquads.
      Done 2026-11-21 on `feature/lidar-6.18` `d70e787ff949` (AIC32x4 page-select fix, step 16).
      Not checked separately: woofer-only and tweeter-only playback.
- [x] Validate networking. Step 10 (`step11-net/`): DHCP, route, DNS, reboot, link flap,
      supplicant restart.
- [x] Validate the UI. Step 10 (`step13-ui/`): setup page, bootstrap, authenticated API.
- [x] Validate audio playback. Owner heard volume steps, cues and the drained cue tail on the
      product path (steps 16, 20-22; `step21-cue/`, `step22-drain/result.md`).
- [x] Validate microphones. All 7 mics capture (`step17-mics/result.md`, `step19-flash/`).
- [x] Validate the voice assistant (`agentd`) and the wake word (`waked`) end to end, and
      confirm an OTA with both required. Until Lidar has audio, its images ship no
      `/etc/libreecho/audio-profile`, so neither is started nor required by OTA confirm
      (Phase 5 step 6 decision: agentd needs the audio socket; waked needs micd's calibrated
      stream, which needs a capture PCM). Adding the audio profile in this phase must turn
      both back on; check that it does.
      Done 2026-11-22, with one item blocked by the network. The audio profile ships from
      v0.2.21 on and both daemons start in local mode; v0.2.21 to v0.2.24 OTAs confirmed with
      them (`step24-voice/result.md`, `step31-mic/`). waked: wake detected in local mode and
      used by the Home Assistant satellite, which the owner confirmed works for voice commands
      after the micd PGA fix (UI `371950abb70d`, v0.2.24). sttd transcribes captured speech on
      the device. The agentd reply needs its online provider and is recorded as
      blocked-internet on the LAN-only network; owner decision, 2026-11-22: not tested in this
      project, left to the maintainer. A local turn that stalled without an outcome is a
      general bug, recorded upstream in `step24-voice/result.md`.
- [x] Validate buttons and LEDs. Volume, mute and Action keys, ring meter, mute ring, LED test,
      Action cue (`step18-buttons/`, `step19-flash/result.md`; Action cue heard 2026-11-21).
- [x] Validate the privacy latch. Latched capture is exactly 0 on all lanes, steady red ring
      while latched, capture back on release (`step17-mics/`, `step19-flash/result.md`).
- [x] Validate reboot and recovery entry. Software paths (step 10, `step14-recovery/`) and
      Action held at power-on into Kaeru (`step23-recovery/result.md`: unplug 10 s, hold
      Action 10 s).
- [x] Validate updates. Steps 4, 5 and 9 on 6.18, and both Wi-Fi tests below.
- [x] Validate development updates over Wi-Fi, so development no longer needs USB. The path
      below is the supported way to install a development build over the air; it is the
      step-6 OTA procedure with ADB over TCP in place of USB:
      1. Build the boot image, then a lab-key-signed bundle on the dev channel whose version
         is above the installed one (`experiments/phase-06/ota/build_ota.sh`).
      2. Connect with `adb connect <device-ip>:5555`. Dev-channel images start adbd on TCP
         5555 (`/etc/libreecho/adb-transport`, `libreecho-init:741-754`); stable images do
         not. ADB over TCP has no authentication, so use it only on a trusted LAN.
      3. With every command pinned to `adb -s <device-ip>:5555`: push the generation tree and
         the bundle, run `libreecho-update install`, and reboot into the other slot.
      4. Wait for the terminal confirmed state, using the same check as `ota_step6_618.sh`.
         A failed confirm falls back to the previous slot through LK tries.

      Prerequisite: the host must reach the device on TCP 5555 (met 2026-11-21 by a router rule). Before the rule, it could not:
      the device's Wi-Fi network does not route to the host's network in either direction
      (ping and `adb connect` both fail; the device reaches only its own gateway).
      Test, with USB still connected as a safety net but unused (every command over Wi-Fi):
      (a) install a newer bundle from the running confirmed slot, reboot, confirm, and
      reconnect over Wi-Fi; (b) install a bundle whose image fails the health confirm, and
      check that the unit falls back to the previous slot and ADB over Wi-Fi comes back. Do
      not reflash through fastboot as part of this test. Only after both pass may development
      updates run with USB unplugged. Kaeru fastboot stays the recovery floor, and it still
      needs USB.
      Done 2026-11-21 (`experiments/phase-06/wifi-dev-updates/README.md`). (a) PASS in run 1:
      v0.2.18 confirmed on slot B. (b) PASS in run 2: a v0.2.20 test image whose `web-status`
      health probe always fails rebooted itself three times on slot A, and LK fell back to
      slot B with ADB over Wi-Fi back, after one host reboot. Run 1's first attempt at (b)
      used the development image, which never brings up Wi-Fi, and the owner had to recover
      it with power cycles. Deviation: USB was not connected during either run; the owner
      chose to continue without it.
- [x] Add LibreEcho-UI work only if the existing device-independent code cannot handle
      Lidar hardware.
      Needed and done on `repos/LibreEcho-UI` `fix/lidar-speaker-path` (`abe8d9111c`, local):
      speaker route, IS31FL3236 LED backend, mute-key handling, all four ADC PGAs, cue level.
- [x] Zigbee and Thread on the EFR32 radio (owner decision, 2026-11-21: in this phase, after
      every item above passes). Starting points: the reference's OpenThread RCP firmware and
      GBL packer (`reference/lidar-mainline` `2719003`, `081f527`, `0aa88f0`), its Thread
      border router service (`14cdc63`), and `tools/lidar-efr32.sh` / `tools/lidar-zigbee.sh`.
      The `ttyS2` power-down fix from `314c0d7` is already in our 6.18 kernel. Before first use,
      check the board DTS: it enables `uart-has-rtscts` on `uart2`, but the reference runs the
      EFR32 host UART without flow control. Silicon Labs SDK, tools and built firmware stay
      local and are never committed or published.
      Done 2026-11-21 on hardware with lab tooling staged in `/run`
      (`experiments/phase-06/hw-20261121/step25-efr32/result.md`): the Gecko bootloader
      answers; stock firmware recorded before any write; our OpenThread RCP installed through
      the bootloader answers Spinel and a host `ot-cli` formed a network as leader; the stock
      Zigbee NCP answered EZSP (EmberZNet 6.5.3.0) and formed a network as coordinator. One
      firmware at a time, as in the reference; the chip is left on our RCP. Pairing a real
      device needs the owner and is not done. Owner decision, 2026-11-21: the permanent Thread
      service moves to Phase 7; this phase only makes uart2 appear as `/dev/ttyS2` with GPIO
      chip nodes (kernel `89b7f3f07a51`).
- [x] Check every LibreEcho feature on Lidar (owner decision, 2026-11-21). Hardware-backed
      features first: Bluetooth phone pairing and A2DP, and the Home Assistant ESPHome voice
      satellite (`libreecho-esphomed`, TCP 6053), which is the owner's main voice path. Then
      the rest of the feature list in `repos/LibreEcho-UI/README.md`. A feature that needs the
      internet is recorded as blocked on the LAN-only network, not as failed. A general
      LibreEcho bug found here is recorded upstream, not fixed in the port.
      Done 2026-11-22 (`experiments/phase-06/hw-20261121/step29-features/result.md`). Owner
      PASS: Bluetooth pairing, A2DP, AVRCP and volume (`step26-bt/owner-a2dp.md`); Home
      Assistant voice commands and a timer (`step29-features/ha-result.md`, v0.2.23 and v0.2.24
      reconnect without help). Port fixes: esphomed wlan0 factory-MAC fallback and DTS node
      `amz_privacy` (v0.2.23), micd PGA (v0.2.24). Silent PASS: timers and alarms, night mode,
      sleep light, idle, wake word settings, diagnostics, updates, privacy state, mDNS,
      Sendspin. Blocked-internet: radio, news, NTP. N/A: USB storage (peripheral-only port),
      Spotify (no LibreEcho image ships its daemon), GPT-Live. Owner checked by eye
      2026-11-22: night and sleep lights look right. Upstream notes: btd discoverable and pairing-off order
      (`step26-bt/`).

Gate: every item above passes on real hardware, kept separate from host tests.

Gate passed, 2026-11-22: the feature sweep and owner checks above ran on hardware, ending
with OTA v0.2.24 confirmed on slot a and the owner's wake and Home Assistant timer retest
(`experiments/phase-06/hw-20261121/README.md`, steps 29-31).

### Phase 7: product integration and production tooling

- [ ] Rebase every repository onto its current upstream main (LibreEcho 0.14.6) and split
      our commits into the Phase 8 branches: general fixes that help the MT8163 targets on
      their own branch from upstream main, Lidar work stacked on top. Drop debug-only
      commits; turn experiment branches into `archive/...` tags, as upstream does. Record
      each new base and branch head in `experiments/phase-07/`.
- [ ] Create the `libreecho-lidar-port` docs repository and publish it under the owner's
      GitHub account. Only
      material that passes the "Safety and evidence rules" goes in: no dumps, microphone
      captures, keys, donor or vendor images, `reference/` or mtkclient. Scrub serials,
      MACs, SSIDs and LAN addresses from logs and replace `/home/build/...` paths before the
      first commit. Creating and pushing the GitHub repository needs separate approval.
- [ ] Delete superseded build outputs under `artifacts/` only after the owner confirms the
      list. Keep current build inputs, the installed image and OTA, the lab key and every
      stock backup.
- [ ] Add `release/targets/lidar.json` with `soc` `mt8167`, `arch` `arm64`, and
      `hardware_accepted` `false`.
- [ ] Generalize the target schema, registries, build, release, and OTA validators instead
      of skipping them.
- [ ] Extend the existing installer identity, payload pin, geometry, state, and readback
      gates for Lidar.
- [ ] Preserve the installer's current backup behavior and userdata-only format.
- [ ] Never write expdb after Kaeru installation.
- [ ] Replace the experimental mtkclient and reference steps with reviewed production
      scripts that use licensed components and source-built chain stages.
- [ ] Lidar Thread service (owner decision, 2026-11-21, moved from Phase 6): upload the RCP
      through the EFR32 bootloader when needed and run a host Thread stack on `ttyS2`. Our
      RCP GBL links Silicon Labs code under the MSLA (`gsdk/License.txt:1-12`), so it stays a
      local-only payload and no image or bundle carrying it is published. Choose Thread or
      Zigbee per unit, because the radio runs one firmware at a time.
- [ ] Generate any proprietary donor-derived artifact locally from the owner's dump; never
      distribute it.
- [ ] Keep Lidar out of the normal web installer until hardware acceptance.

Desired final user flow (target design, not current behavior):

1. Prepare the USB connection.
2. Hold the action button and apply power to enter BROM.
3. Run the reviewed Lidar preparation command. It takes the backups, performs the pre-install
   restore drill and stock-boot check, installs the owner-access chain, and confirms fastboot.
4. Run the normal LibreEcho installer with `--target lidar`.
5. Validate and confirm the installation.

No manual offsets, no eMMC short, and no reference ZIP step appear in this path.

Gate: the documented one-command path works end to end on the device with
`hardware_accepted` still `false`.

### Phase 8: validation and PR preparation

- [ ] Run each owning repository's focused and required checks. Product CI includes
      `python -m unittest tools.test_release_tools` and the release-gate workflow's
      documented steps. Target descriptors validate with
      `python3 build/ci/validate-targets.py --targets lidar`.
- [ ] Run the prose gate on docs.
- [ ] Record the exact tested commit for each repository.
- [ ] Complete real-hardware acceptance for the full checklist below.
- [ ] After user approval, open the PR stack below (owner decision, 2026-11-22). A
      general-fix PR exists only so those fixes reach MT8163 owners without waiting for
      Lidar; otherwise each repository gets one PR.

      | Repository | Branch → base | Merged first |
      | --- | --- | --- |
      | LibreEcho-Linux | `feature/lidar-support` → maintainer's `feature/linux-6.18` (his 6.18 port on v6.18.57; owner decision 2026-11-22): DTS, drivers with provenance notes, defconfig, `lidar` target row | maintainer's 6.18 branch |
      | LibreEcho-UI | `fix/general-fixes-from-lidar-port` → `main` | none |
      | LibreEcho-UI | `feature/lidar-support` → UI general fixes | UI general fixes |
      | LibreEcho-Platform | `fix/general-fixes-from-lidar-port` → `main` | none |
      | LibreEcho-Platform | `feature/lidar-support` → Platform general fixes | Platform general fixes, Linux and UI Lidar PRs |
      | LibreEcho | `feature/lidar-support` → `main`: `lidar.json`, schema and validator generalization | Platform Lidar PR |
      | LibreEcho-Installer-Web | `feature/lidar-support` → `main` | Product PR and hardware acceptance |
- [ ] Give each PR evidence that distinguishes host, CI, image, and hardware tests.

Gate: the user has approved the working result and authorized each PR. Every published PR has
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

These are tasks for the phases that own them, not questions to ask the user now.

- BOOT0 version and whether the stock build can host the chain (Phase 1/2).
- Preloader compatibility and RPMB state (Phase 1/2).
- Kaeru and Koboreru offsets for this board (Phase 2).
- Userdata geometry after install (Phase 5).
- BCB and boot-control behavior on this chain (Phase 5).
- Audio hardware path and codec identity (Phase 6).
- Kernel base for Phase 6: decided 2026-11-21, the 6.18 LTS (Phase 6, "Owner decisions").
- Whether an ARM32 SSH daemon is available for the USB NCM development link (Phase 5).
  LibreEcho-Platform ships a pinned ARM32 dropbear bundle (`tools/mt8163-arm32/ssh/`); it is
  not yet tested under `CONFIG_COMPAT` on this unit.
- Copying reference driver code: allowed by the owner, 2026-11-21 (Phase 6, "Owner
  decisions").
