#!/usr/bin/env python3
"""Create the temporary API account and push it, restarting the web daemon.

Password goes to api/.cred (mode 600) and is never printed.
"""
import hashlib
import os
import secrets
import subprocess
import sys

ADB = os.path.abspath("../../bin/adb")
SERIAL = "<DEVICE_IP_A>:5555"
USER = "le-sweep33"

def adb(*args, check=True):
    return subprocess.run([ADB, "-s", SERIAL, *args], check=check,
                          capture_output=True, text=True)

src = open("users.orig", "rb").read()
assert src.count(b"\n") == 1, src
password = secrets.token_hex(16)
salt = secrets.token_hex(16)
digest = hashlib.sha256((salt + ":" + password).encode()).hexdigest()
line = "%s:sha256:%s:%s\n" % (USER, salt, digest)
if not src.endswith(b"\n"):
    src += b"\n"
open("users.new", "wb").write(src + line.encode())
os.chmod("users.new", 0o600)
os.makedirs("api", exist_ok=True)
with open("api/.cred", "w") as f:
    f.write(USER + "\n" + password + "\n")
os.chmod("api/.cred", 0o600)

adb("push", "users.new", "/data/libreecho/config/users")
adb("shell", "chmod 600 /data/libreecho/config/users")
before = adb("shell", "sha256sum /data/libreecho/config/users").stdout.strip()
print("pushed users:", before)
adb("shell", "/etc/init.d/libreecho-web.init restart")
print("web restarted")
