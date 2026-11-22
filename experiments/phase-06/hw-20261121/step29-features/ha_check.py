#!/usr/bin/env python3
"""Home Assistant ESPHome mode check on the Lidar device (step29).

Enables HA mode through the owner API, verifies libreecho-esphomed listens on
6053, and performs an ESPHome native API Noise handshake + device_info from the
host.  Never prints the Noise key.  Leaves HA mode enabled; the caller restores
the previous mode afterwards.
"""
import asyncio
import json
import socket
import sys
import time

import leclient

DEVICE = "<DEVICE_IP_A>"


def log(label, obj):
    print("== %s %s" % (label, json.dumps(obj, separators=(",", ":"))))
    sys.stdout.flush()


def tcp_probe(host, port, timeout=3):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port))
    finally:
        s.close()


def main():
    token, csrf = leclient.login()
    st, body = leclient.call("GET", "/voice-pipeline", token=token)
    prior = (body.get("data") or {}).get("mode")
    log("voice-before", {"status": st, "mode": prior,
                         "ha": (body.get("data") or {}).get("home_assistant")})
    st, body = leclient.call("GET", "/integrations", token=token)
    log("integrations-before", {"status": st, "ids": [
        {"id": i.get("id"), "enabled": i.get("enabled")}
        for i in (body.get("data") or {}).get("integrations", [])]})

    st, body = leclient.call("PUT", "/voice-pipeline", {"mode": "home-assistant"},
                             token=token, csrf=csrf)
    log("enable-ha", {"status": st, "restart": (body.get("data") or {}).get("restart"),
                      "error": body.get("error")})
    ready = False
    for _ in range(40):
        time.sleep(1)
        st, body = leclient.call("GET", "/voice-pipeline", token=token)
        d = body.get("data") or {}
        rs = d.get("restart") or {}
        if rs.get("state") in ("ready", "failed"):
            log("voice-after", {"status": st, "mode": d.get("mode"), "restart": rs,
                                "ha": d.get("home_assistant")})
            ready = rs.get("state") == "ready"
            break
    if not ready:
        log("voice-timeout", {"last": body})

    st, body = leclient.call("GET", "/home-assistant", token=token)
    d = body.get("data") or {}
    key = d.get("encryption_key") or ""
    log("ha-details", {"status": st, "url": d.get("url"),
                       "key_present": bool(key), "key_len": len(key)})
    log("tcp6053-lan", {"connect_ex": tcp_probe(DEVICE, 6053)})
    log("tcp6053-forward", {"connect_ex": tcp_probe("127.0.0.1", 16053)})

    if key:
        host, port = ("127.0.0.1", 16053) if tcp_probe("127.0.0.1", 16053) == 0 else (DEVICE, 6053)
        try:
            from aioesphomeapi import APIClient
        except ImportError:
            log("aio-client", {"available": False})
            return
        asyncio.run(handshake(host, port, key))


async def handshake(host, port, key):
    import base64
    client = APIClient(host, port, noise_psk=key, client_info="libreecho-step29",
                       provide_time=False)
    try:
        await asyncio.wait_for(client.connect(login=True), 10)
        info = await asyncio.wait_for(client.device_info(), 10)
        log("aio-connect", {"ok": True, "host": host, "port": port,
                            "name": info.name, "mac": info.mac_address,
                            "model": getattr(info, "model", ""),
                            "esphome_version": getattr(info, "esphome_version", ""),
                            "voice_feature_flags": getattr(info, "voice_assistant_feature_flags", None),
                            "api_version": "%d.%d" % (client.api_version.major, client.api_version.minor),
                            "encryption_provisionable": getattr(info, "api_encryption_provisionable", None)})
        entities, services = await asyncio.wait_for(client.list_entities_services(), 10)
        log("aio-entities", {"count": len(entities),
                             "kinds": sorted({type(e).__name__ for e in entities}),
                             "services": len(services)})
        await client.disconnect()
    except Exception as e:  # noqa: BLE001
        log("aio-connect", {"ok": False, "error": repr(e)})
    finally:
        try:
            await client.disconnect(force=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
