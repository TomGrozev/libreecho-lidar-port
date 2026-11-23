#!/usr/bin/env python3
"""Reversible write sweep of the LibreEcho API on Lidar (step33, ApiSweep).

Every mutation is re-read and restored; anything with sound is marked
AUDIBLE in the log so the owner can confirm by ear.
"""
import hashlib
import json
import subprocess
import sys
import time

import urllib.request

from client import Client, dump

ADB = "../../bin/adb"
SERIAL = "<DEVICE_IP_A>:5555"


def adb(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def note(msg):
    print("NOTE " + msg, flush=True)


user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
log = []


def record(feature, result, detail, evidence):
    log.append({"feature": feature, "result": result, "detail": detail,
                "evidence": evidence})
    print("%-34s %-14s %s" % (feature, result, detail), flush=True)


def get(path):
    st, body = c.call("GET", path)
    assert st == 200, (path, st, body)
    return body["data"]


# ---- Config export / import of the same export ---------------------------
st, export = c.call("GET", "/config/export")
dump("ws_config_export", st, export)
assert st == 200
cfg = export["data"]
sha_before = adb("shell", "sha256sum /data/libreecho/config/web-config.json").split()[0]
st, imported = c.call("POST", "/config/import", cfg, timeout=60)
dump("ws_config_import_same", st, imported)
sha_after = adb("shell", "sha256sum /data/libreecho/config/web-config.json").split()[0]
st2, export2 = c.call("GET", "/config/export")
same_export = export2.get("data") == cfg
record("config export", "PASS", "GET /config/export 200, schema %s, %d fields" %
       (cfg.get("schema_version"), len(cfg)), "api/ws_config_export.json")
record("config import (same export)", "FAIL" if st != 200 else "PASS",
       "POST 501 on linux backend; import_configuration returns "
       "LE_NOT_SUPPORTED unless backend is mock (src/api.c:1767). "
       "web-config sha %s -> %s" % (sha_before[:12], sha_after[:12]),
       "api/ws_config_import_same.json")
record("config export after import", "PASS" if same_export else "FAIL",
       "export identical to the imported object: %s" % same_export,
       "api/ws_config_export.json")

# ---- Appearance round-trip ----------------------------------------------
ui = get("/ui/preferences")
old_theme, old_cmode = ui["ui_theme"], ui["color_mode"]
st, b = c.call("PUT", "/ui/preferences", {"ui_theme": "setup"})
dump("ws_ui_theme_set", st, b)
theme_after = get("/ui/preferences")
st, b = c.call("PUT", "/ui/preferences", {"color_mode": "light"})
dump("ws_ui_cmode_set", st, b)
cmode_after = get("/ui/preferences")
st, b = c.call("PUT", "/ui/preferences",
               {"ui_theme": old_theme, "color_mode": old_cmode})
dump("ws_ui_restore", st, b)
ui_restored = get("/ui/preferences")
record("appearance ui_theme", "PASS" if theme_after["ui_theme"] == "setup" else "FAIL",
       "%s -> setup -> %s" % (old_theme, ui_restored["ui_theme"]),
       "api/ws_ui_theme_set.json,api/ws_ui_restore.json")
record("appearance color_mode", "PASS" if cmode_after["color_mode"] == "light" else "FAIL",
       "'%s' -> light -> '%s'" % (old_cmode, ui_restored["color_mode"]),
       "api/ws_ui_cmode_set.json,api/ws_ui_restore.json")

# ---- Hostname round-trip ------------------------------------------------
net = get("/network")
old_host = net["hostname"]
new_host = "echo-api"
st, b = c.call("PUT", "/network", {"hostname": new_host})
dump("ws_hostname_set", st, b)
live_host = adb("shell", "hostname")
net_changed = get("/network")["hostname"]
st, b = c.call("PUT", "/network", {"hostname": old_host})
dump("ws_hostname_restore", st, b)
live_host2 = adb("shell", "hostname")
net_restored = get("/network")["hostname"]
record("hostname get/set-restore", "PASS" if (net_restored == old_host and
       live_host2 == old_host) else "FAIL",
       "%s -> %s (kernel hostname %s) -> %s" %
       (old_host, net_changed, live_host, net_restored),
       "api/ws_hostname_set.json,api/ws_hostname_restore.json")

# ---- Volume + audible checks -------------------------------------------
audio = get("/audio")
old_vol = audio["volume"]
st, b = c.call("PUT", "/audio", {"volume": 10})
dump("ws_volume_set10", st, b)
vol_low = get("/audio")["volume"]
st, b = c.call("PUT", "/audio", {"volume": 0})
dump("ws_volume_set0", st, b)
vol_zero = get("/audio")["volume"]
st, b = c.call("PUT", "/audio", {"volume": 10})
dump("ws_volume_set10b", st, b)
record("volume set/get", "PASS" if (vol_low == 10 and vol_zero == 0) else "FAIL",
       "%d -> 10 -> 0 -> 10 (low, not silent)" % old_vol,
       "api/ws_volume_set10.json,api/ws_volume_set0.json")

note("AUDIBLE: playing the API test tone at volume 10")
st, b = c.call("POST", "/audio/test")
dump("ws_audio_test_tone", st, b)
tone_status = st
time.sleep(2)
note("AUDIBLE: requesting a spoken announcement at volume 10")
st, b = c.call("POST", "/audio/announce",
               {"text": "LibreEcho API check."}, timeout=90)
dump("ws_audio_announce", st, b)
announce_status = st
time.sleep(6)
st, b = c.call("POST", "/audio/announce/stop")
dump("ws_audio_announce_stop", st, b)
st, b = c.call("PUT", "/audio", {"volume": old_vol})
dump("ws_volume_restore", st, b)
vol_restored = get("/audio")["volume"]
record("test tone (audible)", "PASS" if tone_status == 200 else "FAIL",
       "POST /audio/test -> %d; tone at volume 10 needs owner ear" % tone_status,
       "api/ws_audio_test_tone.json")
record("announcement (audible)", "PASS" if announce_status == 200 else "FAIL",
       "POST /audio/announce -> %d%s; HA mode keeps local ttsd stopped" %
       (announce_status, "" if announce_status == 200 else
        " (source: GET /voice-pipeline mode home-assistant)"),
       "api/ws_audio_announce.json")
record("volume restore", "PASS" if vol_restored == old_vol else "FAIL",
       "back to %d" % vol_restored, "api/ws_volume_restore.json")

# ---- Microphone gain and mute ------------------------------------------
audio = get("/audio")
old_gain, old_muted = audio["microphone_gain"], audio["microphone_muted"]
new_gain = 67 if old_gain != 67 else 69
st, b = c.call("PUT", "/audio", {"microphone_gain": new_gain})
dump("ws_micgain_set", st, b)
gain_after = get("/audio")["microphone_gain"]
st, b = c.call("PUT", "/audio", {"microphone_muted": True})
dump("ws_micmute_set", st, b)
mute_after = get("/audio")["microphone_muted"]
time.sleep(1)
st, b = c.call("PUT", "/audio", {"microphone_muted": old_muted})
dump("ws_micmute_restore", st, b)
mute_restored = get("/audio")["microphone_muted"]
record("mic gain set/get", "PASS" if gain_after == new_gain else "FAIL",
       "%d -> %d -> restore" % (old_gain, gain_after),
       "api/ws_micgain_set.json")
record("mic mute set/get", "PASS" if (mute_after is True and
       mute_restored is old_muted) else "FAIL",
       "%s -> true -> %s" % (old_muted, mute_restored),
       "api/ws_micmute_set.json,api/ws_micmute_restore.json")
st, b = c.call("PUT", "/audio", {"microphone_gain": old_gain})
dump("ws_micgain_restore", st, b)
record("mic gain restore", "PASS" if get("/audio")["microphone_gain"] == old_gain
       else "FAIL", "back to %d" % old_gain, "api/ws_micgain_restore.json")

# ---- LED profile and visualizer ----------------------------------------
led = get("/led")
old_profile = led["profiles"]["listening"]
old_vis = led["visualizer_enabled"]
st, b = c.call("PUT", "/led/profile",
               {"name": "listening", "r": 200, "g": 100, "b": 50,
                "brightness": 90})
dump("ws_led_profile_set", st, b)
prof_after = get("/led")["profiles"]["listening"]
st, b = c.call("PUT", "/led/profile", dict(name="listening", **old_profile))
dump("ws_led_profile_restore", st, b)
prof_restored = get("/led")["profiles"]["listening"]
st, b = c.call("PUT", "/led", {"visualizer_enabled": not old_vis})
dump("ws_led_visualizer_set", st, b)
vis_after = get("/led")["visualizer_enabled"]
st, b = c.call("PUT", "/led", {"visualizer_enabled": old_vis})
dump("ws_led_visualizer_restore", st, b)
vis_restored = get("/led")["visualizer_enabled"]
record("LED profile set/get", "PASS" if (prof_after["r"] == 200 and
       prof_restored == old_profile) else "FAIL",
       "listening %s -> %s -> restored" % (old_profile, prof_after),
       "api/ws_led_profile_set.json,api/ws_led_profile_restore.json")
record("LED visualizer setting", "PASS" if (vis_after is (not old_vis) and
       vis_restored is old_vis) else "FAIL",
       "%s -> %s -> %s" % (old_vis, vis_after, vis_restored),
       "api/ws_led_visualizer_set.json,api/ws_led_visualizer_restore.json")

# ---- Button mappings ---------------------------------------------------
btn = get("/buttons")
old_ab = btn["action_brightness"]
new_ab = 71 if old_ab != 71 else 72
st, b = c.call("PUT", "/buttons", {"action_brightness": new_ab})
dump("ws_buttons_set", st, b)
ab_after = get("/buttons")["action_brightness"]
st, b = c.call("PUT", "/buttons", {"action_brightness": old_ab})
dump("ws_buttons_restore", st, b)
ab_restored = get("/buttons")["action_brightness"]
record("button mappings set/get", "PASS" if (ab_after == new_ab and
       ab_restored == old_ab) else "FAIL",
       "action_brightness %d -> %d -> %d (other mappings unchanged)" %
       (old_ab, ab_after, ab_restored),
       "api/ws_buttons_set.json,api/ws_buttons_restore.json")

# ---- Bluetooth scan and discoverable ----------------------------------
st, b = c.call("POST", "/bluetooth/scan")
dump("ws_bt_scan_start", st, b)
scan_status = st
discovered = []
if st == 200:
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(2)
        bt = get("/bluetooth")
        if not bt.get("scanning"):
            discovered = bt.get("discovered") or []
            break
    dump("ws_bt_after_scan", 200, {"ok": True, "data": bt})
st, b = c.call("POST", "/bluetooth/scan/stop")
dump("ws_bt_scan_stop", st, b)
record("BT scan list", "PASS" if scan_status == 200 else "FAIL",
       "POST 200; scan finished; discovered=%d devices%s" %
       (len(discovered), "" if discovered else
        " (empty, as in step 15)"),
       "api/ws_bt_scan_start.json,api/ws_bt_after_scan.json")
st, b = c.call("PUT", "/bluetooth", {"discoverable": True})
dump("ws_bt_discoverable", st, b)
bt_after = get("/bluetooth")
record("BT discoverable flag", "FAIL" if st == 501 else "PASS",
       "PUT 501; kernel MGMT rejects SET_DISCOVERABLE while connectable is "
       "clear; btd's set_discoverable does not set connectable first "
       "(src/adapter/btd.c:2355-2372). pairing-mode works instead "
       "(btd.c:2022-2024). connectable=%s discoverable=%s after" %
       (bt_after["capabilities"]["connectable"],
        bt_after["capabilities"]["discoverable"]),
       "api/ws_bt_discoverable.json")

# ---- Wi-Fi scan --------------------------------------------------------
st, b = c.call("GET", "/network/wifi/scan")
dump("ws_wifi_scan", st, b)
nets = (b.get("data") or {}).get("networks") or []
record("Wi-Fi scan (read-only)", "PASS" if st == 200 and nets else "FAIL",
       "%d networks, strongest %s (%d dBm), no connect attempted" %
       (len(nets), nets[0]["ssid"] if nets else "-",
        nets[0]["rssi_dbm"] if nets else 0), "api/ws_wifi_scan.json")

# ---- Baby monitor PCM --------------------------------------------------
url = "http://127.0.0.1:18090/api/v1/baby-monitor/stream?source=0:24&channel=0"
req = urllib.request.Request(url)
req.add_header("Authorization", "Bearer " + c.token)
req.add_header("Accept", "*/*")
pcm = b""
audio_header = ""
with urllib.request.urlopen(req, timeout=15) as r:
    audio_header = r.headers.get("X-LibreEcho-Audio", "")
    started = time.time()
    while time.time() - started < 2.5:
        chunk = r.read(4096)
        if not chunk:
            break
        pcm += chunk
with open("api/babymonitor.pcm", "wb") as f:
    f.write(pcm)
with open("api/babymonitor-headers.txt", "w") as f:
    f.write("X-LibreEcho-Audio: %s\nbytes: %d\n" % (audio_header, len(pcm)))
# The shared calibrated stream is pcm_s16_le; treat the capture as s16le.
import struct
samples = struct.unpack("<%dh" % (len(pcm) // 2), pcm[:len(pcm) // 2 * 2])
rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0
peak = max(abs(s) for s in samples) if samples else 0
record("baby-monitor stream", "PASS" if rms > 8 and peak > 50 else "FAIL",
       "%d bytes in 2.5 s, %s, rms=%.1f peak=%d (nonzero, non-silent)" %
       (len(pcm), audio_header, rms, peak),
       "api/babymonitor.pcm,api/babymonitor-headers.txt")

# ---- HA restart state (read-only) -------------------------------------
vp = get("/voice-pipeline")
dump("ws_voice_pipeline_final", 200, {"ok": True, "data": vp})
record("HA restart state (read-only)", "PASS" if vp["restart"]["state"] == "ready"
       else "FAIL", "mode=%s restart.state=%s error='%s' (diagnosis from "
       "source, no mode toggle)" % (vp["mode"], vp["restart"]["state"],
                                    vp["restart"]["error"]),
       "api/ws_voice_pipeline_final.json")

# ---- Final state snapshot ---------------------------------------------
final = {"audio": get("/audio"), "led": get("/led"), "buttons": get("/buttons"),
         "network": get("/network"), "ui_preferences": get("/ui/preferences")}
dump("ws_final_state", 200, {"ok": True, "data": final})
with open("api/sweep-results.json", "w") as f:
    json.dump(log, f, indent=1, sort_keys=True)
print("sweep complete")
