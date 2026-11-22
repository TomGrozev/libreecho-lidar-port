#!/usr/bin/env python3
"""Exercise pairing mode (bondable -> connectable -> discoverable) on the UI API."""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18080/api/v1"
TOKEN, CSRF = open("/tmp/le-step15-token").read().split()


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", "Bearer " + TOKEN)
    if data is not None:
        req.add_header("Content-Type", "application/json")
        req.add_header("X-LibreEcho-CSRF", CSRF)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def brief(label, st, body):
    d = body.get("data") or {}
    print("== %s %s %s" % (label, st, json.dumps({
        k: d[k] for k in ("state", "enabled", "hci", "transport", "pairing_mode",
                          "last_error", "profile_state", "discoverable",
                          "connectable", "capabilities") if k in d},
        separators=(",", ":"))))
    sys.stdout.flush()


import sys

st, body = call("POST", "/bluetooth/pairing-mode", {"enabled": True})
print("== pairing-mode-on", st, json.dumps(body, separators=(",", ":")))
brief("after-pairing-on", *call("GET", "/bluetooth"))
time.sleep(2)
brief("after-pairing-on-2s", *call("GET", "/bluetooth"))

st, body = call("POST", "/bluetooth/pairing-mode", {"enabled": False})
print("== pairing-mode-off", st, json.dumps(body, separators=(",", ":")))
brief("after-pairing-off", *call("GET", "/bluetooth"))
