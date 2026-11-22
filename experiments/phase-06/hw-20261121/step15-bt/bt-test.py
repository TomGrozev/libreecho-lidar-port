#!/usr/bin/env python3
"""Step 15 Bluetooth acceptance via the UI control API.

Runs on the host against an `adb forward tcp:18080 tcp:8080` tunnel (adb reverse is
unavailable on this adbd).  Creates a temporary local account, exercises the BT
endpoints, and leaves the account file for the caller to remove.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:18080/api/v1"
USER = "phase6-verify"
PASS = os.environ['LIBREECHO_WEB_PASSWORD']
CSRF = ""


def call(method, path, body=None, token=None, csrf=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if method not in ("GET", "HEAD") and csrf:
        req.add_header("X-LibreEcho-CSRF", csrf)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw}


def show(label, status, body):
    print("== %s %s" % (label, status))
    print(json.dumps(body, separators=(",", ":")))
    sys.stdout.flush()


def brief(label, status, body):
    d = body.get("data") or {}
    keys = ("state", "enabled", "transport", "hci", "address", "last_error",
            "profile_state", "profile_error", "profile_services", "scanning",
            "discoverable", "connectable", "capabilities", "discovered")
    out = {k: d[k] for k in keys if k in d}
    print("== %s %s %s" % (label, status, json.dumps(out, separators=(",", ":"))))
    sys.stdout.flush()


def main():
    global CSRF
    st, body = call("GET", "/config")
    CSRF = (body.get("data") or {}).get("csrf_token", "")
    show("config-bootstrap", st, {"bootstrap_required": body["data"].get("bootstrap_required"),
                                  "user_count": body["data"].get("user_count")})

    st, body = call("POST", "/auth/bootstrap",
                    {"username": USER, "password": PASS, "password_confirm": PASS}, csrf=CSRF)
    show("bootstrap", st, body)
    token = (body.get("data") or {}).get("token", "")

    st, body = call("GET", "/config", token=token)
    CSRF = (body.get("data") or {}).get("csrf_token", CSRF)
    show("config-auth", st, body)

    st, body = call("GET", "/bluetooth", token=token)
    brief("bt-get", st, body)

    t0 = time.time()
    st, body = call("PUT", "/bluetooth", {"enabled": True}, token=token, csrf=CSRF)
    show("bt-enable", st, body)

    enabled = False
    for _ in range(20):
        time.sleep(1)
        st, body = call("GET", "/bluetooth", token=token)
        d = body.get("data") or {}
        if d.get("enabled"):
            enabled = True
            break
    print("== bt-enable-latency seconds=%.1f" % (time.time() - t0))
    brief("bt-enabled", st, body)

    st, body = call("PUT", "/bluetooth", {"discoverable": True}, token=token, csrf=CSRF)
    show("bt-discoverable", st, body)
    st, body = call("GET", "/bluetooth", token=token)
    d = body.get("data") or {}
    print("== bt-discoverable-check %s" % json.dumps({
        "discoverable": d.get("discoverable"),
        "capabilities.discoverable": (d.get("capabilities") or {}).get("discoverable"),
        "profile_services": d.get("profile_services"),
        "profile_state": d.get("profile_state"),
    }, separators=(",", ":")))

    t0 = time.time()
    st, body = call("POST", "/bluetooth/scan", {}, token=token, csrf=CSRF)
    show("bt-scan", st, body)
    st, body = call("GET", "/bluetooth", token=token)
    d = body.get("data") or {}
    print("== bt-scan-now seconds=%.1f scanning=%s discovered=%s" % (
        time.time() - t0, d.get("scanning"), json.dumps(d.get("discovered") or [])))

    time.sleep(12)
    st, body = call("GET", "/bluetooth", token=token)
    d = body.get("data") or {}
    print("== bt-scan-12s seconds=%.1f scanning=%s discovered=%s" % (
        time.time() - t0, d.get("scanning"), json.dumps(d.get("discovered") or [])))
    show("bt-after-scan", st, body)

    st, body = call("POST", "/bluetooth/scan/stop", {}, token=token, csrf=CSRF)
    show("bt-scan-stop", st, body)

    with open("/tmp/le-step15-token", "w") as f:
        f.write(token + "\n" + CSRF + "\n")
    print("== token-saved")

    st, body = call("PUT", "/bluetooth", {"discoverable": False}, token=token, csrf=CSRF)
    show("bt-discoverable-off", st, body)


if __name__ == "__main__":
    main()
