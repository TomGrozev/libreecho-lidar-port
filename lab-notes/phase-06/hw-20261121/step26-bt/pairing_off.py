#!/usr/bin/env python3
"""Turn pairing mode off when btd's restore step is rejected.

btd restores the saved discoverable flag before connectable
(src/adapter/btd.c:2039-2046); the kernel rejects SET_DISCOVERABLE while
page scan is off. Enable connectable first, then pairing mode off, then
clear discoverable. Leaves the unit connectable so the bonded phone can
reconnect. Needs `adb forward tcp:19999 localfilesystem:/run/libreecho/bluetooth.sock`.
"""
import json
import socket
import time


def btd(cmd, args=None):
    s = socket.create_connection(("127.0.0.1", 19999), timeout=10)
    s.sendall((json.dumps({"v": 1, "id": 1, "cmd": cmd,
                           "args": args or {}}) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(65536)
        if not chunk:
            break
        buf += chunk
    s.close()
    return buf.decode().strip()


def state():
    data = json.loads(btd("status"))["data"]
    caps = data["capabilities"]
    return {"pairing_mode": data["pairing_mode"], "last_error": data["last_error"],
            **{k: caps[k] for k in ("connectable", "discoverable", "bondable")}}


print("before", json.dumps(state()))
print("set_connectable", btd("set_connectable", {"enabled": True}))
print("pairing_mode_off", btd("pairing_mode", {"enabled": False}))
print("set_discoverable_off", btd("set_discoverable", {"enabled": False}))
time.sleep(2)
print("after", json.dumps(state()))
