#!/usr/bin/env python3
"""Read-only GET probe of the endpoints the step34 recheck needs."""
import json

from client import Client, dump

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
for name, path in [
    ("get_baby-monitor", "/baby-monitor"),
    ("get_light", "/light"),
    ("get_status", "/status"),
    ("get_voice-pipeline", "/voice-pipeline"),
    ("get_bluetooth", "/bluetooth"),
    ("get_config", "/config"),
]:
    st, body = c.call("GET", path, timeout=20)
    dump("probe_" + name, st, body)
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict):
        print(name, st, sorted(data.keys()))
        if name == "get_baby-monitor":
            print("  sources:", json.dumps(data.get("sources")))
        if name == "get_voice-pipeline":
            print("  restart:", json.dumps(data.get("restart")))
        if name == "get_bluetooth":
            print("  capabilities:", json.dumps(data.get("capabilities")))
        if name == "get_light":
            print("  light:", json.dumps(data))
