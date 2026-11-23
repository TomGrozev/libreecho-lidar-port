#!/usr/bin/env python3
"""Probe baby-monitor stream query variants and report status/headers/body."""
from client import Client

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
queries = [
    "/baby-monitor/stream?source=0:24",
    "/baby-monitor/stream?source=0:24&channel=0",
    "/baby-monitor/stream?source=0:24&channel=6",
    "/baby-monitor/stream?source=0:1&channel=0",
]
for q in queries:
    st, h, body = c.call("GET", q, timeout=6, raw=True)
    print(q, st, len(body), h.get("X-LibreEcho-Audio"),
          h.get("Content-Type"), body[:240])
