#!/usr/bin/env python3
"""Longer baby-monitor capture: 6 s on the listed source, channels 0 and 6."""
import struct
import time
import urllib.request

from client import Client

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
for ch in ("0", "6"):
    for attempt in (1, 2):
        url = ("http://127.0.0.1:18090/api/v1/baby-monitor/stream?source=0:1"
               "&channel=%s" % ch)
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + c.token)
        pcm = b""
        hdr = ""
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                hdr = r.headers.get("X-LibreEcho-Audio", "")
                while time.time() - t0 < 6 and len(pcm) < 384000:
                    b = r.read(4096)
                    if not b:
                        break
                    pcm += b
        except Exception as e:  # noqa: BLE001
            print("ch", ch, "attempt", attempt, "error", e)
            continue
        n = len(pcm) // 2 * 2
        s = struct.unpack("<%dh" % (n // 2), pcm[:n])
        rms = (sum(x * x for x in s) / len(s)) ** 0.5 if s else 0
        peak = max((abs(x) for x in s), default=0)
        step = 32000
        per = [round((sum(x * x for x in s[i:i + step]) /
                      max(1, len(s[i:i + step]))) ** 0.5, 1)
               for i in range(0, min(len(s), 6 * step), step)]
        print("ch", ch, "try", attempt, "bytes", len(pcm), "hdr", hdr,
              "rms", round(rms, 2), "peak", peak, "per_sec", per)
