# adb over USB: root-cause fixes (2026-11-19)

Work is on local branches. Nothing is committed, pushed, flashed, or run on
hardware. No adb, fastboot, or device access was used.

## Base commits and branches

| Tree | Base commit | Branch |
|---|---|---|
| `repos/LibreEcho-Linux` | `7594c5780db2ff3bc35083223c93d7926ebb4124` | `experiment/lidar-musb-rx-kick` |
| `repos/LibreEcho-Platform` | `e917f8f9502509fae26812b5e362c0a3eba1ec7a` | `experiment/lidar-adb-stability` |
| UI source checkout `artifacts/phase-05/toolchains/sources/libreecho-ui` | `b39af308f0d32e5ae56986d4c603195ab524dbc4` | `experiment/lidar-startup-readiness` |

UI source state on the branch hashes to
`65bd8d8bfeab255db372a5b7878013aab80c0df29dde12427b9c7bc387e5391c`
(`git diff --binary HEAD` over the two changed files, no untracked files). That
value is now `UI_DIFF_SHA256` in `experiments/phase-05/build_images.sh`.

## 1. MUSB rx_kick backport

Patch: `[PATCH v2] usb: musb: gadget: don't flush a waiting RX packet when
queueing a request`, Elvira Khabirova, 2026-11-07, Message-Id
`20261107105505.6554-1-lineprinter0@gmail.com`,
<https://lkml.indiana.edu/2611.0/21280.html> (lore is Anubis-blocked from this
host). Upstream delta: `musb_core.c` +3, `musb_gadget.c` +107,
`musb_gadget.h` +9.

Review against the upstream diff (file:line in the 6.1.178 tree):

- `musb_gadget.h:14` adds `<linux/workqueue.h>`; `:27-28` prototypes and
  `:49-50` no-gadget stubs for the suspend helpers; `:102-103`
  `struct work_struct rx_kick` and `bool rx_kick_deferred` in `struct musb_ep`.
  Matches upstream hunks.
- `musb_core.h:370` `bool rx_kicks_disabled`, set only across system suspend
  (see the substitution below).
- `musb_gadget.c:151-155` giveback re-queues a deferred kick and drops the PM
  ref on `queue_work` failure; `:158-165` `musb_g_defer_rx_kick()` takes
  `pm_runtime_get_noresume` before setting the flag, exactly as upstream.
- `musb_gadget.c:834-841` defers a non-DMA `musb_g_rx()` while `ep->busy`;
  `:1319-1331` defers an RX request queued behind a running giveback.
- `musb_gadget.c:1210-1218` `musb_ep_restart()` RX branch: if `RXPKTRDY` is set
  it queues `rx_kick` instead of `FLUSHFIFO`. This is the data-loss fix.
- `musb_gadget.c:1222-1247` worker takes `musb->lock`, bails before any MMIO
  when `desc`, `is_runtime_suspended`, or `rx_kicks_disabled` indicate it must
  not run, defers when `busy`, re-reads `RXCSR`, and calls `musb_g_rx()`.
- `musb_gadget.c:1138-1145` `musb_gadget_disable()`: `nuke()`, then
  `cancel_work()` (non-sync) and deferred-flag clear, each releasing the PM ref.
  `cancel_work_sync()` would deadlock: the caller holds `musb->lock`, which the
  running worker needs. Upstream uses the same non-sync call. The ordering is
  safe because `nuke()` runs first, so no new kick can be queued behind the
  cancel while the endpoint still has requests.
- `musb_gadget.c:1783` `INIT_WORK` in `init_peripheral_ep()`;
  `:1886-1912` cleanup/suspend helpers. Called from `musb_gadget_cleanup()`
  and `musb_suspend()`, both without `musb->lock` held, which is what makes the
  synchronous cancel legal there.
- `musb_core.c:2831` disable in `musb_suspend()` before `DEVCTL` is cleared;
  `musb_core.c:2881` enable in `musb_resume()` after `musb_restore_context()`.

6.1 substitutions, both documented in code comments and in the previous
hand-off:

1. `system_bh_wq` (6.9 BH workqueues) -> `system_wq`. The worker still runs in
   process context and takes `musb->lock` with `spin_lock_irqsave`, so the
   lockup that `3fc137386c46` guarded against cannot recur.
2. `disable_work_sync()` / `enable_work()` -> `cancel_work_sync()` plus
   `musb->rx_kicks_disabled`. `cancel_work_sync()` cannot prevent a later
   `queue_work()` during suspend, so the flag makes such a worker exit before
   touching MMIO and release its own PM reference. Resume clears the flag and
   re-queues a deferred kick (upstream's `enable_work()` only re-enables; the
   re-queue here also closes the window where a kick deferred across suspend is
   never run again).

PM-ref accounting matches upstream: `get_noresume` at queue/defer, released by
`put_noidle` when `queue_work` fails, by the worker's final
`put_autosuspend`, by the deferred-flag clear, or by `cancel_work()`
returning true.

Build (Phase 5 path, host clang 23.1.5, LLVM=1, 12 jobs), run from the
workspace root:

```sh
export KBUILD_BUILD_USER=libreecho KBUILD_BUILD_HOST=phase5 \
       KBUILD_BUILD_TIMESTAMP="2026-11-17 00:00:00 UTC"
make -C repos/LibreEcho-Linux O=/tmp/lidar-p5-kbuild ARCH=arm64 LLVM=1 mt8167_arm64_defconfig
make -C repos/LibreEcho-Linux O=/tmp/lidar-p5-kbuild ARCH=arm64 LLVM=1 olddefconfig
make -C repos/LibreEcho-Linux O=/tmp/lidar-p5-kbuild ARCH=arm64 LLVM=1 Image dtbs -j12
```

Result: exit 0, no warnings in the musb files. The patch is compiled in:
`System.map` has `musb_gadget_disable_rx_kicks`,
`musb_gadget_enable_rx_kicks` and `musb_g_rx_kick`, and `.config` has
`CONFIG_USB_MUSB_DUAL_ROLE=y` and `CONFIG_USB_MUSB_MEDIATEK=y`.

Outputs copied to `artifacts/phase-05/kernel/` (`Image`, 10,854,912 bytes,
sha256 `f8992cc409d0df14e8d0275df33721775d8b4adf5f50cab2f1e3b2b1e3c0affd`;
`libreecho-lidar.dtb` 19,314 bytes, sha256
`eb8444d8c4b7e9b62145b3baf62c392ff8c5f77b5b83179e7d93e04fdf29f4bf`), with
`SHA256SUMS` regenerated. No compile error needed fixing in the backport.

## 2. libreecho-init

`repos/LibreEcho-Platform/tools/mt8163-arm32/initramfs/libreecho-init`:

- `:130-132` adds `ensure_chr /dev/kmsg 1 11` to the device-node list, with a
  comment naming the consequence of a missing node (every `log()` and adbd
  diagnostic line is lost).
- `:788-791` mounts FunctionFS with `...,no_disconnect`, so the last close of
  `ffs.adb` no longer clears the UDC and drops D+.
- `:841-862` starts a detached supervisor after the first UDC bind. Every
  second it tests the devlog.sh REBIND condition: `$G/UDC` empty, `adbd` still
  alive, both `/dev/usb-ffs/adb/ep1` and `ep2` present. It then writes the
  same UDC back and logs `udc-rebound:<udc>` or `udc-rebind-failed:<udc>`;
  it exits with `udc-rebind-supervisor-exit` when adbd goes away. This is the
  Android-init `sys.usb.ffs.ready` behaviour, needed for a host reset that
  still clears the UDC.

The script hash pin changed; both consumers were updated:

- `build_recovery_image.py:64` `RECOVERY_INIT_SHA256`
- `verify_recovery_image.py:61` `INIT_SHA256`

both now `d5a605be5ecae0068bc69e053f1500d65a9c2e8f328c9fd743abae6b6f9b71c1`.

Test added in `tools/mt8163-arm32/test_recovery_image_tools.py`:
`test_adb_transport_survives_ffs_close_with_detached_udc_rebind` checks the
kmsg node precedes `log()`, the `no_disconnect` mount, the supervisor's
position after the bind, that it is a background job, and that the rebind
write, the two endpoint tests, the 1 s poll and both log markers are inside
it. `test_linux61_adb_uses_configfs_functionfs_before_binding_udc` now expects
the `no_disconnect` mount string.

## 3. libreecho-web.init readiness

`artifacts/phase-05/toolchains/sources/libreecho-ui/init/libreecho-web.init`:

- `:184-208` `startup_services_ready()` no longer waits for the voice stack
  unconditionally. It scans `sttd`/`ttsd`/`agentd` pidfiles; if none is a live
  process (`voice_running=0`), the whole voice gate is skipped and the previous
  fallback (`esphome_service_ready`) runs. When one runs, all three live
  pidfiles and the `stt`/`tts`/`agent` sockets are required, as before.
- `:219-235` `mark_startup_ready()` replaces the 10 Hz `sleep 0.1` / reset
  counter with a doubling delay from 1 s, capped at
  `STARTUP_READY_MAX_DELAY` (default 30 s, replacing
  `STARTUP_READY_TIMEOUT_TICKS`). A probe that never succeeds now costs one
  shell every 30 s instead of one every 0.1 s.

Platform side: `build_recovery_image.py` `validate_ui_startup_contract()`
markers and ordered list now require `STARTUP_READY_MAX_DELAY`, `delay=1`,
`sleep "$delay"`, the doubling step and the cap, plus the new
`voice_running=0` / `if [ "$voice_running" -eq 1 ]` condition. The same test
file's `valid_web` fixture and its one-shot and syntax mutations were updated.
The UI test `tests/test_bluetooth_startup_readiness_contract.sh` asserts the
new variable instead of the tick counter.

## 4. Image

`experiments/phase-05/build_images.sh` rebuilt all three images because the
script has no single-image switch; the UI bundle was rebuilt first with
`experiments/phase-05/build_components.sh ui` (new UI manifest sha256
`b888e70cda597f9a43bd3361c177f8142f7fc0ca43f15edcd0e5e727e719132d`). Build and
verify exited 0.

v1 image: `artifacts/phase-05/images/boot-lidar-v1.img`

| field | value |
|---|---|
| sha256 | `9d7645a081fad17171f8458d158e3c170106367aeda641a94d55f409eaf85e27` |
| file size | 16,777,216 bytes (one full 16 MiB slot) |
| xz ramdisk | 5,387,360 bytes |
| gzip kernel | 4,603,904 bytes |
| DTB collection | 1,024,374 bytes |
| margin to 16 MiB | 5,756,928 bytes |

The verifier printed:

```
lidar_recovery_image_contract=PASS android_v0=yes mtk_wrapper=yes arm64_kernel=yes lidar_dtb=yes
initramfs_arm32=yes image_profile=ota service_profile=production feature_policy=preserve
ota=yes gzip_kernel_bytes=4603904 dtb_collection_bytes=1024374 ramdisk_bytes=5387360
margin_to_16mib_bytes=5756928 status=PREPARED_NOT_FLASHED
```

The dev and v2 images were rebuilt from the same inputs (`ad14a6c4…`,
`f4b80766…`) and also verified `PASS`. The OTA lab bundles in
`artifacts/phase-05/ota/` still embed the previous v1/v2 images and were not
regenerated.

## Tests run (host only)

- `sh -n` on both init scripts: ok.
- `python3 -m unittest test_recovery_image_tools test_userdata_geometry test_recovery_ap`
  from `repos/LibreEcho-Platform/tools/mt8163-arm32`: 336 tests, 15 failures and
  6 errors, all environmental and present before these edits:
  `ModuleNotFoundError: No module named 'nacl'` (6 OTA tests),
  `busybox: command not found` (fetch-quarantine test), and
  `unavailable: no-phy:wlan0` (14 `test_recovery_ap` readiness tests on a host
  with no wireless PHY). No pin, startup-contract, or adb test fails.
- `python3 -m unittest test_recovery_image_tools -k startup -k ui_bundle`: 10
  tests, ok (2 skipped).
- `python3 -m unittest test_recovery_image_tools -k functionfs -k rebind -k adb`:
  7 tests, ok (1 skipped).
- UI source: `sh tests/test_bluetooth_startup_readiness_contract.sh` ok.
  `python3 tests/test_esphome_health.py` timed out (>300 s) while building its
  C fixture, so its result is unverified. `sh tests/test_startup_animation.sh`
  passes its `libreecho-web.init` contract greps and then fails with
  `./build/libreecho-ledd: cannot execute binary file: Exec format error`,
  because the ARM32 daemon is run on this x86 host.

## Unverified

- No hardware run: the rx_kick fix, `no_disconnect`, the rebind supervisor and
  the backoff loop are untested on the device. The image is
  `PREPARED_NOT_FLASHED`.
- The 30 s backoff means a late-starting payload is noticed up to 30 s after
  it appears; that delay is a design choice, not a measurement.
- OTA lab bundles were not rebuilt; their embedded image hashes are stale.
- `test_fetch_quarantine_survives_current_and_prior_cleanup`, the six
  `nacl`-dependent OTA tests and the 14 `test_recovery_ap` readiness tests fail
  on this host for missing `busybox`, `PyNaCl` and a wireless PHY; they are not
  caused by these changes.
