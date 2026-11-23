#!/usr/bin/env python3
"""Read-only /light and /status sample after the recovery reboot."""
import json

from client import Client, dump

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
light = c.call("GET", "/light", timeout=20)
status = c.call("GET", "/status", timeout=20)
dump("light", light[0], light[1])
dump("status", status[0], status[1])
l = (light[1].get("data") or {})
s = (status[1].get("data") or {})
rows = [
    {"feature": "GET /light lux",
     "result": "PASS" if l.get("lux", -1) > 0 else "FAIL",
     "detail": "status=%s lux=%s calibrated_lux=%s powered=%s visible=%s "
               "infrared=%s" % (light[0], l.get("lux"),
                                l.get("calibrated_lux"), l.get("powered"),
                                l.get("visible"), l.get("infrared")),
     "evidence": "api/light.json"},
    {"feature": "/status temperature and light",
     "result": "PASS" if (s.get("temperature_c", 0) > 0 and
                          s.get("light_lux", -1) != -1) else "FAIL",
     "detail": "status=%s temperature_c=%s light_lux=%s" %
               (status[0], s.get("temperature_c"), s.get("light_lux")),
     "evidence": "api/status.json"},
]
with open("api/postreboot-results.json", "w") as f:
    json.dump(rows, f, indent=1, sort_keys=True)
for r in rows:
    print("%-32s %s %s" % (r["feature"], r["result"], r["detail"]))
