# lidar-mainline comparison record

Date: 2026-11-17. Scope: documentation only. No code was built, nothing was flashed, and
nothing from the reference project was run on hardware for this record.

## Source

- Project: https://github.com/LeagueRaINi/lidar-mainline
- Local clone (read-only): `reference/lidar-mainline`
- Commit: 35f8ba147c663a5d19ce3f95704321dbad6d1255
- License: GPL-2.0 (kernel and tools), GPL-2.0+ / GPL-2.0 OR MIT DTS in `lidar-uboot/`,
  GPL-2.0 OR BSD-3-Clause in `lidar-wifi/` (license table below)
- Linux version: 7.3; U-Boot version: v2026.10

## Scope overlap

Their work starts at our Phase 4 onward: it boots after an existing Kaeru unlock, so it
covers none of our Phases 1-3 (BROM, LK unlock, partition discovery). Their Phase-4
equivalent covers kernel boot, USB, a debug channel and a userspace image. Everything below
describes their tree, not ours.

## Kernel and USB

Both sides run the same stack: MUSB at 0x11100000 (SPI 72), clocks CLK_TOP_USB, USBIF and
USB_1P, and a `phys` phandle into the in-SoC T-PHY at 0x11110000 (port 0x11110800, ref clock
CLK_TOP_USB_PHY48M = univpll/26). Their SoC dtsi USB nodes are the same shape as ours
(`reference/lidar-mainline/lidar-linux/arch/arm64/boot/dts/mediatek/mt8516.dtsi:555-601` vs
`repos/LibreEcho-Linux/arch/arm64/boot/dts/mediatek/mt8516.dtsi:470-519`).

Their USB code is stock mainline. Their only USB kernel patches are two musb_gadget.c UAC2
isochronous fixes (`reference/lidar-mainline/README.md:277-278`); upstream v7.3 T-PHY has no
`mediatek,mt8516-tphy` entry (it falls back to generic-tphy-v1) and set_mode forces IDDIG
only (phy-mtk-tphy.c v7.3:936-943, 1554-1563). Our tree carries a forked MUSB glue
(`repos/LibreEcho-Linux/drivers/usb/musb/mediatek.c:54-72,110-190,600-740,1101-1254,1281-1286`)
and local T-PHY analog writes (SQTH=6, VRT/TERM=7, DP100K, IDDIG/AVALID/VBUSVALID force,
`repos/LibreEcho-Linux/drivers/phy/mediatek/phy-mtk-tphy.c:296-298,515-533,605-630,1236-1241`).
None of these exist upstream in 6.1 or 7.3. Our own PHY-force run was negative
(`experiments/phase-04/notes.md:1452-1471`), so the value of this comparison is a missing
control: nobody has booted our DT with clean upstream 6.1 USB drivers on our board.

Ranked differences (their side verified on their hardware, unverified on our unit):

| # | Difference | Our evidence | Their evidence | Confidence |
|---|---|---|---|---|
| 1 | No `clk_ignore_unused` in our cmdline. Linux gates unclaimed clocks after late init, after the gadget pullup, matching our symptom. | `experiments/phase-04/notes.md:644`; 0 grep hits in notes.md/PLAN.md | `tools/mk-testimg.sh:235`; `README.md:149-151` | Medium (untested on ours) |
| 2 | Our USB driver shape is a local fork; theirs is pristine upstream and works. | `mediatek.c:110-190,600-740`; `phy-mtk-tphy.c:515-533,605-630` | v7.3 phy-mtk-tphy.c:936-943,1554-1563; glue matches only `mediatek,mtk-musb` | High that the fork is not the fix; control missing |
| 3 | Config delta: we have MUSB_PIO_ONLY=y, RNDIS+F_FS only; they have INVENTRA_DMA and CONFIGFS ACM+NCM. | `mt8167_arm64_defconfig:39-48` | `lidar.config:18-26`; `mk-testimg.sh:153-162` | Low for the missing connect; high for reproducing experiments (`notes.md:405-406`) |
| 4 | Kernel base 6.1.178 vs v7.3. No USB-code delta found. | `clk-mt8167.c:66,563,833-883,936` identical entries | v7.3 glue/tphy identical for this SoC | Low for USB; medium for unowned-clock gating |
| 5 | PMU and PSCI idle states left enabled in our DT. Theirs disables pmu and deletes cpu-idle-states. | `libreecho-lidar.dts:218-236` (no override); `mt8516.dtsi:54-56,102-121,167-170` | board dts:69-74, 578-601; `README.md:361-365` | Low as no-connect cause; inert under our full defconfig (`notes.md:79-80`) |
| 6 | Memory node overlap with TEE top of RAM. | `libreecho-lidar.dts:44-46` (to 0x80000000) | board dts:43-46 (ends 0x7f9c0000) | Medium as general risk; [INFERENCE] LK may already fix it up |
| 7 | pstore placement inside LK's boot-image load window. | `libreecho-lidar.dts:97-104`; `notes.md:663-670` (empty captures) | board dts:55-66 (0x60000000); `README.md:186-190` | Info; likely reason our pstore is empty |

Clock fixes: their clk-mtk table-sizing fix (IDs above 174 unreachable,
`README.md:375-379`) belongs to the new mtk_clk_desc framework and affects MSDC2_INFRA; our
6.1 driver allocates by MT8167_CLK_TOP_NR_CLK (`clk-mt8167.c:936`). Their USB clock entries
(clk-mt8516.c:59,386,566-612) are identical in value to ours. Their clock fixes do not
affect USB.

Confounds: our probe kernels carry WDT-reset hooks inside musb_pullup
(`musb_gadget.c:1636-1697`) that never return, killing the gadget 5-10 s after pullup. Any
image with CONFIG_LIBREECHO_MUSB_{BDEVICE,DEVCTL,PULLUP}_STATUS or the pullup-reset option
must not go into non-probe images. Our notes contain no clk_summary, TOPCKGEN or PHY register
readback (0 grep hits), so the 48 MHz PHY ref has never been measured on our side.

Verdict: 6.1.178 is adequate for this SoC's USB; every piece the reference depends on exists
in 6.1. Keep 6.1 for the USB A/B and reproduce their environment (upstream drivers,
`clk_ignore_unused`, configfs gadget) before considering a rebase. A 7.3 rebase becomes
relevant for Wi-Fi, cpufreq and audio, not USB.

## Boot chain and packer

Their chain adds a stage we lack: boot_a holds U-Boot packed as an arm64 LK kernel; U-Boot
re-reads GPT, boots extlinux from system_a/b ext4, and exposes full fastboot with
`oem run` and `oem console` (`reference/lidar-mainline/lidar-uboot/configs/mt8516_amazon_lidar_defconfig:71-73`,
`README.md:303-304`). Our Kaeru LK rejects `fastboot boot`, so each experiment here is a
flash, a bounded WDT reset and a ramoops fetch.

Boot image format comparison:

| Field | Ours | Theirs | Verdict |
|---|---|---|---|
| v0 header / 2048 page | yes, byte-identical (`pack_boot.py:687-724`) | yes (`lidarboot.py:30-33`) | tie |
| MTK KERNEL header 0x58881688 | yes (`pack_boot.py:52-55`) | yes (`lidarboot.py:35-40`) | tie |
| gzip Image + appended DTBs | yes, 19 blobs | yes, any count | tie |
| `bootopt=64S3,32N2,64N2` prefix | inherited from stock cmdline; no check (`test_pack_boot.py:210`) | hard-enforced (`lidarboot.py:105-110`) | theirs: cheap guard |
| DTB per-blob <= 0x80000 | no check | hard-enforced (`lidarboot.py:86-95`) | theirs: real LK limit |
| DTB first root compatible | index-4 PVT hash only (`pack_boot.py:706-718`) | `amzn,lidar-*` check (`lidarboot.py:89-95`) | theirs, more general |
| Ramdisk | stock ARM32 gzip required (`pack_boot.py:724-734`) | optional, empty cpio default (`lidarboot.py:38-46`) | ours stricter |
| Envelope | fixed 16 MiB, zero-filled (`pack_boot.py:37,809`) | page-padded, 16 MiB max (`lidarboot.py:187`) | ours mirrors partition |
| BL31 overlap | no check; our kernel violates their rule and boots | hard reject if kernel end > 0x43000000 (`lidarboot.py:66-72`) | ours: their check is over-strict |

BL31 overlap: our proven kernel reports image_size=0x850000, spanning 0x40080000-0x48850000,
straight through BL31 at 0x43000000, and still completes every initcall level 0-7 and execs
/init (`PLAN.md:640-790`). Their tool would refuse to pack it. "Image plus BSS must end below
0x43000000" (`README.md:97`) holds only for their small U-Boot payload. [INFERENCE] BL31 runs
from its ATF-resident copy; our `atf@43000000` no-map reservation
(`libreecho-lidar.dts:46-51`) overlapping the kernel image is nonetheless inconsistent and
should be reconciled.

Env offset contradiction (their side): `mt8516_amazon_lidar_defconfig:10,18` sets
ENV_OFFSET=0x1970000 and ENV_OFFSET_REDUND=0x1960000 (absolute device addresses), while
`README.md:311-318` and `mk-testimg.sh:38-42` document partition-relative 0x70000/0x60000.
misc is 0x80000 bytes at 0x1900000
(`experiments/phase-01/brom-printgpt.log:132`), so a relative reading of 0x1970000 would be
an out-of-partition saveenv. One of the two is wrong. [INFERENCE] the defconfig values are
stale absolute offsets and the README values are what actually ran on their board. Resolve
against U-Boot v2026.10 env/mmc.c before any adoption.

Their A/B env in misc upper half does not collide with our misc[0:16]/BCB rule
(`PLAN.md:112`) under the README reading. Their fastboot exposes every named GPT partition
(`README.md:298-301`), so `PLAN.md:111-114` (never write expdb) would need an explicit
deny-list, not prose.

## Verification channel

| | Ours | Theirs |
|---|---|---|
| Interactive evidence | none; 8-30 s WDT timing classes + ramoops fetch (`notes.md:-260`) | USB ACM root shell, NCM 169.254.7.2, telnet on usb0, pstore on warm reboot (`README.md:174-196`) |
| Cost per iteration | flash + reboot + timed reset + fetch + decode | one shell command |
| Dependency | only LK + kernel (works today) | kernel-side MUSB gadget must enumerate, our open failure |

Their channel is better per experiment but sits downstream of our blocker. Two pieces are
adoptable without our USB: the ramoops-on-warm-reboot convention, and `oem console`-style
readback (needs their U-Boot). Their U-Boot fastboot USB works on this exact board, which is
strong independent evidence that our failure is in our MUSB/PHY path, not the cable or host.

## Userspace

| | Ours | Theirs |
|---|---|---|
| Rootfs | LibreEcho ARM32 userspace, ARM64 kernel via CONFIG_COMPAT (`PLAN.md:38,102-107`; `mt8167_arm64_defconfig:12`) | Alpine aarch64 minirootfs, busybox init, ext4 on system_a/b (`mk-testimg.sh`) |
| Install/update/recovery | Phase 5 target (`PLAN.md:952-961`) | none; flashing a slot erases it |
| Product fit | matches existing LibreEcho images and A/B model | bring-up substrate only |

Their extlinux-on-ext4 A/B layout is structurally close to our Phase 5 A/B ext4 slots and is
a reference for that phase. Their aarch64 Alpine rootfs does not exercise CONFIG_COMPAT and
is not a product fit. Our CONFIG_COMPAT is validated as far as ARM32 /init exec
(`PLAN.md:780-790`).

## Feature coverage

| Area | Ours | Theirs | Better |
|---|---|---|---|
| eMMC | yes | yes + MSDC2 clock fixes | theirs (fixes) |
| USB | gadget registers but never enumerates | ACM+NCM working; MUSB iso/DATAERROR fixes | theirs |
| console/pstore | ramoops 0x43810000 via custom fetch | ramoops 0x60000000, plain warm reboot | theirs |
| audio/mics | out of scope (`libreecho-lidar.dts:11-12`) | AFE+machine+TLV320 codecs, 7 mics, UAC2 (`lidar.config:38-44`) | theirs |
| LEDs/buttons | absent | IS31FL3236 multicolor fix, GPIO buttons, privacy switch | theirs |
| cpufreq | absent | RT5738/RT5739 vproc, 598 MHz-1.3 GHz | theirs |
| Wi-Fi/BT | absent | MT7668 out-of-tree + clk-mtk/MSDC2/reset fixes | theirs (code), unknown (HW) |
| pmu/idle | no pmu node, no cpu-idle-states in our mt8167.dtsi | pmu disabled + idle-states deleted as workarounds | both moot for us |

All feature rows describe their hardware verification, not ours.

## Licensing and reuse limits

| Their path | License | Reusable in LibreEcho? |
|---|---|---|
| `lidar-linux/` | GPL-2.0-only kernel code | yes, into LibreEcho-Linux with attribution; `PLAN.md:40-54` forbids only the donor ZIP/binaries, AGPL Kaeru binary and proprietary firmware |
| `lidar-uboot/` | GPL-2.0+ / GPL-2.0 OR MIT DTS | yes, same |
| `lidar-wifi/` | GPL-2.0 OR BSD-3-Clause | yes, most permissive |
| `tools/` | GPL-2.0-only | yes, but `lidarboot.py` as-is rejects our kernel (BL31 check above) |
| Alpine test image, Fire OS staging | Alpine packages / owner-local blobs | no blob commit (`PLAN.md:41-42`) |

License compatibility does not settle the copying decision. For Phase 4 we take facts and
settings only (config symbols, DT values, cmdline, boot-image constraints, gadget setup). No
reference code is copied in Phase 4. AGENTS.md "Reference material" forbids copying from
`reference/` into a source repository. Phase 6 copying candidates (MT8516 AFE + Lidar machine
driver, TLV320ADC3xxx changes, IS31FL32xx brightness fix, TSL2540, RT5739, musb isochronous
fix, MT7668 Wi-Fi) are GPL-2.0-compatible with LibreEcho-Linux but need an explicit owner
decision when that phase starts. This is an open question, not a permission.

## Owner decisions and adopted Phase 4 route

The owner decided:

1. ADB is dropped as the Phase 4 verification route. The debug channel becomes a USB CDC ACM
   serial root shell (getty on ttyGS0), a USB NCM link with SSH as a development-only service
   (key auth, bound to the USB interface, never a product default), and pstore/ramoops console
   readback after a warm reboot. Passwordless telnet as in the reference is rejected.
2. Phase 4 stays on Linux 6.1.178 (repos/LibreEcho-Linux, branch feature/lidar-support). A 7.3
   rebase is an evidence-gated later option, evaluated when Phase 6 needs Wi-Fi, cpufreq or
   audio.
3. Nothing is built, flashed or run from the reference project. Its good ideas go into our own
   kernel, packer and plan.
4. Phase 4 adopts facts and settings only; no reference code is copied (see licensing above).

Adopted Phase 4 work, in order (the new route to the gate):

a. USB clean control: save the current uncommitted probe/PHY patches as a patch file under
   `experiments/phase-04/`, then restore upstream 6.1 USB paths (drivers/usb/musb/mediatek.c,
   musb_core.c, musb_gadget.c, drivers/phy/mediatek/phy-mtk-tphy.c, f_fs.c); drop the board
   `&usb0` compatible override `mediatek,mt8167-usb20` and use the inherited mt8516.dtsi
   nodes; remove all LibreEcho WDT-reset/status probe hooks from the bring-up image. Reason:
   the reference works on stock upstream USB code identical to what 6.1 has; nobody has run
   that control on our board.
b. Kernel cmdline: add `clk_ignore_unused` as a documented bring-up workaround, removed once
   every clock consumer is described. Keep the `bootopt=64S3,32N2,64N2` prefix.
c. Defconfig (arch/arm64/configs/mt8167_arm64_defconfig): drop CONFIG_MUSB_PIO_ONLY, enable
   CONFIG_USB_INVENTRA_DMA, CONFIG_USB_CONFIGFS_ACM, CONFIG_USB_CONFIGFS_NCM, PSTORE_RAM,
   PSTORE_CONSOLE, PSTORE_PMSG, PANIC_TIMEOUT=10. ADB/RNDIS symbols are no longer needed for
   the gate.
d. DT: end the memory node at 0x7f9c0000 after checking LK's memory fixup on our chain; move
   ramoops out of LK's boot-image load window (0x60000000 size 0x100000, record 0x20000,
   console 0x80000, pmsg 0x20000, the reference's choice, to validate against our LK load
   addresses); add `pmu` disabled and delete `cpu-idle-states` (+ later proc-supply) as
   preventive hardening. These are inert under the current full defconfig but required before
   any build with CONFIG_CPU_IDLE or an arm64-defconfig base.
e. Test initramfs built by us (not Alpine): ARM32 userspace to keep exercising CONFIG_COMPAT;
   configfs gadget with acm + ncm functions, bind UDC after functions are linked, getty on
   ttyGS0, link-local address on usb0, SSH daemon with an owner key. Whether an ARM32 SSH
   daemon (dropbear) is available from LibreEcho-Platform is an open question; the ACM shell
   alone satisfies the gate.
f. pack_boot.py guards: enforce the bootopt prefix, cap each appended DTB at 0x80000 bytes
   (LK copies the selected DTB to 0x4e000000), check the first root compatible is
   `amzn,lidar-*`. Do not adopt the reference's BL31-overlap rejection: our 0x850000 kernel
   crosses 0x43000000 and completed every initcall.
g. Hardware sequence: each flash/reboot separately approved, true disconnect-first power
   cycle between steps. First flash carries a+b+c+d+e. If the host still sees no connect, the
   next diagnostic is clock/PHY state (clk_summary, TOPCKGEN, PHY registers) captured through
   pstore after a warm reboot; no such measurement exists in our notes yet.

New Phase 4 gate wording: a development kernel boots from a single slot, and the owner reaches
a root shell over USB CDC ACM (or SSH over USB NCM). Capture `uname -a`, `/proc/cmdline`,
`dmesg` and `/proc/cpuinfo` through that shell, and a pstore console readback after a warm
reboot.

## Correction to earlier plans

UART0 TX is test point TM58 at 1.8 V, 921600 8N1, output only. UART0 RX is on no known test
point (reference README test-point table; not verified on our unit). The earlier note that the
next decisive diagnostic is a 3.3 V UART console (PLAN.md line ~284) is superseded; 3.3 V
would be the wrong level. The UART stays optional.

## Later, not in the Phase 4 gate

Phase 5 candidates from the reference: a second-stage U-Boot chainloaded from boot_a, giving
`fastboot boot`, `oem run`, `oem console` log readback without UART, extlinux on ext4, and A/B
bootcount. Preconditions before any adoption: resolve the env offset contradiction above, add
a hard fastboot deny-list for expdb, lk_*, tee*, BOOT0/BOOT1, kb, dkb, and keep misc[0:16] and
the BCB untouched (PLAN.md boot-chain safety). Their aarch64 Alpine rootfs is not a product
fit.

Phase 6 reference inventory (verified by them on their hardware, not by us): audio
AFE/machine/TLV320 codecs and 7 mics, IS31FL3236 ring LEDs (channel map 3n-2..3n), gpio
buttons, privacy latch GPIO18, KEY_MICMUTE GPIO108, force GPIO107, TSL2540 light sensor,
RT5738/RT5739 vproc cpufreq 598 MHz-1.3 GHz, MT7668 SDIO Wi-Fi/BT with MAC from IDME, EFR32 on
ttyS2, and a musb isochronous PIO fix for UAC2.
