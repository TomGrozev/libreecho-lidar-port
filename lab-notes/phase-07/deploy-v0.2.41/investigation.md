# Why v0.2.41 panics at boot

Scope: Linux 6.18.64 built from private/integration/LibreEcho-Linux (head faf4056ba9b1).
Evidence only: pstore/dmesg-ramoops-0, deploy logs, the git trees and the built images.
No hardware loop was possible (investigation only, no build and no device), so this is a
differential static analysis: known-good build against the failing build, plus the fault
record. Every conclusion below names the file and line or commit it rests on.

Headline: two independent defects chain into the panic.

1. `mtk_musb_set_mode()` no longer treats "set the mode that is already active" as a
   no-op. Probe asks for the peripheral mode it was configured for, gets -EINVAL, and
   aborts. Introduced by 6f13c1a4825a.
2. The musb core error unwind frees the driver instance while its gadget device is still
   registered on the gadget bus. That dangling device is what configfs later walks into.
   This unwind is pre-existing (unchanged by 6f13c1a and present in the maintainer base),
   but it only fires because of defect 1.

## Stage 1: "Does not support changing modes", probe fails -EINVAL

Inputs that are identical between the working and the failing kernel:

* Device tree. `arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:743-745` sets
  `&usb0 { dr_mode = "peripheral"; status = "okay"; }`, with no `usb-role-switch`,
  connector or extra phys. The known-good source commit 8cb65710c72f has the same node
  (`arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:491-494` at that commit), only the
  order of the two properties differs. The DT change in the integration line
  (acef477032bf "arm64: dts: mediatek: add the LibreEcho Lidar board") does not touch
  this node's meaning.
* Kernel configuration. Both `private/artifacts/phase-06/kernel-step36-thermal/config`
  (known-good) and `private/artifacts/builds/cache/kernel/faf4056.../config` (v0.2.41)
  have `CONFIG_USB_MUSB_HDRC=y`, `CONFIG_USB_MUSB_DUAL_ROLE=y`,
  `CONFIG_USB_MUSB_MEDIATEK=y` and `CONFIG_USB_ROLE_SWITCH=y`, with
  `CONFIG_USB_MUSB_HOST` and `CONFIG_USB_MUSB_GADGET` both unset. The two configs do
  differ elsewhere (CPUFREQ_DT, MTK_THERMAL, PMIC_WRAP and compiler identity flags), but
  nothing in the USB or gadget selection differs, so the configuration is not the input
  that changed this code path.

So the differing input is driver source. The known-good image was built from
`fix/lidar-port-identity` 47feddd6b58f, a direct child of 8cb65710c72f with no branches
combined (`private/artifacts/phase-07/ota-v0.2.35/build-info.json`, inputs.kernel_commit
and kernel_commit_note). That tree has the stock set_mode: `grep -c mode_lock` on
`8cb65710:drivers/usb/musb/mediatek.c` returns 0, and `git merge-base --is-ancestor
6f13c1a4825a 8cb65710c72f` exits 1. The maintainer commit 6f13c1a4825a is an ancestor of
the integration base 16989cef41b7 (exit 0), so every build on origin/feature/linux-6.18,
including v0.2.40 at 6.18.58, carries it. That matches the identical failure recorded for v0.2.40 in the lab
workspace.

The code path:

* `drivers/usb/musb/musb_core.c:2336` sets `musb->port_mode = plat->mode`. The glue
  fills `pdata->mode = usb_get_dr_mode(dev)` in `mtk_musb_probe()`, so with
  `dr_mode = "peripheral"` the port mode is `MUSB_PERIPHERAL`.
* `musb_core.c:2540` calls `musb_gadget_setup()`, which registers the gadget with the UDC
  core. Then `musb_core.c:2543` calls `musb_platform_set_mode(musb, MUSB_PERIPHERAL)`,
  which reaches `mtk_musb_set_mode()` via `musb_core.h:536-541`.
* In the failing tree `mtk_musb_set_mode()` (`drivers/usb/musb/mediatek.c:887`) maps
  `MUSB_PERIPHERAL` to `USB_ROLE_DEVICE`, then at `mediatek.c:910-912` rejects every
  non-OTG port:
  `if (musb->port_mode != MUSB_OTG) { dev_err(..., "Does not support changing modes"); return -EINVAL; }`.
* Probe also initialises `glue->role = USB_ROLE_DEVICE` and
  `glue->phy_mode = PHY_MODE_USB_DEVICE` for this DT (`mediatek.c:1176-1179`), so the
  request is for the role that is already active.

The maintainer base before 6f13c1a handled exactly that case. At
`af430c2a73f6:drivers/usb/musb/mediatek.c:218` the function computed both `new_mode`
(PHY_MODE_USB_DEVICE) and `new_role`, and at lines 243-245 returned 0 before the port-mode
guard:

    if (glue->phy_mode == new_mode)
        return 0;

With `dr_mode = "peripheral"` that comparison is true, so the probe-time
`musb_platform_set_mode(MUSB_PERIPHERAL)` was a no-op and probe succeeded. 6f13c1a
deleted those lines and the `new_mode` variable. The deletion is visible in the commit
diff, hunk `@@ -215,24 +859,47 @@` (removal of `enum phy_mode new_mode` and its
assignments) and hunk `@@ -240,15 +907,23 @@` (removal of the three-line early return
immediately before the guard that prints "Does not support changing modes"). The rewrite
replaced the phy-mode equality test with a role-queueing path that is only reachable for
`MUSB_OTG`, and left no equivalent no-op for peripheral or host ports.

`status` is -EINVAL, so `musb_core.c:2559` (`if (status < 0) goto fail3`) is taken.

## Stage 2: the gadget device is left registered on a freed driver instance

`fail3` (`musb_core.c:2572`) cancels work, destroys DMA and then falls through
`pm_runtime_put_sync()` at 2584, `pm_runtime_disable()` at 2585, `fail2` at 2587,
`musb_platform_exit()` at 2590 and `musb_free()` at 2595. Nowhere in that path is
`musb_gadget_cleanup()` (`drivers/usb/musb/musb_gadget.c:1903`, the only caller of
`usb_del_gadget_udc()`) called. Compare `musb_remove()` at `musb_core.c:2649-2658`, which
does call it on the normal teardown.

That leaves the gadget device registered:

* `musb_gadget_setup()` calls `usb_add_gadget_udc()` (`musb_gadget.c:1892`), which links
  the gadget to a `usb_udc` (`drivers/usb/gadget/udc/core.c:1429`) and registers the UDC
  device with `device_add(&udc->dev)` (`udc/core.c:1447`). The gadget's own `struct
  device` is part of the registered device hierarchy at that point.
* `usb_del_gadget()` is the only routine that later removes it, and it returns early when
  `gadget->udc` is NULL (`udc/core.c:1579`), which is never even attempted here.
* The `struct musb` that embeds `musb->g` is allocated with
  `devm_kzalloc()` on the musb-hdrc platform device (`musb_core.c:2150`). When
  `really_probe()` fails, the driver core calls `devres_release_all()` (`drivers/base/dd.c:610`),
  so that memory, including the gadget structure, is freed while the gadget device it
  contains is still on the gadget bus.

Later, `libreecho-init` writes the UDC name into configfs. That runs
`gadget_dev_desc_UDC_store()` -> `usb_gadget_register_driver_owner()` ->
`driver_register()` (`udc/core.c:1747`) -> `bus_for_each_dev()` -> `gadget_match_driver()`
(`udc/core.c:1620`). The iteration finds the stale gadget device, reads its freed memory,
and dereferences the NULL `udc` pointer recorded in the panic.

This unwind defect is not ours and not 6f13c1a's: `git diff af430c2..HEAD --
drivers/usb/musb/musb_core.c` shows only two added lines in the suspend/resume paths
(`musb_gadget_disable_rx_kicks` at 2825 and `enable` at 2875), and the same `fail3` shape
exists at the maintainer base. It is a latent upstream bug that needs a probe failure
after `musb_gadget_setup()` to become reachable, and defect 1 supplies exactly that.

The "Runtime PM usage count underflow" line is part of the same unwind and is expected
once probe fails:

* `musb_core.c:2470` takes one reference (`pm_runtime_get_sync`).
* `fail3`'s `pm_runtime_put_sync()` at 2584 drops it to zero.
* `musb_platform_exit()` at 2590 calls `mtk_musb_exit()`, which does
  `pm_runtime_put_sync(dev)` again at `mediatek.c:1038` on the same musb-hdrc device,
  producing the underflow warning.

The maintainer base already had that second put (`af430c2:drivers/usb/musb/mediatek.c:344-345`),
so the underflow is a consequence of any musb probe failure, not a separate regression.

## Stage 3: decoding the fault

The failing Image is `private/artifacts/builds/cache/kernel/faf4056.../Image`. The five
reported code words `d1012033 f9406e60 b40000e0 f85b0042 (f9403441)` occur exactly once,
at file offset 0x482c3c. Disassembling that window (`aarch64-linux-gnu-objdump -b binary
-m aarch64`) gives:

    482c30: mov  x2, x0                 ; x2 = dev (first argument)
    482c3c: sub  x19, x1, #0x48         ; driver = container_of(drv, usb_gadget_driver, driver)
    482c40: ldr  x0, [x19, #216]        ; driver->udc_name
    482c44: cbz  x0, 0x482c60
    482c48: ldur x2, [x2, #-80]         ; udc = gadget->udc, gadget = dev - 0x70, udc at +0x20
    482c4c: ldr  x1, [x2, #104]         ; dev_name(): &udc->dev.init_name   <-- faults
    482c50: cbnz x1, 0x482c58
    482c54: ldr  x1, [x2, #24]          ; fallback, kobject name at &udc->dev
    482c58: bl   strcmp                 ; udc_name vs dev_name(&udc->dev)
    482c60: ldrb w0, [x19, #224]        ; driver->is_bound
    482c64: eor  w0, w0, #2
    482c68: ubfx w0, w0, #1, #1         ; return !is_bound

This is `gadget_match_driver()` inlined: `dev_to_usb_gadget(dev)` at `udc/core.c:1622`,
`gadget->udc` at 1623, then the `strcmp(driver->udc_name, dev_name(&udc->dev))` test.
The faulting instruction is `ldr x1, [x2, #104]` with `x2 = 0`, so the fault address is
0x68. That matches the register dump (`x2 = 0`, `x0` = the device pointer, `x1` and
`x19` live) and the logged `virtual address 0x68`. The NULL pointer is therefore
`gadget->udc`: the freed gadget's UDC pointer read back as zero. Offset 104 is
`offsetof(struct usb_udc, dev) + offsetof(struct device, init_name)`, which is the first
load of `dev_name()`; the fallback load at offset 24 is `dev->kobj.name`.

## Stage 4: the role of commit 6f13c1a4825a

6f13c1a4825a "usb: musb: mediatek: MT8163 dual-role and console diagnostics" is the cause
of the probe failure and the trigger of the panic, but not the author of the unwinder
bug.

* Causal hunk for stage 1: in `drivers/usb/musb/mediatek.c`, the removal of
  `if (glue->phy_mode == new_mode) return 0;` and its `new_mode` plumbing (old lines
  215-245 region; the commit diff hunk `@@ -240,15 +907,23 @@`). Nothing else in the
  commit changes how a non-OTG port's probe-time `set_mode` is handled.
* Not the cause of stage 2: the commit touches `mediatek.c`, `musb_gadget.c` and
  `f_fs.c`, not `musb_core.c` or `udc/core.c`. The missing `musb_gadget_cleanup()` in
  `fail3` and the gadget-bus registration are stock.
* Note for the record: the same commit also rewrites `musb_ep_restart()` in
  `musb_gadget.c` (the FIFO-flush path becomes `rxstate()`), which is a behavioural
  change, not a diagnostic. It is unrelated to this panic but should be reviewed on its
  own.

v0.2.40's identical panic at 6.18.58 shows the defect arrived with the maintainer base
merge, not with the 6.18.64 stable update (6167e214df3a) and not with any LibreEcho topic.

## Recommended fix (not a revert)

Primary, in the musb MediaTek glue. Restore the "already in this role" no-op inside
`mtk_musb_set_mode()`, before the OTG-only guard at `mediatek.c:910`: after computing
`new_role`, return 0 when `new_role == glue->role`. For this board probe-time
`MUSB_PERIPHERAL` maps to `USB_ROLE_DEVICE`, which equals the `glue->role` set for
`dr_mode = "peripheral"` at `mediatek.c:1176-1179`, so the call becomes a no-op again.
This keeps the new role-queue design for OTG ports and does not resurrect the phy_mode
coupling. (Equally valid: reintroduce `new_mode` and the original phy-mode equality
test. The role comparison is preferred because `mtk_otg_switch_set()` already uses it as
its own idempotence check.)

Secondary, defence in depth, in the musb core. On a `set_mode` (or later) failure after
`musb_gadget_setup()`, call `musb_gadget_cleanup(musb)` before unwinding, so a failed
probe never leaves a gadget device registered on freed memory. Add a dedicated failure
label in the `MUSB_PERIPHERAL` and `MUSB_OTG` cases of `musb_init_controller()`
(`musb_core.c:2538-2555`) rather than calling it from `fail3` unconditionally, because
the HOST case never set a gadget up.

Both are MT8163-general, not Lidar-specific: they belong on the
`fix/general-fixes-from-lidar-port` topic of LibreEcho-Linux per
private/integration/integration.lock.json, and should be offered to the maintainer of
origin/feature/linux-6.18, since the primary defect is in their base. Nothing goes on
`feature/lidar-support`.

## How to verify on hardware

1. Build v0.2.42 from the integration tree with both patches.
2. Boot slot a (or any spare slot) and check dmesg: no "Does not support changing
   modes", no "probe with driver musb-hdrc failed", no "Runtime PM usage count underflow",
   and libreecho-init logs `configfs-udc-bound:musb-hdrc.3.auto`, as the known-good slot-a
   log did.
3. Confirm adb enumerates, then run `python3 tools/lab-build.py deploy` for the OTA and let
   the bootloader try slot b. Success criteria: three consecutive boots on b,
   `/data/libreecho/update/boot-health` shows `slot_b_success=1`, boot-history shows no
   rollback, and the pstore record is empty.

## What remains unproven

* No boot was performed here; the fix is not hardware-validated.
* The other 51 maintainer commits on origin/feature/linux-6.18 were not audited. This
  panic is explained, but the OTA could still fail later for another reason.
* The freed gadget memory happened to read `udc == NULL`; a different allocator state
  could yield a non-NULL dangling pointer and a different fault. The unwind bug is the
  invariant, the NULL is this instance.
* Whether mainline musb has since fixed the `fail3` unwind was not checked beyond the
  maintainer base commit af430c2; within this tree it is unchanged.
