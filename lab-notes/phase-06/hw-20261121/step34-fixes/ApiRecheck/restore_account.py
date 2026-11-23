#!/usr/bin/env python3
"""Restore the original users file byte-for-byte and restart the web daemon."""
import os
import subprocess

ADB = os.path.abspath("../../bin/adb")
SERIAL = "<DEVICE_IP_A>:5555"

def adb(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], check=True,
                          capture_output=True, text=True)

adb("push", "users.orig", "/data/libreecho/config/users")
adb("shell", "chmod 600 /data/libreecho/config/users")
print("restored users:", adb("shell", "sha256sum /data/libreecho/config/users").stdout.strip())
adb("shell", "/etc/init.d/libreecho-web.init restart")
print("web restarted")
if os.path.exists("api/.cred"):
    os.unlink("api/.cred")
print("credential file removed")
