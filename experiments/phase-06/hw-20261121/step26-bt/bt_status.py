#!/usr/bin/env python3
"""Print btd status (read-only). Needs
`adb forward tcp:19999 localfilesystem:/run/libreecho/bluetooth.sock`.
Device addresses are cut to their last two bytes."""
import json
import re
import socket

s = socket.create_connection(("127.0.0.1", 19999), timeout=10)
s.sendall(b'{"v":1,"id":1,"cmd":"status","args":{}}\n')
buf = b""
while not buf.endswith(b"\n"):
    chunk = s.recv(65536)
    if not chunk:
        break
    buf += chunk
text = re.sub(r"([0-9A-Fa-f]{2}:){4}([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})", r"xx:\2", buf.decode())
print(json.dumps(json.loads(text), indent=1))
