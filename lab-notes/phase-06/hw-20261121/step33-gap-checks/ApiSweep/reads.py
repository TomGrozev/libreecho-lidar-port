#!/usr/bin/env python3
"""Read-only baseline capture for the step33 API sweep."""
import sys

from client import Client, dump

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)

reads = [
    "/status", "/audio", "/baby-monitor", "/microphones/beams", "/led",
    "/buttons", "/network", "/ui/preferences", "/bluetooth",
    "/network/wifi/scan", "/voice-pipeline", "/config",
]
for path in reads:
    st, body = c.call("GET", path)
    dump("get" + path.replace("/", "_"), st, body)

st, body = c.call("GET", "/config/export")
dump("get_config_export", st, body)
open("api/config-export-baseline.json", "w").write(
    __import__("json").dumps(body.get("data"), indent=1, sort_keys=True))
print("baseline captured")
