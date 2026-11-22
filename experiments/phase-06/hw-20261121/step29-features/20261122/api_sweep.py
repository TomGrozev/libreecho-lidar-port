#!/usr/bin/env python3
"""Read-mostly LibreEcho API sweep for the 2026-11-22 Lidar feature pass.
Temporary account, created and removed by the caller; writes are reverted."""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:18090/api/v1"
USER = sys.argv[1]
PASSWORD = sys.argv[2]
OUT = sys.argv[3]


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
            raw = r.read().decode()
            try:
                return r.status, json.loads(raw or "{}")
            except ValueError:
                return r.status, {"raw": raw[:2000]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:500]}
    except Exception as e:
        return 0, {"client_error": str(e)}


def dump(name, status, body):
    with open("%s/%s.json" % (OUT, name), "w") as f:
        json.dump({"status": status, "body": body}, f, indent=1, sort_keys=True)
    err = (body or {}).get("error")
    print("%-28s %s %s" % (name, status, json.dumps(err) if err else "ok"))


def ensure(token, csrf):
    st, body = call("GET", "/config", token=token)
    return 200 if st == 200 else st


st, body = call("GET", "/config")
csrf = (body.get("data") or {}).get("csrf_token", "")
st, body = call("POST", "/auth/login", {"username": USER, "password": PASSWORD}, csrf=csrf)
token = (body.get("data") or {}).get("token", "")
st, body = call("GET", "/config", token=token)
csrf = (body.get("data") or {}).get("csrf_token") or csrf
if not token:
    print("LOGIN FAILED", st, body)
    sys.exit(1)
print("login ok")

reads = ["/status", "/system", "/system/boot", "/system/update", "/diagnostics",
         "/logs?limit=40", "/events", "/privacy", "/wake-word", "/led",
         "/voice-pipeline", "/integrations", "/local-services", "/spotify",
         "/sendspin", "/storage/usb", "/playback", "/assistant", "/provenance",
         "/news", "/home-assistant", "/light", "/microphones/beams",
         "/baby-monitor", "/network", "/bluetooth", "/ui/preferences", "/timers",
         "/diagnostics/kernel"]
state = {}
for p in reads:
    name = "get" + p.replace("/", "_").replace("?", "_").replace("=", "-")
    st, body = call("GET", p, token=token)
    dump(name, st, body)
    state[p] = (st, body)

led = state["/led"][1].get("data") or {}
wd = state["/wake-word"][1].get("data") or {}

led_restore = {
    "night": led.get("night"),
    "idle_mode": led.get("idle_mode"),
    "idle_auto_off_minutes": led.get("idle_auto_off_minutes"),
    "sleep_light": led.get("sleep_light"),
}
sens0 = wd.get("sensitivity")

results = []


def w(name, method, path, payload):
    st, body = call(method, path, payload, token=token, csrf=csrf)
    dump(name, st, body)
    results.append((name, st, body))
    return st, body


try:
    # Timers: create then delete through the API.
    st, body = w("timer_create", "POST", "/timers", {"seconds": 3600, "label": "apSweep22"})
    tid = (body.get("data") or {}).get("id")
    st, body = w("timer_list_after_create", "GET", "/timers", None)
    if tid:
        w("timer_delete", "DELETE", "/timers/%d" % tid, None)
    w("timer_list_after_delete", "GET", "/timers", None)

    # Wake word sensitivity round-trip (installed model is read-only).
    if isinstance(sens0, int):
        target = sens0 + 3 if sens0 <= 96 else sens0 - 3
        w("wakeword_set", "PUT", "/wake-word", {"sensitivity": target})
        w("wakeword_get_changed", "GET", "/wake-word", None)
        w("wakeword_restore", "PUT", "/wake-word", {"sensitivity": sens0})
        w("wakeword_get_restored", "GET", "/wake-word", None)

    # Night mode.
    n = led_restore["night"] or {}
    w("night_set", "PUT", "/led/night",
      {"enabled": True, "start_minute": 1320, "end_minute": 420,
       "r": 255, "g": 40, "b": 0, "brightness": 12})
    w("night_get", "GET", "/led", None)
    w("night_restore", "PUT", "/led/night",
      {"enabled": bool(n.get("enabled")), "start_minute": int(n.get("start_minute", 1320)),
       "end_minute": int(n.get("end_minute", 420)),
       "r": 255, "g": 40, "b": 0, "brightness": 12})
    w("night_get_restored", "GET", "/led", None)

    # Sleep light.
    s = led_restore["sleep_light"] or {}
    w("sleep_set", "PUT", "/led/sleep",
      {"mode": "pulse", "brightness": 10, "period_ms": 8000, "timer_minutes": 0,
       "restore_on_boot": False})
    w("sleep_get", "GET", "/led", None)
    w("sleep_restore", "PUT", "/led/sleep",
      {"mode": s.get("mode", "off"), "brightness": int(s.get("brightness", 8)),
       "period_ms": int(s.get("period_ms", 8000)),
       "timer_minutes": int(s.get("timer_minutes", 0)),
       "restore_on_boot": bool(s.get("restore_on_boot", False))})
    w("sleep_get_restored", "GET", "/led", None)

    # Idle mode.
    w("idle_set", "PUT", "/led/idle", {"mode": "always", "auto_off_minutes": 0})
    w("idle_get", "GET", "/led", None)
    w("idle_restore", "PUT", "/led/idle",
      {"mode": led_restore["idle_mode"] or "indicator",
       "auto_off_minutes": int(led_restore["idle_auto_off_minutes"] or 0)})
    w("idle_get_restored", "GET", "/led", None)
finally:
    st, body = call("GET", "/led", token=token)
    dump("final_led", st, body)
    st, body = call("GET", "/wake-word", token=token)
    dump("final_wakeword", st, body)
    st, body = call("GET", "/timers", token=token)
    dump("final_timers", st, body)
print("sweep done")
