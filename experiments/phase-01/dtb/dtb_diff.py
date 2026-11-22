#!/usr/bin/env python3
"""Walk extracted DTBs, dump node/prop inventory, and diff the Lidar variants."""
import json, os, struct, sys

OUT = "/workspace/libreecho/experiments/phase-01/dtb"
FDT_MAGIC = 0xD00DFEED


def align(x, p=4):
    return (x + p - 1) // p * p


def parse(blob):
    (magic, totalsize, off_struct, off_strings, off_rsv, ver, last,
     cpu, size_strings, size_struct) = struct.unpack(">10I", blob[:40])
    assert magic == FDT_MAGIC, hex(magic)
    strtab = blob[off_strings:off_strings + size_strings]
    pos, end = off_struct, off_struct + size_struct
    path, nodes = [], []
    while pos < end:
        tok = struct.unpack(">I", blob[pos:pos + 4])[0]; pos += 4
        if tok == 1:
            e = blob.index(b"\0", pos)
            name = blob[pos:e].decode("latin1")
            pos = align(e + 1)
            path.append(name)
            nodes.append({"path": "/" + "/".join(p for p in path if p), "props": {}})
        elif tok == 2:
            if path: path.pop()
        elif tok == 3:
            ln, nsoff = struct.unpack(">II", blob[pos:pos + 8]); pos += 8
            val = blob[pos:pos + ln]; pos = align(pos + ln)
            nm = strtab[nsoff:strtab.index(b"\0", nsoff)].decode("latin1")
            nodes[-1]["props"][nm] = val
        elif tok == 4:
            continue
        elif tok == 9:
            break
        else:
            raise ValueError(hex(tok))
    return nodes


def strs(v):
    return [x.decode("latin1") for x in v.split(b"\0") if x]


master = json.load(open(os.path.join(OUT, "boot-parse.json")))
entries = []
for i, t in enumerate(master["dtbs"]):
    blob = open(os.path.join(OUT, t["saved_as"]), "rb").read()
    nodes = parse(blob)
    entries.append({"index": i, "offset": t["offset"], "size": t["totalsize"],
                    "sha256": t["sha256"], "model": t["model"],
                    "compatible": t["compatible"],
                    "saved_as": t["saved_as"], "nodes": nodes})

json.dump([{k: e[k] for k in ("index", "offset", "size", "sha256", "model", "compatible", "saved_as")} |
           {"paths": [n["path"] for n in e["nodes"]]} for e in entries],
          open(os.path.join(OUT, "dtb-inventory.json"), "w"), indent=1)

lidar = [e for e in entries if any(c.startswith("amzn,lidar") for c in e["compatible"])]
print("lidar dtbs:", [(e["index"], e["model"]) for e in lidar])

# 1. properties anywhere in each lidar DTB whose name mentions board/hw/rev/efuse/id
KEY = ("board", "hw", "rev", "efuse", "sku", "project")
for e in lidar:
    print(f"\n== idx {e['index']} {e['model']} ==")
    for n in e["nodes"]:
        for k, v in n["props"].items():
            if any(s in k.lower() for s in KEY):
                print(f"  {n['path']} : {k} = {strs(v)[:4]}")

# 2. node path sets difference against the first lidar DTB
base = set(n["path"] for n in lidar[0]["nodes"])
for e in lidar[1:]:
    cur = set(n["path"] for n in e["nodes"])
    print(f"\n## {e['model']} vs {lidar[0]['model']}: only-here={sorted(cur-base)} only-base={sorted(base-cur)}")

# 3. property differences on shared paths
def propmap(e):
    return {n["path"]: {k: (strs(v) if b"\0" in v else v.hex()) for k, v in n["props"].items()}
            for n in e["nodes"]}
pm = [propmap(e) for e in lidar]
for i, e in enumerate(lidar[1:], 1):
    print(f"\n## prop diffs {e['model']} vs {lidar[0]['model']}")
    diff = 0
    for p in sorted(set(pm[0]) & set(pm[i])):
        a, b = pm[0][p], pm[i][p]
        for k in set(a) | set(b):
            if a.get(k) != b.get(k):
                diff += 1
                if diff <= 40:
                    print(f"  {p} {k}: {str(a.get(k))[:70]} -> {str(b.get(k))[:70]}")
    print("  total prop diffs:", diff)
