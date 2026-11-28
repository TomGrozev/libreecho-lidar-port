# Lidar Thread service, host work 2026-11-24

State: host work only. No device access. The RCP was already proven on hardware in
`private/lab/phase-06/hw-20261121/step25-efr32/` (`rcp-flash.log`,
`spinel-final.log`, `thread-form.log`).

Update, 2026-11-28: v0.2.68 packages the service. Its manifest has
`thread.enabled = true` with `libreecho-threadd.init`, `lidar-efr32` and a static
`otbr-agent`, `start_order = [lidar-efr32, otbr-agent]`, and status
`PREPARED_NOT_FLASHED`. This is image evidence only; none of the binaries has run on the
device. The work moved to the `feat/lidar-radio` topic. `ot-ctl` is built but not
staged, and `OTBR_REST` and border routing remain off, so Home Assistant cannot join a
network yet.

## What is in the trees

- Platform `tools/mt8163-arm32/efr32/lidar-efr32.c`: GPIO chardev control
  (`EFR32_SWCLK` line 1, `EFR32_RESET_N` line 13), Gecko bootloader menu,
  XMODEM-CRC GBL upload, Spinel NCP_VERSION exchange. It sets 115200 8N1 with
  `crtscts` off, matching the lab.
- Platform `tools/mt8163-arm32/otbr/SOURCE.lock`: ot-br-posix
  `thread-reference-20230119` at `22d4f4e488b4f59cd2541ee5b4bee69591053609`,
  BSD-3-Clause, armv7 hard-float, `OTBR_BORDER_AGENT=ON`, `OTBR_MDNS=avahi`,
  `OTBR_DBUS=OFF`, `OTBR_REST=OFF`. It also pins the four static dependencies:
  expat 2.6.4, libdaemon 0.14, dbus 1.14.10, avahi 0.8, each with a
  `source_sha256`.
- Platform `tools/mt8163-arm32/otbr/build_otbr_deps.sh`: builds that
  dependency set as static ARM32 (libexpat, libdaemon, libdbus-1,
  libavahi-common, libavahi-client) into a prefix, plus static `dbus-daemon`
  and `avahi-daemon`. It checks every archive against SOURCE.lock before
  unpacking and refuses a non-ARM32 archive or non-static daemon.
- Platform `tools/mt8163-arm32/otbr/build_otbr.sh`: builds `otbr-agent` and
  `ot-ctl` from that checkout with submodules and the armhf toolchain, linking
  against the `OTBR_DEPS` prefix and requiring `libavahi-client.a`,
  `libavahi-common.a` and `libdbus-1.a` there.
- Platform `tools/mt8163-arm32/initramfs/libreecho-threadd`: reads the `radio`
  string from `/data/libreecho/config/web-config.json` (thread|zigbee|none,
  default none), runs the RCP version check, uploads
  `/data/libreecho/firmware/lidar-ot-rcp.gbl` only when no OpenThread RCP
  answers, then starts the discovery stack and `otbr-agent`. It is staged to
  `/etc/init.d/libreecho-threadd.init` by `add_overlay`.
- Product `tools/radio_firmware.py` + `tools/test_radio_firmware.py`, called by
  `tools/check-release-components.py`: refuses `.gbl`/EFR32 binary suffixes,
  the Gecko GBL magic `eb17a603`, and EFR32/OpenThread firmware names.
- Linux 6.18: `uart2` no longer sets `uart-has-rtscts`; comment cites step25.

## Build, 2026-11-24

All paths below are under `private/artifacts/phase-07/thread/`. The compiler is
the phase-05 armhf toolchain through the wrappers in `build/bin`
(`arm-linux-gnueabihf-gcc` and `g++`, both carrying `--sysroot` and the host
runtime `LD_LIBRARY_PATH`).

```sh
cd private/artifacts/phase-07/thread
OTBR_DEPS_ARCHIVES=$PWD/sources \
ARM_CC=$PWD/build/bin/arm-linux-gnueabihf-gcc \
ARM_CXX=$PWD/build/bin/arm-linux-gnueabihf-g++ \
  sh tools/mt8163-arm32/otbr/build_otbr_deps.sh $PWD/deps
OT_BR_SRC=$PWD/otbr-src OTBR_DEPS=$PWD/deps \
ARM_CC=$PWD/build/bin/arm-linux-gnueabihf-gcc \
ARM_CXX=$PWD/build/bin/arm-linux-gnueabihf-g++ \
  sh tools/mt8163-arm32/otbr/build_otbr.sh $PWD/otbr-build
```

The dependency step runs first: dbus 1.14.10 and avahi 0.8 (with expat 2.6.4
and libdaemon 0.14) build only after their source hashes match SOURCE.lock,
and the two daemons are linked with libtool `-all-static` at `make` time.
The otbr step then configures with `OTBR_BORDER_AGENT=ON`,
`OTBR_MDNS=avahi`, `OTBR_DBUS=OFF` and `OTBR_REST=OFF`, and links the
publisher stack from the `OTBR_DEPS` prefix.

Artifacts and hashes (all `ELF 32-bit LSB executable, ARM, EABI5 ...,
statically linked`):

| Artifact | Bytes | sha256 |
|---|---|---|
| `otbr-build/src/agent/otbr-agent` | 3507656 | `95ebc60f2d14cc35e4288a974f9e53ba18c83e1ae9fce4da4f17e247b3403172` |
| `otbr-build/third_party/openthread/repo/src/posix/ot-ctl` | 454116 | `f7200861614245c0c8c072e10fe8b45c0e56c0abb904c6026f10c949a02c0042` |
| `deps/bin/dbus-daemon` | 1651536 | `2072683a3ff199ae3ed399872a76e49864cc32e9270e33ff126a72d64d456de1` |
| `deps/sbin/avahi-daemon` | 2939772 | `deb43afbc37581c5c1fda040b0ae563ba354d32b5dbbacd42543355a594529db` |

`CMakeCache.txt` in `otbr-build` records `OTBR_REST:BOOL=OFF`,
`OTBR_DBUS:BOOL=OFF`, `OTBR_MDNS:STRING=avahi` and
`OTBR_BORDER_AGENT:BOOL=ON`. `strings otbr-agent` shows
`otbr::BorderAgent::PublishMeshCopService` and `otbr::Mdns::PublisherAvahi`.
Because REST is off, Home Assistant's OTBR/Thread integration, which drives
the REST API for Matter-over-Thread commissioning, cannot use this build; the
border agent is reachable only through mDNS/SRP by a commissioner that does
not need REST.

## Start order and invocation

`libreecho-threadd` now starts `dbus-daemon` (system bus at
`/run/dbus/system_bus_socket`, from `/etc/dbus-1/system.conf`), waits for the
socket, starts `avahi-daemon` (from `/etc/avahi/avahi-daemon.conf`,
`enable-wide-area=no`), and only then starts `otbr-agent`; stop runs in
reverse. The agent invocation is:

```sh
otbr-agent -I wpan0 -B wlan0 spinel+hdlc+uart:///dev/ttyS2?uart-baudrate=115200 -d 5
```

The previous invocation passed the Spinel URL to `-B`. In ot-br-posix `-B`
is the Wi-Fi backbone interface and the radio URL is positional, so the old
form gave the agent a URL where it expected an interface and no radio at all.

## Verified on the host

- `make ARCH=arm64 mediatek/libreecho-lidar.dtb` -> 24004-byte DTB.
- `python3 -B tools/test_radio_firmware.py` -> 5 tests OK.
- `python3 tools/check-release-components.py --release-scope
  commercially-unrestricted` -> component gate passes, radio gate passes.
- `lidar-efr32.c` compiles host (`gcc -Wall -Wextra -Werror`) and cross-links
  static ARM32 hard-float with the phase-05 toolchain.
- `sh -n` on `libreecho-threadd`, `bash -n` on `build_otbr.sh` and
  `build_otbr_deps.sh` all pass.
- UI `web/js/app.js` parses (`node --check`). Its Thread option now reads
  "Thread (OpenThread border router)" instead of "Thread (Matter and
  OpenThread border router)"; the radio note no longer claims a Matter
  interruption. No UI test covers this panel (`git grep` finds no test that
  asserts the label), so the change was checked by parsing only. Commit
  `96db763` in the UI fork (the branch cleanup rewrote it from `947841ea9`).

## Not verified / gaps

- The four binaries above build and carry the hashes in the table. None was
  executed (no QEMU/user-mode run yet): arm32 execution needs
  `qemu-arm-static`, which this host lacks.
- Image wiring is implemented in the MT8167 builder (`--lidar-efr32`,
  `--otbr-agent`, `--dbus-daemon`, `--avahi-daemon`, all-or-nothing,
  Lidar-only, `/usr/local/sbin`, manifest `start_order` and config records,
  GBL refused). `LIDAR_DTC=.../scripts/dtc/dtc python3 -m unittest
  test_recovery_image_tools` ran 31 tests from `tools/mt8167-arm64`: 20 pass,
  11 fail on the missing host `busybox`/`qemu-arm-static` used by the
  verifier's target-parser probe. The same 31 tests give the same 7 failures
  and 4 errors at HEAD `7011650f9` without these changes, so the failures are
  environmental. Both radio staging tests pass.
- The radio setting now has a web field: `GET/PUT /api/v1/radio`, persisted as
  `radio` in `web-config.json` and carried by config import/export. The Device
  page shows the selector only when the endpoint answers, i.e. only on Lidar.
  `build/test-config-import-linux` passes, including reject-bogus and
  persist-thread cases; the page itself was not opened in a browser.
- Nothing ran on the Echo.

## On-device steps still needed

1. Run the built static `otbr-agent`, `ot-ctl`, `dbus-daemon`,
   `avahi-daemon` and `lidar-efr32` under QEMU or on the device; then pass
   all four image paths to the MT8167 builder and record the image manifest
   hashes.
2. Put my local RCP GBL at `/data/libreecho/firmware/lidar-ot-rcp.gbl`
   (never in the image), mode 0600.
3. Pick `Thread` in the Device page radio selector (or `PUT /api/v1/radio`
   with `{"radio":"thread"}`) and run
   `/etc/init.d/libreecho-threadd.init start`.
4. Confirm the start order: the D-Bus socket appears, `avahi-daemon` runs,
   then `otbr-agent`.
5. Confirm `lidar-efr32 version` returns the OpenThread NCP_VERSION, that a
   second start skips the upload, and that deleting the GBL leaves the agent
   down with a logged reason.
6. Confirm `otbr-agent` answers `ot-ctl state` on the device and that the
   border agent's `_meshcop._udp` service is visible to an mDNS browser.
   Home Assistant's OTBR integration cannot be used: this build has
   `OTBR_REST=OFF` (`otbr-build/CMakeCache.txt`), so Matter commissioning via
   Home Assistant is unverified and unsupported until a REST build exists.
7. Switch to `zigbee` and confirm the Thread service stays down and leaves the
   radio untouched.

None of these device steps has been run.
