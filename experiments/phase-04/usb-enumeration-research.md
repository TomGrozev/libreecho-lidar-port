# USB peripheral enumeration on MT8516/MT8167/MT8163: primary-source research

Date: 2026-11-15
Question: Linux MUSB gadget/UDC probe succeeds, but the USB host never sees a
connect/enumeration. What do primary sources say about this class of failure on
these SoCs, and which single-factor experiments best discriminate between the
remaining causes?

This note does not modify code, run builds, or touch hardware. Local clones under
`repos/` are used as primary sources; upstream claims are pinned to the v6.6 tag,
upstream commit IDs, U-Boot master, or lore/patchwork URLs.

## Evidence classes used below

- **A (proven from source/commit)**: the mechanism is visible in the cited code,
  binding, or commit. Still a statement about code, not about the board.
- **B (analogy)**: same IP block or sibling SoC, different silicon/board. Useful
  for ranking hypotheses, never for conclusions about this board.
- **C (hypothesis)**: consistent with the sources but not demonstrated.
- **D (measured artifact or local measurement)**: register/DT dump, USB
  observation, or flashed-image result from this project. Recorded, not
  independently re-verified in this note.

## 1. Bottom line

1. **No primary-source report of this exact failure was found.** The closest
   upstream device-mode datapoint is MT7623, where the same MUSB glue plus the
   mainline T-PHY enumerated as a CDC device (A for MT7623; B for MT8163). On
   this unit, stock LK fastboot enumerates as `0bb4:0c01` repeatedly on the same
   board, cable, and host (D), so a known-good peripheral reference already
   exists and no new bootloader port is needed to get one.
2. **Upstream has never validated USB device mode on MT8163 or MT8167.** MT8167
   inherits the MT8516 USB nodes wholesale; the MT8167 dtsi was merged as
   "GPIO, Clocks" only, and the MT8163 arm64 series explicitly defers
   peripherals. So there is no upstream "known good" reference for these two
   SoCs to diff against (A).
3. **The mainline contract is rigid**: one `reg`, exactly three named clocks
   (`main`, `mcu`, `univpll`), required `phys`. A stock-shaped MT8163 node
   (four clocks, two `reg`s; downstream also looks up an optional `vusb`, which
   the stock PVT DT does not have) cannot be used unmodified under
   the mainline binding/driver (A). A custom MT8167 + MT8163 recovery build that
   accepted the stock-shaped node (two `reg` regions, four clocks, the downstream
   optional `vusb` lookup) was flashed and still never enumerated as
   `0525:a4a6` (D, image
   `5aba70f61d81c550ce4a682085f589caabca259a37f2c8165a933a40c7fe9dab`), so
   matching the stock DT shape alone is not the fix.
4. **The two DT descriptions address the same PHY.** The stock second `reg`
   region is the USB SIF bank; the vendor driver reaches the PHY at
   `bank + 0x800`. Mainline instead gives the T-PHY node the bank base and the
   port node `+0x800` (A).
5. **The observed `DEVCTL=0x98` is weaker evidence than it looks.** Mainline
   T-PHY `power_on` sets `RG_VBUSVALID|RG_AVALID`, clears `RG_SESSEND`, and
   `set_mode(DEVICE)` forces IDDIG. So VBUS-valid, session, and ID/b-device
   status can all be synthetic; the dump proves the driver asked for peripheral
   mode, not that the cable/PHY/host path works (A). LK fastboot proves the
   external path itself is fine (D), so the interesting state is what Linux
   changes after LK.
6. **The missing fourth clock is unlikely to be the cause.** U-Boot's DTS lists
   four clocks while its driver gets and enables only three (`usbpll`, `usbmcu`,
   `usb`, with `icusb` unused); the upstream driver uses three, and the
   downstream driver treats all four as optional and never `clk_enable()`s
   `icusb` (A).
7. **Prime suspects narrowed**: with LK enumerating and the stock-shaped Linux
   port still failing, the leading candidates are Linux's T-PHY re-initialization
   (comparator force state), the PHY 48 MHz reference/clock gating, and the
   gadget pullup path. Board wiring, host port, and cable are no longer suspects
   (C, ranked in section 8).

## 2. Upstream description (A)

### 2.1 Device tree

`arch/arm64/boot/dts/mediatek/mt8516.dtsi` (v6.6 and master, unchanged since
the 2020 additions):

- `usb0` at `mt8516.dtsi:470-481`: `compatible = "mediatek,mt8516-musb",
  "mediatek,mtk-musb"`, `reg = <0 0x11100000 0 0x1000>`, IRQ 72, **one**
  `phys = <&usb0_port PHY_TYPE_USB2>`, clocks `CLK_TOP_USB`,
  `CLK_TOP_USBIF`, `CLK_TOP_USB_1P` named `"main","mcu","univpll"`, and
  `status = "disabled"`.
- `usb1` at `:483-495`: same shape at `0x11190000`, `dr_mode = "host"`,
  disabled.
- `usb_phy: t-phy@11110000` at `:497-519`: `mediatek,mt8516-tphy` +
  `mediatek,generic-tphy-v1`; `reg` bank `0x11110000..0x11110800`; port
  `usb0_port` at `:506-511` uses `0x11110800` length `0x100` with
  `clocks = <&topckgen CLK_TOP_USB_PHY48M>`, `clock-names = "ref"`.

Introduced by `5236347bde42` (initial MT8516 dtsi), with the generic fallback
compatible added later (`86c5ed12cf72`) and `usb1` added by `40fe44cab01c`.
The `status = "disabled"` default matters: "probe succeeds" on a board means the
board enabled the node, but the SoC dtsi gives no board-level validation.

Clock identity is a recurring source of confusion:

| DT name | Clock ID | What it gates | Notes |
|---|---|---|---|
| `main` | `CLK_TOP_USB` | USB core clock, parent `usb_78m` | `clk-mt8167.c` gate TOP1 bit 13 |
| `mcu` | `CLK_TOP_USBIF` | bus/interface clock, parent `ahb_infra_sel` | gate TOP2 bit 24 |
| `univpll` | `CLK_TOP_USB_1P` | 1P/USB clock, parent `usb_78m` | gate TOP2 bit 14; name is historical, **not** univpll itself |
| PHY `ref` | `CLK_TOP_USB_PHY48M` | 48 MHz PHY reference | `FACTOR(..., "usb_phy48m_ck", "univpll", 1, 26)` at `clk-mt8167.c:66` |

(`drivers/clk/mediatek/clk-mt8167.c:66,833,865,876`; MT8167 includes
`mt8516-clk.h`, so the IDs are shared.)

### 2.2 Binding

`Documentation/devicetree/bindings/usb/mediatek,musb.yaml`:

- compatible enum `mediatek,mt8516-musb`, `mediatek,mt8167-usb20`,
  `mediatek,mt2701-musb`, `mediatek,mt7623-musb` + required fallback
  `mediatek,mtk-musb` (`:16-24`).
- `reg: maxItems: 1` (`:26-27`).
- `clocks` exactly three entries (`:38-43`), `clock-names` exactly
  `main`, `mcu`, `univpll` (`:45-50`).
- `phys: maxItems: 1` and `phys` is in `required` (`:52-53`, `:81-88`).
- `dr_mode` allows `peripheral` (`:60-64`).
- `additionalProperties: false` (`:90`). There is **no** `vusb` property.

Consequence: the downstream MT8163 shape (4 clocks, 2 regs, a `vusb` lookup, no
`phys`) is not merely ignored: it is rejected by the binding, and `clk_bulk_get`
would fail on a 4-clock/3-name node even without schema validation.

Also note the binding allows `mediatek,mt8167-usb20` but the driver's
`of_device_id` table contains only `mediatek,mtk-musb`
(`drivers/usb/musb/mediatek.c:523`). A stock-compatible node with no
`mediatek,mtk-musb` fallback therefore does not probe under mainline at all
(inference directly from the match table).

### 2.3 Glue driver

`drivers/usb/musb/mediatek.c` (v6.6):

- `MTK_MUSB_CLKS_NUM 3` (`:40`), bulk clock names hardcoded (`:50,63`).
- `mtk_musb_probe` (`:400`): `devm_of_phy_get_by_index(dev, np, 0)` (`:455`)
  makes the PHY mandatory, and `clk_bulk_prepare_enable` (`:480`) runs in
  probe; the MUSB child device is registered afterwards.
- `mtk_musb_init` (`:258-303`) is where PHY sequencing happens:
  `phy_init` → `phy_power_on` → `phy_set_mode(glue->phy, glue->phy_mode)`
  (`:277-285`). For `dr_mode = "peripheral"`, `glue->phy_mode` is
  `PHY_MODE_USB_DEVICE` (`:443-446`).
- No SoC-specific pdata, PHY base, second register bank, `vusb`, or
  `needs_soc_phy_recover` exists upstream. Recent upstream commits to this file
  are cleanups only.

### 2.4 T-PHY

`drivers/phy/mediatek/phy-mtk-tphy.c` (v6.6):

- `mtk_phy_power_on` (`:1393`); U2 power-on sets
  `P2C_RG_VBUSVALID | P2C_RG_AVALID` (`:871`) and clears `P2C_RG_SESSEND`
  (`:873`). Power-off reverses both (`:893-895`).
- `mtk_phy_set_mode` (`:1433`): for `PHY_MODE_USB_DEVICE` it only sets
  `P2C_FORCE_IDDIG | P2C_RG_IDDIG` (`:930`); for host it sets `FORCE_IDDIG`
  alone (`:933`); for OTG it clears both (`:937`).
- There is **no** mainline force for BVALID or for the session-end comparator in
  device mode. Only IDDIG is forced; VBUSVALID/AVALID are *set as RG fields*,
  i.e. driven to valid, not measured.

## 3. Downstream/vendor MT8163 description (A for that tree; B for silicon behaviour)

Source: `repos/LibreEcho-Platform/drivers/misc/mediatek/usb20/mt8163/`.
The register sequences are vendor-original; the clock-get block has local
"tolerate missing clock" edits (see below), so do not treat its error handling as
stock behaviour.

### 3.1 Resources and supplies

- `mt_usb_dts_probe` (`usb20.c:1296`) gets four clocks by name, in order:
  `"usbpll"`, `"usb"`, `"usbmcu"`, `"icusb"` (`:1309,1323,1337,1355`).
  Every lookup and prepare is optional: a missing clock logs a warning and the
  driver continues "using bootloader USB setup". `icusb` is prepared but no
  `clk_enable(icusb_clk)` call exists anywhere in the driver (grep of the tree).
- `mt_usb_init` (`usb20.c:1044`) gets regulator `"vusb"` (`:1079`);
  failure is silently tolerated (`if (!IS_ERR(reg))`). The stock Lidar PVT
  `usb@11100000` node decompiled directly by Main has **no `vusb` property and
  no supply** (D), so this lookup is dead code on this board and neither the
  vendor driver nor mainline needs a `vusb` model here.
- The second `reg` region is the USB SIF bank. PHY accessors are
  `xceiv->io_priv + 0x800 + offset` (`mtk_musb.h:6-20`). On MT8163 the stock
  second region is `0x11210000`, so PHY register `0x6c` lives at
  `0x11210800 + 0x6c`, the same layout as the mainline T-PHY port node.
  On MT8516/MT8167 the mainline T-PHY already models exactly this:
  `0x11110000` bank + port `0x11110800` (A).

### 3.2 PHY sequences

`usb20_phy.c` power-on (`:343-398`) and recover (`:495-590`); recover is called
from `mt_usb_enable` (`usb20.c:253`) and the save/restore path is
`usb20.c:282`.

Power-on: clear `0x6b/0x6e/0x21`, set `0x22|0x04`, clear `0x22|0x03`, set
`0x20|0x10`, clear `0x6a|0x04`, program `0x18`, `udelay(800)`, write
`0x6c=0x2e`, `0x6d=0x3e`, then `0x05=0x77`.

Recover: clear `0x1d|0x10`, `0x6b|0x04`, `0x6e|0x01`, `0x6a|0x04`,
`0x21|0x03`, `0x68|0xf4`, `0x69|0x3c`, `0x6a|0xba`, `0x1a|0x80`; set
`0x1a|0x10`, program `0x18`, delay 800 µs, force all of `0x6c/0x6d`,
`0x05=0x77`.

These are the same class of "force the PHY comparators and terminations" writes
as U-Boot. They are evidence that this PHY family needs explicit force writes to
present a device; they are **not** evidence that mainline's smaller force set is
wrong (MT7623 works with mainline's set).

## 4. U-Boot MT85xx driver (A, source reference)

`drivers/usb/musb/mt85xx.c` (U-Boot master):

- PHY base hardcoded at `0x11110800`, independent of DT.
- Gets/enables three clocks named `usbpll`, `usbmcu`, `usb`; the fourth DTS
  clock `icusb` is unused. Original driver commit `7d017d607eaa` (MediaTek,
  Jan 2020); DTS commit `9fe7493b80` (Fabien Parent, Oct 2020) added four
  clocks with names `usbpll/usbmcu/usb/icusb` and a single `reg`.
- `mt_usb_phy_poweron` writes `0x6c=0x2e`, `0x6d=0x3e` after an 800 ms delay.
- `recover()` has the device-force writes commented out and sets `0x00` bit 5.
- Board-level gadget enable: `4e828d9c75f` (`usb_ether_init`) and
  `d67393503be` (Pumpkin gadget config), enumerating as `0e8d:201c`.

Why this matters: U-Boot is a different driver with a *smaller* clock set, a
hardcoded PHY base, no `vusb`, and no T-PHY framework, and it enumerates on
MT85xx/MT8167 family boards. That makes it evidence that three clocks plus a
hardcoded PHY base are sufficient for this IP, not an end-to-end control for
this unit; LK fastboot is that control (section 6, E2).

## 5. What the MUSB/PHY sources say about a "silent" device

### 5.1 Session bit and b-device

`drivers/usb/musb/musb_core.c`:

- `musb_peri_setup` (`:516-548`) reads `DEVCTL`; **if `BDEVICE` is already
  set it returns immediately** (`:529-531`). It only clears `SESSION` when the
  controller is *not* already in peripheral mode (`:534`).
- `musb_host_setup` is the path that sets `SESSION` (`:465-501`).

So `DEVCTL = 0x98` (BDEVICE `0x80` + VBUS field `0x18`, session `0`) is exactly
what the core expects in peripheral mode with VBUS reported full. Session `0` is
not a bug and not evidence of a failed session negotiation.

### 5.2 Pullup

`musb_gadget.c:1598-1606` (`musb_pullup`) only toggles `MUSB_POWER_SOFTCONN`
in the MUSB controller; it makes no PHY call. The D+ pullup itself is analog,
inside the PHY, and is what a host actually detects. `POWER.SOFTCONN` being set
therefore proves only that the gadget requested a connect, not that a 1.5 kΩ
pullup appeared on D+.

### 5.3 Why `DEVCTL` cannot be trusted as board evidence here

Both upstream and the local tree force the comparator inputs:

- Upstream `power_on`: `RG_VBUSVALID` and `RG_AVALID` set, `RG_SESSEND` cleared
  (`phy-mtk-tphy.c:871-873`).
- Upstream `set_mode(DEVICE)`: IDDIG forced (`:930`).
- Local working-tree patch `vendor_device_mode_force`
  (`phy-mtk-tphy.c:298,515,607-635,1237`, not upstream) additionally forces
  AVALID/BVALID/VBUSVALID in the device init path (`:607-625`) on top of
  forcing IDDIG (`:628-631`).

Therefore BDEVICE, VBUS-valid, and session state in a register dump taken after
probe reflect driver intent and forced PHY inputs at least as much as the cable.
The trustworthy external observables are: host-side VBUS with an inline meter,
a 1.5 kΩ D+ pullup at the connector, 48 MHz at the PHY reference, and host
enumeration itself.

## 6. Prior reports and their limits

Searched/reviewed for this note: lore.kernel.org and the linux-mediatek /
linux-arm-kernel archives (MT8516/MT8167 dtsi threads; MT7623 MUSB threads),
the mainline MT8167 dtsi submission, U-Boot MT85xx commits, and the vendor tree
in `repos/LibreEcho-Platform`. Within that material:

- **No report found** of "UDC probes, gadget binds, host never enumerates" on
  MT8163/MT8167/MT8516. Absence of a report is not proof that none exists; it
  does mean there is no community workaround to copy.
- **MT7623 works in device mode**: Sungbo Eo, Aug 2021,
  <https://lists.infradead.org/pipermail/linux-arm-kernel/2021-August/675947.html>:
  mainline `mtk-musb` + `mtk-tphy`, `g_cdc` enumerates. The thread also
  documents a role-switch ordering quirk (gadget must load before host role is
  used). This is the strongest B-class evidence that the mainline glue/PHY
  device path is sound on this IP family.
- **MT8167 dtsi was merged as "GPIO, Clocks" only**: Fabien Parent,
  <https://lists.infradead.org/pipermail/linux-arm-kernel/2020-October/612321.html>
  ("This commit is just adding the basic dtsi file with the support of the
  following IOs: GPIO, Clocks"). MT8167 has no USB node of its own; it inherits
  the disabled MT8516 nodes.
- **MT8516/MT8167 dtsi fixes (Dec 2024) contain no USB changes**: GIC range,
  watchdog IRQ type, i2c clock-div, TF-A reservation, keypad
  <https://lists.infradead.org/pipermail/linux-mediatek/2024-December/086862.html>.
- **MT8163 arm64 support series explicitly defers peripherals**: Ben Grisdale,
  v2 0/6 (Oct/Nov 2026),
  <https://lists.openwall.net/linux-kernel/2026/11/05/2496>: SoC + Echo Dot,
  "further peripherals later"; no USB node.
- **Project-local, not upstream**: commit `d2cb959ead4b` adds MT8163 pdata with
  four clocks, `phy_optional`, `needs_soc_phy_recover`, a second `reg` bank plus
  `0x800` offset, and a `vusb` lookup. Treat it as a downstream port, not as
  evidence of what mainline requires.

### Local measured controls (D)

- **LK fastboot enumerates as `0bb4:0c01`**, repeatedly, on this exact board,
  cable, and host. It is the end-to-end known-good peripheral control. At the
  moment fastboot is reachable, the connector, host port, VBUS, ID strap,
  D+/D-, pad mux, clock tree, and PHY are all in a working state under LK. Stock
  LK source is not in this workspace, so the comparison in E2 is behavioral and
  register-based unless that source is obtained.
- **The stock-shaped two-reg/four-clock port was measured negative.** A
  MT8167 + MT8163 recovery experiment with the downstream-compatible driver
  changes and the stock-shaped node (two `reg` regions, four clocks, the
  downstream optional `vusb` lookup) was flashed as image
  `5aba70f61d81c550ce4a682085f589caabca259a37f2c8165a933a40c7fe9dab`. A valid
  `uv`-run PyUSB observer saw the chain `fastboot -> preloader -> fastboot` but
  never the Linux gadget `0525:a4a6`. The source experiment is being reverted.
  This is a measured negative for "match the stock DT shape and it will
  enumerate", not proof that every two-reg/four-clock variant is equivalent.

## 7. Hypothesis assessment

| # | Hypothesis | Class | Evidence for | Evidence against | Discriminating test |
|---|---|---|---|---|---|
| H1 | Missing 4th clock (`icusb`) or clock ordering | A/D against | stock DT lists 4 clocks | U-Boot works with 3 (DTS lists 4, driver enables 3); upstream uses 3; vendor never enables `icusb`; all four are optional in vendor code; the 4-clock build still failed (D) | clk_summary/register audit (E1) |
| H2 | PHY base/second `reg` mismatch | A/D against | stock node has 2 regs; the stock-shaped build was tried | stock bank+0x800 == tphy port address; the 2-reg/4-clock build still never enumerated (D) | none; measured |
| H3 | PHY 48 MHz ref absent / wrong rate | A mechanics | `usb_phy48m_ck` is univpll/26; if univpll is off the PHY has no ref | none yet on this board | read `clk_summary` rates and TOPCKGEN/USB gate regs (E1) |
| H4 | PHY force state prevents a D+ pullup even though the PHY is powered | A mechanics, C for this board | PHY needs force writes; mainline forces VBUSVALID/AVALID/IDDIG; local patch forces more | LK fastboot pulls up and enumerates with LK's own PHY init; MT7623 enumerates with mainline's smaller force set | LK-vs-Linux init comparison (E2); vanilla-TPHY A/B (E3); D+ measurement (E6) |
| H5 (withdrawn) | `vusb` rail off on this board | D against | downstream code looks up `"vusb"` | the stock Lidar PVT `usb@11100000` has no `vusb` property or supply (Main decompiled it directly); the lookup is dead code | none; hypothesis removed |
| H6 | Linux re-muxes or resets IDDIG/D+/D- pads that LK had left working | C | MT8167 pinfunc muxes IDDIG (pins 17/19) and USB_DRVVBUS (18/22); Linux pinctrl can reset pads | LK fastboot proves the pads can carry USB, so only a Linux-side difference remains | pinmux read under LK vs Linux; force A/B (E5) |
| H7 | Gadget never actually pulled up (config/UDC not bound) | A mechanics | pullup is a gadget action; UDC may be "not attached" | "UDC probe succeeded" does not prove a gadget bound and called pullup | `state`/`soft_connect` read, configfs vs g_serial (E4) |
| H8 | Local T-PHY force patch regressed enumeration | C | it changes exactly the comparator state; failure observed on patched tree | no report either way | revert patch only (E3) |
| H9 (withdrawn) | Host port/cable/port role | D against | trivial but common | LK fastboot enumerates as `0bb4:0c01` repeatedly on the same board, cable, and host | none; hypothesis removed |
| H10 | Linux undoes a clock/PHY state that LK had already enabled (warm-boot dependency) | C | LK leaves USB running; the failing boots pass through LK; Linux re-inits clocks and PHY from scratch | LK-to-Linux handover is the normal boot path, so a working handover should be achievable; no proof either way | preserve-LK-state vs re-init A/B (E2) |

## 8. Ranked experiments

Each changes one factor. Stop at the first test that flips enumeration; do not
stack DT-shape changes with driver changes.

### E1: Read-only clock and PHY state audit (free, no reboot)

Read `/sys/kernel/debug/clk/clk_summary` for `usb_phy48m_ck`, `usb`, `usbif`,
`usb_1p`, their parents (`univpll`, `usb_78m`, `ahb_infra_sel`), and the prepare/
enable counts. Dump T-PHY `0x11110800 + {0x18,0x1a,0x21,0x22,0x6a,0x6b,0x6c,
0x6d}`, plus `POWER` and `DEVCTL` from the MUSB regs, *before and after* the
gadget binds.

- Confirms: whether the PHY ref is actually running, whether all three glue
  clocks are enabled, and whether the force bits changed at pullup time.
- Falsifies H1/H3 if all rates/enables are sane and stable.
- Caveat: enabled counts do not prove a clock reaches the PHY; a gate can be on
  with a dead parent mux. Read the TOPCKGEN gate/mux registers too.
- Cost: minutes, read-only, no risk.

### E2: LK fastboot initialization comparison (known-good control)

LK fastboot enumerates as `0bb4:0c01` repeatedly on this board, cable, and host,
so the PHY, pad mux, clock tree, and connector path are demonstrably working when
LK runs. Linux then boots from that state and re-initializes the T-PHY and MUSB;
the failure appears after that point. Compare the two initializations, one factor
at a time:

1. **Preserve vs re-init A/B** (highest value, one factor). Boot the same kernel,
   DT, and gadget userspace, but suppress only the T-PHY re-initialization in
   `mtk_musb_init` / `mtk_phy_power_on` / `mtk_phy_set_mode`, keeping LK's
   already-working PHY state and the three glue clocks enabled across the
   handover. Everything else stays identical.
   - Enumerates: Linux's PHY init is the divergence. The diff targets are
     `power_on` (`RG_VBUSVALID|RG_AVALID`, `RG_SESSEND`), `set_mode` IDDIG
     forcing, and the local `vendor_device_mode_force` writes (E3).
   - Still fails: the PHY was already valid, so the fault is in the MUSB/gadget
     pullup path (E4) or in a clock that Linux gates off (E1), not in PHY init.
2. **State capture before the driver probes** (read-only). Dump the USB clock
   gates, pinmux, and PHY registers at the earliest Linux point before the MUSB
   driver binds, and compare with the same registers while LK fastboot is
   enumerated (if LK can be instrumented) or with LK's documented write set.
   This shows exactly what Linux changes; it does not by itself prove which
   change matters.
3. **Source diff where source exists.** Stock LK source is not in this workspace,
   so obtain it (or the MTK LK release for this platform) and diff its USB init
   against `mediatek.c`, `phy-mtk-tphy.c`, and the vendor `usb20_phy.c` write
   list. Until then, treat LK as a black-box known-good control.

- Single factor: re-init vs preserve, with DT, clocks, gadget, and cable fixed.
- Do not power-cycle between LK fastboot and the Linux boot under test unless the
  experiment is specifically cold-boot vs warm-boot; the LK-left state is the
  variable being tested.
- Why not U-Boot: LK already is the shipping known-good stack on this exact
  device. A U-Boot port would add work without adding evidence.

### E3: Revert only the local T-PHY force patch

Restore upstream v6.6 T-PHY behaviour (force IDDIG only; no AVALID/BVALID/
VBUSVALID forcing) while keeping the current DT and gadget userspace identical.

- If enumeration returns: the local `vendor_device_mode_force` patch is the
  regression; diff its `0x6c/0x6d` writes against vendor recover/power-on.
- If nothing changes: H8 is dead; stop tuning force bits and move to E4/E6.
- Single factor: T-PHY comparator forcing.
- Caveat: keep a copy of the current kernel/DT hash so the A/B is unambiguous.

### E4: Prove whether a pullup was requested at all

Check the UDC `state` (and `soft_connect`) in configfs after binding, then repeat
with a minimal `g_serial`/`gadget` via configfs instead of the current composite.

- `state` stays "not attached": gadget never reached pullup; the problem is
  userspace/config ordering, not the PHY (H7).
- `state` becomes "configured"/"not attached" inconsistently: compare
  `POWER.SOFTCONN` with the PHY force bits to see who is lying.
- Single factor: gadget stack/ordering. Cheap and non-invasive.

### E5: IDDIG and pad mux under Linux

LK already proves the pads can carry USB. Read the pinmux registers for IDDIG
(pins 17/19 on MT8167) and USB_DRVVBUS (18/22) under LK fastboot and under Linux
with the UDC bound; add a Linux pinctrl state only if it differs.

- If Linux leaves a pad as GPIO where LK muxed it, and adding that pinctrl state
  restores enumeration, H6 is confirmed. Single factor: pinctrl state.
- If the mux is identical, pads are not the difference; move to E6.
- Do not toggle VBUS/DRVVBUS pins experimentally without the schematic; a wrong
  VBUS back-drive can damage the host or the SoC.

### E6: D+ pullup and 48 MHz at the connector

LK fastboot already proves host VBUS and the data path, so only the Linux-side
analog state needs measuring. Compare, under LK fastboot and under Linux with the
UDC bound:

- 1.5 kΩ D+ pullup at the connector (or the D+ high level with a suitable probe).
- 48 MHz at the PHY reference test point.

- No pullup under Linux but present under LK: PHY force/clock problem inside
  Linux (H3/H4); the LK init diff (E2) is the next step.
- Pullup present under Linux but no host traffic: revisit MUSB/gadget (E4),
  since host, cable, and D- are proven by LK.
- 48 MHz absent only under Linux: clock tree/gate issue; tie back to E1.
- Use an inline meter for VBUS; do not back-drive VBUS.

De-prioritized: porting or reviving the downstream `mt8163` pdata
(`d2cb959ead4b`) with four clocks, a second bank, `phy_optional`, and a `vusb`
lookup. The stock-shaped two-reg/four-clock build already measured negative
(section 6), the upstream binding rejects that shape, and U-Boot's DTS lists four
clocks while its driver enables only three. It is not a fix candidate.

## 9. Consequences for the local DT decision

- **Do not add a second `reg`** for the mainline driver. The stock second region
  is the SIF bank, and mainline already covers it with the T-PHY bank/port
  split. `reg: maxItems: 1` is enforced.
- **Do not carry four clocks** into the mainline node. `clk_bulk_get` uses three
  hardcoded names; the fourth is unused by U-Boot and never enabled downstream.
- **There is no `vusb` property or supply in the stock PVT DT** (D). Nothing
  needs modeling, and the downstream `"vusb"` lookup is dead code on this board;
  do not add such a property to the mainline node (the binding rejects it).
- **Keep `phys` and the `mediatek,mtk-musb` fallback.** Without the fallback, a
  stock-shaped `mediatek,mt8167-usb20` node does not match the driver.
- **`phy_optional` is a downstream invention**, not upstream semantics; it only
  makes sense if the board has no T-PHY node at all, which contradicts the
  address evidence above.
- **The mainline 3-clock node is the correct long-term shape.** The 2-reg/
  4-clock build was measured negative (D), and LK proves the board-level path.
  The remaining fault is in Linux's clock rates, T-PHY re-initialization/force
  state, warm-boot handover, or gadget pullup, not in the DT shape.
- **Do not revive the stock-shaped experiment as a fix.** It has been reverted
  and it did not enumerate.

## Sources

Primary:

- `arch/arm64/boot/dts/mediatek/mt8516.dtsi` (v6.6): `:470-481`, `:497-519`.
- `Documentation/devicetree/bindings/usb/mediatek,musb.yaml` (v6.6):
  `:16-90`.
- `drivers/usb/musb/mediatek.c` (v6.6): `:40,50,63,258-303,400,455,480,523`.
- `drivers/usb/musb/musb_core.c` (v6.6): `:465-548`.
- `drivers/usb/musb/musb_gadget.c` (v6.6): `:1598-1606`.
- `drivers/usb/musb/musb_regs.h`: `MUSB_DEVCTL_BDEVICE 0x80`,
  `MUSB_DEVCTL_VBUS 0x18`, `MUSB_DEVCTL_SESSION 0x01`.
- `drivers/phy/mediatek/phy-mtk-tphy.c` (v6.6): `:871-895,930-937,1393,1433`.
- `drivers/clk/mediatek/clk-mt8167.c`: `:66,833,865,876`.
- Commits: `5236347bde42`, `86c5ed12cf72`, `40fe44cab01c` (MT8516 dtsi/USB),
  `d2cb959ead4b` (project-local MT8163 pdata).
- U-Boot: `drivers/usb/musb/mt85xx.c`; commits `7d017d607eaa` (driver),
  `9fe7493b80` (DTS), `4e828d9c75f`, `d67393503be` (board gadget).

Mailing list / reports:

- MT7623 device-mode success:
  <https://lists.infradead.org/pipermail/linux-arm-kernel/2021-August/675947.html>
- MT8167 dtsi submission (GPIO/clocks only):
  <https://lists.infradead.org/pipermail/linux-arm-kernel/2020-October/612321.html>
- MT8516/MT8167 dtsi fixes, no USB changes:
  <https://lists.infradead.org/pipermail/linux-mediatek/2024-December/086862.html>
- MT8163 arm64 bring-up, peripherals deferred:
  <https://lists.openwall.net/linux-kernel/2026/11/05/2496>

Downstream tree (analogy / comparison only):

- `repos/LibreEcho-Platform/drivers/misc/mediatek/usb20/mt8163/usb20.c`:
  `:253,282,1044,1079,1296-1364`.
- `.../mt8163/usb20_phy.c`: `:343-398,495-590`.
- `.../usb20/mtk_musb.h`: `:6-20`.

Local measurements (D, recorded from this project):

- Stock Lidar PVT `usb@11100000` decompiled directly by Main: no `vusb`
  property or supply.
- LK fastboot enumerates as `0bb4:0c01` repeatedly on the same board, cable, and
  host. Stock LK source is not present in this workspace.
- Stock-shaped two-reg/four-clock MT8167 + MT8163 recovery build, image
  `5aba70f61d81c550ce4a682085f589caabca259a37f2c8165a933a40c7fe9dab`:
  `uv`-run PyUSB observer saw `fastboot -> preloader -> fastboot`, never
  `0525:a4a6`. Source experiment being reverted.
