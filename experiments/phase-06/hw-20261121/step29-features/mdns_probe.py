#!/usr/bin/env python3
"""Send one mDNS PTR query and print matching answers (host side, read-only)."""
import socket
import struct
import sys


def name(q):
    out = b""
    for part in q.split("."):
        if part:
            out += bytes([len(part)]) + part.encode()
    return out + b"\0"


def read_name(buf, off):
    parts = []
    while True:
        n = buf[off]
        if n == 0:
            return ".".join(parts), off + 1
        if n & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", buf[off:off + 2])[0] & 0x3FFF
            sub, _ = read_name(buf, ptr)
            parts.append(sub)
            return ".".join(parts), off + 2
        off += 1
        parts.append(buf[off:off + n].decode("latin1"))
        off += n


def query(qname):
    tid = 0
    header = struct.pack("!HHHHHH", tid, 0, 1, 0, 0, 0)
    q = name(qname) + struct.pack("!HH", 12, 0x8001)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(3)
    s.sendto(header + q, ("224.0.0.251", 5353))
    found = []
    while True:
        try:
            data, addr = s.recvfrom(9000)
        except socket.timeout:
            break
        if addr[0] != sys.argv[1] if len(sys.argv) > 1 else False:
            continue
        an = struct.unpack("!H", data[6:8])[0]
        off = 12
        for _ in range(struct.unpack("!H", data[4:6])[0]):
            _, off = read_name(data, off)
            off += 4
        for _ in range(an):
            rn, off = read_name(data, off)
            rtype, _, _, rdlen = struct.unpack("!HHIH", data[off:off + 10])
            off += 10
            if rtype == 12:
                target, _ = read_name(data, off)
                found.append((rn, target))
            off += rdlen
    return found


for svc in ("_airplay._tcp.local", "_raop._tcp.local", "_esphomelib._tcp.local",
            "_spotify-connect._tcp.local", "_sendspin._tcp.local"):
    try:
        ans = query(svc)
    except OSError as e:
        ans = [("error", str(e))]
    print(svc, "->", ans if ans else "NO ANSWERS")
