# step25: Zigbee and Thread on the EFR32 radio, 2026-11-21

Status: **partial, firmware state changed**. The EFR32 now runs Amazon's Zigbee
NCP (`xncp-fw.gbl`, uploaded through the Gecko bootloader's own XMODEM path).
The OpenThread RCP GBL was still building when the run stopped; nothing from
that build was flashed.

## 1. Why `/dev/ttyS*` was absent

1. `/dev` is a plain initramfs directory: devtmpfs is not mounted there and
   mdev is unused. `libreecho-init` creates a fixed node list (`/init:106-136`)
   with no ttyS entries; the ports exist in `/sys/class/tty`.
2. `uart2` (`serial@11007000`) is `ttyS1`, not `ttyS2`: our 6.18 `8250_mtk.c`
   lacks the reference's `of_alias_get_id(np, "serial")` line assignment, so
   ports number by probe order (0x11006000=ttyS0, 0x11007000=ttyS1). `ttyS2/3`
   are unbacked `serial8250` stubs.

Workaround, no image change: `mount -t devtmpfs devtmpfs /run/devtmpfs`;
`/run/devtmpfs/ttyS1` is 4:65.

## 2. EFR32 UART and Gecko bootloader (hardware facts)

- Port: ttyS1, 115200 8N1, raw, no flow control. Bootloader banner:
  `Gecko Bootloader v1.0.0 / 1. upload gbl / 2. run / 3. ebl info` (log in
  `bootloader-probe.log`).
- `EFR32_SWCLK` (gpiochip0 line 1): low keeps the bootloader in its menu,
  high lets the application run.
- `EFR32_RESET_N` (gpiochip0 line 13) has **no pull-up**: releasing the line
  holds the chip in reset. Every reset must end by driving the line high.
- Built locally (static aarch64, pushed to `/run`): `efr32-gpio` (GPIO
  chardev v1 `list/set/pulse`), `lidar-xmodem` (reference
  `tools/lidar-xmodem.c`), `tcp-uart` (one-client TCP<->UART relay),
  `efr32-exchange.sh`, `ash-probe.sh`, `efr32-flash.sh`.

## 3. Stock firmware recorded before any write

Read-only from `mmcblk0p13` (PARTNAME=system_a) mounted at `/run/fireos`;
local copies in `local-firmware/` (not for commit or publication).

| file | size | sha256 | app type | app version |
|---|---|---|---|---|
| `system/vendor/firmware/silabs/xncp-fw.gbl` | 186480 | `1d9ed42f…d212406` | 0x1 (Zigbee NCP) | 0x36 |
| `system/vendor/firmware/dsr/zb_mux_rcp.gbl` | 145216 | `4e138f84…f61849` | 0x10 (RCP) | 0x01160000 |

The application found in flash answered neither an ASH reset (no RSTACK) nor
the ASCII menu, which fits the DSR dual-PAN image behind DSR's own
multiplexer (inference, not proven).

## 4. Zigbee NCP installed and answering

`efr32-flash.sh local-firmware/xncp-fw.gbl` (SWCLK low, RESET low then held
high, menu `1`, XMODEM, then SWCLK high and a reset) exited 0. Live probe:

```
RST (1A C0 38 BC 7E) -> 1A C1 02 0B 0A 52 7E    (ASH RSTACK, version 2,
                                                 reset code 0x0B, CRC okay)
```

ASH details confirmed against zigpy/bellows `ash.py`: CRC is
`binascii.crc_hqx(.., 0xFFFF)` sent big-endian, and a DATA payload is XORed
with the fixed ASH pseudo-random sequence. A randomized EZSP `version`
request (v4 and v5 encodings sent) was accepted (ACK, `frm=0, ack=1`), and the
NCP answered with a CRC-valid DATA frame both times. Its de-randomized
payload was `00 80 00 07 02 30 65`. The EZSP header split (1-byte vs 2-byte
frame control) and hence the exact stack version string were **not**
resolved; that is the next check (bellows against `tcp-uart` or a corrected
header split). Nothing beyond the ASH link level is claimed for Zigbee; no
network was formed and no device was paired (pairing needs the owner).

## 4a. Zigbee NCP verified over EZSP

The stock `xncp-fw.gbl` was re-flashed through the bootloader (rc=0), the
relay restarted and `bellows` (in `/tmp/bellows-venv`) driven by
`ezsp-probe.py` over `socket://127.0.0.1:16638` (adb forward). ASH negotiated
up from EZSP v4 to **protocol version 7**, stack type 2, **stack version
0x6530 = EmberZNet 6.5.3.0** (`ezsp-probe.log`, EUI64 redacted). After a
fresh network key and the standard well-known trust-center link key,
`initialize_network` returned OK and `formNetwork` came up as **coordinator**
(`getNetworkParameters`: status SUCCESS, node type COORDINATOR, panId 0x1a2b,
channel 15). A second run's `setInitialSecurityState`/`formNetwork` returned
INVALID_CALL because the network was already up; that is expected. The
network key was generated on the host and never logged.

Product firmware decision (reference `lidar-mainline` HEAD `0aa88f0`): the
`thread` service uploads our RCP and runs `otbr-agent`; the optional `zigbee`
service uploads Fire OS's NCP. Both are `extra 0` by default and "share the
one radio: with both enabled, neither starts". Therefore the chip runs **one
firmware at a time**, and the reference's primary design is the Thread RCP.
The chip was therefore switched back to our `lidar-ot-rcp.gbl` and Spinel
re-verified (`spinel-final.log`, same NCP_VERSION/protocol 4/CAPS).

## 5. Thread RCP built, flashed, and verified over Spinel

`build/fetch.sh` completed: Gecko SDK 4.4.3 at `d95099f`, ot-efr32 at
`089440d`, slc-cli 6.0.22 with its Python/JRE, Arm GNU 12.2.rel1. The sources
now live in `/var/tmp/efr32-moved` (symlinked as `/tmp/efr32`) because the
tmpfs filled up; nothing there is committed. `build/build-rcp.sh` replays the
reference build natively with `-DCMAKE_POLICY_VERSION_MINIMUM=3.5` (cmake 4.5)
and packs the GBL with `mkgbl.py`:

    /tmp/efr32/out/lidar-ot-rcp.gbl  113764 bytes  crc32 ok
    HEADER version 0x03000000
    APPLICATION type 0x00000010 version 0x00000001
    ERASEPROG base 0x0  image 113688 bytes
    text 113100 data 588 bss 17980

Main flashed it through the bootloader (`rcp-flash.log`, sha256 `5327b1d1…`,
"uploaded and started", rc=0) after the Echo rebooted into slot A for
VoiceStack's OTA. The RCP runs at **115200** (`SL_UARTDRV_USART_VCOM_BAUDRATE`
in `extension/lidar/config/sl_uartdrv_usart_vcom_config.h:42`).

Spinel verified through `tcp-uart` (device UART <-> TCP) + `adb forward
tcp:16638 tcp:6638` (the LAN path to 6638 is refused; only adb, 8080 and 5555
answer from the host, so the relay is reached over the adb forward):

    RESET(0x81 0x01) -> 80 06 00 70  (PROP_VALUE_IS LAST_STATUS = 112,
                                      STATUS_RESET_SOFTWARE)
    GET NCP_VERSION  -> 82 06 02 "OPENTHREAD/089440d-dirty; EFR32;
                                      Nov 21 2026 20:57:28"
    GET PROTOCOL_VER -> 83 06 01 04  (Spinel protocol version 4)
    GET CAPS         -> 84 06 05 05 0c 18 22 81 04  (5 capability bytes)
    GET INTERFACE    -> 85 06 03 03  (UART)

Frame check: header 0x80 flag, IID in bits 4-5, TID in bits 0-3; the command
is the byte after the header. HDLC-lite FCS is CRC-16/X-25 (reflected 0x8408,
init/xorout 0xFFFF), sent little-endian, with 0x7d escaping for 0x7e/0x7d/0x11
/0x13. Frames were validated by `crc-check.py`. The NCP_VERSION string carries
`-dirty` because the reference extension was copied into the SDK tree.

## 6. Thread network formation (attempted, not reached)

Built a host FTD (`ot-cli`, POSIX) from the same tree at `/var/tmp/ot-host`
(`cmake -DOT_PLATFORM=posix -DOT_APP_CLI=ON`, ninja target `ot-cli`, rc=0).
`run-thread.sh` bridges a host pty to the Echo UART (`ptytcp.py` over the adb
forward) and drives `ot-cli` with `dataset init new`, `dataset commit active`,
`ifconfig up`, `thread start`, polling `state`. `ot-cli` refused the pty with
`tiocmbic: Inappropriate ioctl for device`, so `ioctl-shim.so` (LD_PRELOAD)
swallows TIOCMBIC/TIOCMBIS/TIOCMSET.

Result before the Echo rebooted for VoiceStack's Wi-Fi fix:
`dataset init new` / `commit active` / `ifconfig up` / `thread start` all
answered `Done`, then three `state` polls returned `detached` in ~8 s. The
run was cut off by the reboot, so why the FTD stays detached (RCP radio
capability mismatch, channel/dataset or radio not enabled) is **not
determined**. After the reboot the RCP was restaged (devtmpfs, SWCLK high,
RESET pulse with the line held high, `tcp-uart` relay, adb forward) and
Spinel answers again with the same NCP_VERSION/PROTOCOL_VERSION/CAPS/IFACE
values shown in section 5.

## 7. `libreecho-radiod` is unrelated

`libreecho-radiod` (`LibreEcho-UI` `src/adapter/radiod.c`) is the
internet-radio player behind `radio.sock`; it does not touch the EFR32.

## 7. Board DTS flow control

`libreecho-lidar.dts:230-236` enables `uart2` with `uart-has-rtscts`; the
reference runs the EFR32 UART without flow control. The port works with
`stty -crtscts`; the DTS was not changed.

## 8. Not done

- Finish/verify the RCP GBL, upload it, verify Spinel (version, caps), then
  decide the final product firmware. The reference README describes `thread`
  as the service that uploads/uses the RCP and `zigbee` as the alternative
  that restores `xncp-fw.gbl`; which one its final image enables by default
  was not established here.
- Host Thread stack (`ot-daemon`/`otbr-agent`) on the Echo, network formation,
  `state`, `dataset active` (with the network key redacted).
- Image changes (ttyS nodes in `libreecho-init`, `8250_mtk` alias numbering)
  and a lab OTA bundle. No branch or bundle was created.
- Restore whichever stock firmware the final product uses through the
  bootloader; both stock GBLs are kept in `local-firmware/`.
