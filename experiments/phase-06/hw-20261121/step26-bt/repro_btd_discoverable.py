#!/usr/bin/env python3
"""Reproduce the btd discoverable rejection over Wi-Fi.

The host tunnel `adb forward tcp:19999 localfilesystem:/run/libreecho/bluetooth.sock`
exposes btd's real adapter socket, which is the exact socket the web API's
backend calls (backend_linux.c bluetooth_controller_setting).  It sends the same
{"enabled": bool} request the API produces.

Runtime-only: BT settings are toggled and restored; no files, no reboot.
"""
import json
import socket
import sys
import time

HOST, PORT = "127.0.0.1", 19999


def btd(cmd, args=None, timeout=10):
    s = socket.create_connection((HOST, PORT), timeout=timeout)
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


def report(label, raw):
    print("== %s" % label)
    print(raw)
    sys.stdout.flush()


def caps():
    data = json.loads(btd("status"))["data"]
    out = {k: data["capabilities"][k]
           for k in ("connectable", "discoverable", "bondable")}
    out["last_error"] = data["last_error"]
    out["state"] = data["state"]
    out["enabled"] = data["enabled"]
    return out


report("status-baseline", json.dumps(caps(), separators=(",", ":")))

# 1. The reported failure: make the adapter visible while page scan is off.
report("set_discoverable_true-without-connectable",
       btd("set_discoverable", {"enabled": True}))
report("status-after-failed-enable", json.dumps(caps(), separators=(",", ":")))

# The same kernel precondition also rejects a disable while not connectable.
report("set_discoverable_false-without-connectable",
       btd("set_discoverable", {"enabled": False}))

# 2. Workaround order that the web UI's separate toggle allows.
report("set_connectable_true", btd("set_connectable", {"enabled": True}))
report("set_discoverable_true-after-connectable",
       btd("set_discoverable", {"enabled": True}))
time.sleep(2)
report("status-after-success", json.dumps(caps(), separators=(",", ":")))

# 3. Restore the settings observed at baseline.
report("restore-discoverable-false", btd("set_discoverable", {"enabled": False}))
report("restore-connectable-false", btd("set_connectable", {"enabled": False}))
time.sleep(3)
report("status-restored", json.dumps(caps(), separators=(",", ":")))
