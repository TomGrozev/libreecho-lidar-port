#!/usr/bin/env python3
"""Step 34 recheck of the five API gaps on Lidar (slot a, 0.2.26).

Reversible writes only: config export/import of the same export, and BT
discoverable on then back off. The baby-monitor read, voice-pipeline read,
/light and /status are read-only. Nothing here reboots or changes mode.
"""
import hashlib
import json
import struct
import subprocess
import time
import urllib.request

from client import Client, dump

ADB = "../../bin/adb"
SERIAL = "<DEVICE_IP_A>:5555"
CFG = "/data/libreecho/config/web-config.json"


def adb(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def sha(path):
    return adb("shell", "sha256sum " + path).split()[0]


def get(path, timeout=30):
    st, body = c.call("GET", path, timeout=timeout)
    assert st == 200, (path, st, body)
    return body["data"]


def record(feature, result, detail, evidence):
    log.append({"feature": feature, "result": result, "detail": detail,
                "evidence": evidence})
    print("%-36s %-5s %s" % (feature, result, detail), flush=True)


user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
log = []

# ---- 1. Baby monitor: listed source and PCM -----------------------------
bm = get("/baby-monitor")
dump("get_baby-monitor", 200, {"ok": True, "data": bm})
listed = (bm.get("sources") or [{}])[0].get("id", "")
url = ("http://127.0.0.1:18090/api/v1/baby-monitor/stream?source=%s"
       "&channel=0" % listed)
req = urllib.request.Request(url)
req.add_header("Authorization", "Bearer " + c.token)
req.add_header("Accept", "*/*")
pcm = b""
audio_header = ""
stream_status = 0
stream_error = ""
started = time.time()
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        stream_status = r.status
        audio_header = r.headers.get("X-LibreEcho-Audio", "")
        while time.time() - started < 3.0 and len(pcm) < 192000:
            chunk = r.read(4096)
            if not chunk:
                break
            pcm += chunk
except Exception as e:  # noqa: BLE001
    stream_error = str(e)
n = len(pcm) // 2 * 2
samples = struct.unpack("<%dh" % (n // 2), pcm[:n])
rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0
peak = max((abs(s) for s in samples), default=0)
with open("api/babymonitor-%s.pcm" % listed.replace(":", "_"), "wb") as f:
    f.write(pcm)
with open("api/babymonitor-headers.txt", "w") as f:
    f.write("url: %s\nstatus: %d\nX-LibreEcho-Audio: %s\nbytes: %d\n"
            "rms: %.2f\npeak: %d\nerror: %s\n" %
            (url, stream_status, audio_header, len(pcm), rms, peak,
             stream_error))
record("baby-monitor listed source", "PASS" if listed == "0:1" else "FAIL",
       "GET /baby-monitor sources[0].id = %r (expected 0:1)" % listed,
       "api/get_baby-monitor.json")
record("baby-monitor stream PCM", "PASS" if (stream_status == 200 and
       rms > 8 and peak > 50) else "FAIL",
       "stream source=%s -> %d, %d bytes, %s, rms=%.2f peak=%d" %
       (listed, stream_status, len(pcm), audio_header or "-", rms, peak),
       "api/babymonitor-%s.pcm,api/babymonitor-headers.txt" %
       listed.replace(":", "_"))

# ---- 2. Config export, import of the same export ------------------------
st, export = c.call("GET", "/config/export")
dump("config_export", st, export)
assert st == 200
cfg = export["data"]
adb("pull", CFG, "api/web-config.before.json")
sha_before = sha(CFG)
st, imported = c.call("POST", "/config/import", cfg, timeout=90)
dump("config_import_same", st, imported)
time.sleep(1)
sha_after = sha(CFG)
adb("pull", CFG, "api/web-config.after.json")
st2, export2 = c.call("GET", "/config/export")
dump("config_export_after", st2, export2)
same_export = export2.get("data") == cfg
before = json.load(open("api/web-config.before.json"))
after = json.load(open("api/web-config.after.json"))


def field_diff(a, b, prefix=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            p = prefix + "." + k if prefix else k
            if k not in a:
                out.append({"field": p, "before": "<absent>",
                            "after": b[k]})
            elif k not in b:
                out.append({"field": p, "before": a[k],
                            "after": "<absent>"})
            else:
                out.extend(field_diff(a[k], b[k], p))
    elif a != b:
        out.append({"field": prefix or "<root>", "before": a, "after": b})
    return out


diff = field_diff(before, after)
with open("api/config-field-diff.json", "w") as f:
    json.dump({"sha_before": sha_before, "sha_after": sha_after,
               "bytes_identical": sha_before == sha_after,
               "semantic_identical": before == after,
               "fields": diff}, f, indent=1, sort_keys=True)
record("config export", "PASS" if st == 200 else "FAIL",
       "GET /config/export -> %d, schema %s, %d top-level keys" %
       (st, cfg.get("schema_version"), len(cfg)),
       "api/config_export.json")
record("config import of same export", "PASS" if st == 200 else "FAIL",
       "POST /config/import -> %d %s" %
       (st, json.dumps((imported or {}).get("error"))),
       "api/config_import_same.json")
record("web-config unchanged in meaning", "PASS" if (before == after and
       same_export) else "FAIL",
       "sha256 %s -> %s; parsed config equal=%s; re-export equal=%s; "
       "%d field(s) differ" % (sha_before[:12], sha_after[:12],
                               before == after, same_export, len(diff)),
       "api/config-field-diff.json,api/web-config.before.json,"
       "api/web-config.after.json")

# ---- 3. BT discoverable on then off ------------------------------------
bt_before = get("/bluetooth")
dump("bt_before", 200, {"ok": True, "data": bt_before})
st_on, b = c.call("PUT", "/bluetooth", {"discoverable": True})
dump("bt_discoverable_on", st_on, b)
time.sleep(1)
bt_on = get("/bluetooth")
dump("bt_after_on", 200, {"ok": True, "data": bt_on})
st_off, b = c.call("PUT", "/bluetooth", {"discoverable": False})
dump("bt_discoverable_off", st_off, b)
bt_off = get("/bluetooth")
for _ in range(5):
    if (bt_off["capabilities"]["connectable"] ==
            bt_before["capabilities"]["connectable"] and
            not bt_off["capabilities"]["discoverable"]):
        break
    time.sleep(1)
    bt_off = get("/bluetooth")
dump("bt_after_off", 200, {"ok": True, "data": bt_off})
caps_before, caps_on, caps_off = (x["capabilities"] for x in
                                  (bt_before, bt_on, bt_off))
record("BT discoverable on", "PASS" if st_on == 200 else "FAIL",
       "PUT {discoverable:true} -> %d; discoverable=%s connectable=%s" %
       (st_on, caps_on["discoverable"], caps_on["connectable"]),
       "api/bt_discoverable_on.json,api/bt_after_on.json")
record("BT discoverable off", "PASS" if st_off == 200 else "FAIL",
       "PUT {discoverable:false} -> %d; discoverable=%s" %
       (st_off, caps_off["discoverable"]),
       "api/bt_discoverable_off.json,api/bt_after_off.json")
record("BT connectable restored", "PASS" if (caps_off["connectable"] ==
       caps_before["connectable"]) else "FAIL",
       "connectable %s -> %s (on) -> %s (off), prior %s" %
       (caps_before["connectable"], caps_on["connectable"],
        caps_off["connectable"], caps_before["connectable"]),
       "api/bt_before.json,api/bt_after_off.json")

# ---- 4. Voice pipeline restart.phase -----------------------------------
vp = get("/voice-pipeline")
dump("voice_pipeline", 200, {"ok": True, "data": vp})
restart = vp.get("restart") or {}
record("voice-pipeline restart.phase", "PASS" if
       ("phase" in restart and restart.get("phase") == "" and
        restart.get("state") != "pending") else "FAIL",
       "mode=%s restart.state=%s phase=%r error=%r" %
       (vp.get("mode"), restart.get("state"), restart.get("phase"),
        restart.get("error")),
       "api/voice_pipeline.json")

# ---- 5. Light and status (read-only, current device state) -------------
import os
if not os.environ.get("SKIP_LIGHT"):
    light = get("/light")
    dump("light", 200, {"ok": True, "data": light})
    status = get("/status")
    dump("status", 200, {"ok": True, "data": status})
    record("GET /light lux", "PASS" if light.get("lux", -1) > 0 else "FAIL",
           "lux=%s calibrated_lux=%s powered=%s visible=%s infrared=%s" %
           (light.get("lux"), light.get("calibrated_lux"),
            light.get("powered"), light.get("visible"),
            light.get("infrared")), "api/light.json")
    record("/status temperature and light", "PASS" if
           (status.get("temperature_c", 0) > 0 and
            status.get("light_lux", -1) != -1) else "FAIL",
           "temperature_c=%s light_lux=%s" %
           (status.get("temperature_c"), status.get("light_lux")),
           "api/status.json")

with open("api/recheck-results.json", "w") as f:
    json.dump(log, f, indent=1, sort_keys=True)
print("recheck complete")
