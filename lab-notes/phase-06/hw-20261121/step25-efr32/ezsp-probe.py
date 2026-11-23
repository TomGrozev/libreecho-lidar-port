#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""ezsp-probe: talk EZSP to the EFR32 NCP through the pty/TCP relay.

Usage: ezsp-probe.py <host> <port>
Prints the EZSP and stack versions, then initializes and forms a fresh
network, and reports the NCP network parameters (no keys are printed).
"""
import asyncio
import logging
import sys

from bellows.ezsp import EZSP

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")


async def main(host: str, port: int) -> None:
    from bellows import types as t

    ezsp = EZSP(
        {
            "path": f"socket://{host}:{port}",
            "baudrate": 115200,
            "flow_control": None,
        }
    )
    await ezsp.connect()
    try:
        await ezsp.version()
        print(f"ezsp_protocol={ezsp.ezsp_version}")
        eui64 = await ezsp.getEui64()
        print(f"eui64={eui64!r}")

        try:
            await ezsp.leaveNetwork(timeout=10)
            print("leave(before)=done")
        except Exception as exc:  # no network up, or nothing to leave
            print(f"leave(before)={type(exc).__name__}: {exc}")

        nstat, ntype, nparams = await ezsp.getNetworkParameters()
        print(
            f"before status={nstat!r} node_type={ntype!r} "
            f"panId=0x{nparams.panId:04x} channel={nparams.radioChannel}"
        )
        if ntype == t.EmberNodeType.COORDINATOR and nstat == t.EmberStatus.NETWORK_UP:
            print("already formed; skipping")
            return

        status = await ezsp.initialize_network()
        print(f"networkInit={status!r}")

        from bellows import types as t

        import os

        isc = t.EmberInitialSecurityState()
        isc.bitmask = (
            t.EmberInitialSecurityBitmask.HAVE_PRECONFIGURED_KEY
            | t.EmberInitialSecurityBitmask.REQUIRE_ENCRYPTED_KEY
            | t.EmberInitialSecurityBitmask.TRUST_CENTER_GLOBAL_LINK_KEY
            | t.EmberInitialSecurityBitmask.HAVE_NETWORK_KEY
            | t.EmberInitialSecurityBitmask.NO_FRAME_COUNTER_RESET
        )
        # Network key is generated here and never printed; the standard
        # well-known trust-center link key is public (ZigBeeAlliance09).
        isc.networkKey = t.KeyData(os.urandom(16))
        isc.networkKeySequenceNumber = t.uint8_t(0)
        isc.preconfiguredKey = t.KeyData(b"ZigBeeAlliance09")
        isc.preconfiguredTrustCenterEui64 = t.EUI64.convert(
            "00:00:00:00:00:00:00:00"
        )
        status, = await ezsp.setInitialSecurityState(state=isc)
        print(f"setInitialSecurityState={status!r}")

        params = t.EmberNetworkParameters(
            extendedPanId=t.ExtendedPanId.convert("11:22:33:44:55:66:77:88"),
            panId=t.EmberPanId(0x1A2B),
            radioTxPower=t.uint8_t(8),
            radioChannel=t.uint8_t(15),
            joinMethod=t.EmberJoinMethod.USE_MAC_ASSOCIATION,
            nwkManagerId=t.EmberNodeId(0),
            nwkUpdateId=t.uint8_t(0),
            channels=t.Channels(0x07FFF800),
        )
        await ezsp.formNetwork(params)
        print("formNetwork=NETWORK_UP")

        status, node_type, params = await ezsp.getNetworkParameters()
        print(
            f"ncp status={status!r} node_type={node_type!r} "
            f"panId=0x{params.panId:04x} channel={params.radioChannel} "
            f"extPanId={params.extendedPanId}"
        )
    finally:
        await ezsp.disconnect()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
