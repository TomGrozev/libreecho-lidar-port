# TSL2540 remove()/boot state fix (AlsFix)

Repos and bases: `repos/LibreEcho-Linux-618` branch `fix/lidar-port-identity`
HEAD `8985a44d45a8`; `repos/LibreEcho-UI` branch `fix/lidar-port-identity`
HEAD `27a4363`. Nothing was built into or run on a device: the unit is wedged
until I power-cycle it. Inputs: `experiments/phase-06/hw-20261121/step34-fixes/api-recheck.md`
and `KernelFixes.md`.

## 1. remove() now unwinds probe (`ams_tsl2540.c:924-975`)

Probe registers, in order: platform init/power, the chip, `tsl2540_attr_group`
(`ABI_SET_GET_REGISTERS`), `tsl2540_als_attr_group`, the optional IRQ, the
optional input devices, then `tsl2540_setup()` enables ALS when `boot-on`.
`remove()` used to unregister only `p_idev`, run `platform_teardown`, and free
the chip. It now, in reverse order:

1. `free_irq` (same `TSL2540_ENABLE_INTERRUPT` guard as the request),
2. `sysfs_remove_group(tsl2540_als_attr_group)` and, under
   `ABI_SET_GET_REGISTERS`, `sysfs_remove_group(tsl2540_attr_group)`. These go
   first because they block until in-flight callbacks finish and stop new ones;
   every callback dereferences `chip` from drvdata,
3. `input_unregister_device` for `d_idev`, `a_idev`, `p_idev` under the same
   `#ifdef`s as their registration,
4. `tsl2540_configure_als_mode(chip, 0)` under `chip->lock` when ALS is on, and
   `platform_power(POWER_OFF)` outside the lock, unwinding `tsl2540_setup()` and
   the probe power-on,
5. `platform_teardown`, `i2c_set_clientdata(NULL)`, free `pdata` only when the
   probe allocated it (`chip->pdata != client->dev.platform_data`), free `chip`.

The pdata guard also removes a latent double free / free-of-board-data on the
non-DT path. devm conversion was not used: the failed registration paths and
the chip/pdata lifetime are already explicit, and `devm_device_add_group` would
not change this unwind order. No new struct fields were needed.

`TSL2540_ENABLE_INPUT` and `TSL2540_ENABLE_INTERRUPT` are defined nowhere in
this tree (`grep` over the repo: only the two driver source files mention them),
so this build registers no `a_idev`/`d_idev` and no IRQ. The step 34 incident
attributed the unbind fallout to an input device too; the actual live
registrations are the two sysfs groups, which matches the observed `-EEXIST`
from `sysfs_create_group` and the UAF in `tsl2540_als_enable_show`. The guarded
input unregisters keep the code correct if those macros are ever enabled.

## Shutdown path

The driver has no `.shutdown`; `i2c_device_shutdown()` only calls
`driver->shutdown` when present (`drivers/i2c/i2c-core-base.c:647-656`), and
`device_shutdown()` calls neither suspend nor the PM ops. The only PM callbacks
are `tsl2540_suspend/resume`, and `tsl2540_resume()` returns before its body
(dead code, left untouched). On a clean boot the driver therefore cannot enter
or block `device_shutdown`: the step 34 reboot hung after the bad unbind had
freed `chip` while live sysfs still pointed at it, and the resulting oops left
the block I/O backed `/data` path stuck (three D-state tasks); that hang is a
consequence of the UAF, not of a driver shutdown callback. With the fixed
remove() the unbind no longer leaves freed memory reachable, so the trigger is
gone; no shutdown hook is needed or added.

## 2. Boot with ALS on: DT `boot-on` (`libreecho-lidar.dts:522`)

Root cause: `tsl2540_setup()` enables ALS only when `pdata->boot_on`, which
`tsl2540_init_dt()` reads from the node's `boot-on` property, and the node did
not have it. So `als_power_state` read 0, ADC channels read 0, and `GET /light`
reported `lux=0 powered:false`.

Fixed at the source with the driver's existing DT knob: `boot-on;` in the
`light-sensor@39` node. Probe then leaves `ENABLE` with `PON|AEN|WEN` set and
`chip->als_enabled` true, which is what `als_power_state` reports. The UI needs
no change: `repos/LibreEcho-UI/src/backend_linux.c:735-833` only reads
`als_lux`, `als_calibrated_lux`, `als_ch0/1`, `als_gain`, `als_power_state`,
`als_itime` and never writes; no host tests were touched. The only node with
this compatible is `libreecho-lidar.dts`, and the property is per-node, so
MT8163 is unaffected (`mt8163-*` power-domain tables untouched as well).

## 3. Build

```
cd repos/LibreEcho-Linux-618
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=phase6 \
  KBUILD_BUILD_TIMESTAMP="2026-11-21 00:00:00 UTC"
make -s O=/tmp/lidar-618-als ARCH=arm64 LLVM=1 mt8167_arm64_defconfig   # exit 0
make -s O=/tmp/lidar-618-als ARCH=arm64 LLVM=1 -j16 Image \
  mediatek/libreecho-lidar.dtb                                          # exit 0
```

Logs `/tmp/als-defconfig.log`, `/tmp/als-build.log` (3056 lines; warnings only
from `mt7668/common/wlan_lib.c`, none mention the driver or the DTS). A second
incremental `make` after the final edit exited 0 with no output; the driver
object (09:15:34) is newer than `ams_tsl2540.c` (09:13:18) and the `Image`
(09:15:51) was relinked from it. `dtc` from the build tree decoded the DTB with
exit 0 and no warnings; the decoded DTS has `boot-on;` in `light-sensor@39`.

Artifacts `artifacts/phase-07-prep/kernel-als/{Image,libreecho-lidar.dtb,config,SHA256SUMS}`:

```
53417fd7390f2b7ec9c6fd5073674b3528d50ea0b13efa15c4bb17cf1af1ccf6  Image              13,818,368 bytes
fe0fc1391396c895e15d3029ecd383712f63922ed06276ebc800a6e2279be68e  libreecho-lidar.dtb  23,326 bytes
26ffe02e85fe0f051970103b5a1410ee6e90f8b48a7e325eed8f7f9d1147912f  config
```

Not verified (host only, device unavailable): `als_power_state` = 1 on boot,
nonzero `als_lux`/`GET /light`, the unbind -> rebind cycle (`-EEXIST` gone, no
oops on `als_power_state` read after unbind), and boot/reboot with this image.
`tsl2540_resume()`'s dead early `return 0` is left in place, out of scope.
