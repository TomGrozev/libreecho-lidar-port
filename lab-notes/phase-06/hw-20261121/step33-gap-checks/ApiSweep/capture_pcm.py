#!/usr/bin/env python3
"""Capture a few seconds of the baby-monitor stream and measure it."""
import struct
import time
import urllib.request

from client import Client

user, password = open("api/.cred").read().splitlines()
c = Client().login(user, password)
wanted = 64000  # 2 s of 16 kHz mono s16
for source in ("0:1", "0:24"):
    url = ("http://127.0.0.1:18090/api/v1/baby-monitor/stream?source=%s"
           "&channel=0" % source)
    req = urllib.request.Request(url)
    req.add_header("Authorization", "Bearer " + c.token)
    pcm = b""
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            hdr = r.headers.get("X-LibreEcho-Audio", "")
            while len(pcm) < wanted and time.time() - started < 4:
                chunk = r.read(4096)
                if not chunk:
                    break
                pcm += chunk
        tag = "ok"
    except Exception as e:  # noqa: BLE001
        hdr = ""
        tag = "error:%s" % e
    n = len(pcm) // 2 * 2
    samples = struct.unpack("<%dh" % (n // 2), pcm[:n])
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0.0
    peak = max((abs(s) for s in samples), default=0)
    name = source.replace(":", "_")
    open("api/babymonitor-%s.pcm" % name, "wb").write(pcm)
    print(source, tag, "bytes", len(pcm), "audio", hdr,
          "rms %.1f peak %d" % (rms, peak))
