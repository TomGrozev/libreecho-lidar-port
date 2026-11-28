#!/usr/bin/env python3
"""Append one temporary local account line to a users-file copy.
Usage: mkuser.py <input-users-file> <output-file> <username> <password>
Format: name:sha256:<salt hex>:sha256(salt ":" password)
"""
import hashlib
import os
import sys

src, dst, user, password = sys.argv[1:5]
salt = os.urandom(16).hex()
digest = hashlib.sha256((salt + ":" + password).encode()).hexdigest()
line = "%s:sha256:%s:%s\n" % (user.lower(), salt, digest)
data = open(src, "rb").read() if os.path.exists(src) else b""
if data and not data.endswith(b"\n"):
    data += b"\n"
open(dst, "wb").write(data + line.encode())
os.chmod(dst, 0o600)
print("appended", user)
