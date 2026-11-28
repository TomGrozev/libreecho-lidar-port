#!/usr/bin/env python3
"""Read-only parser for the MTK/Android boot image and appended DTBs."""
import hashlib, json, os, struct, sys

BOOT = "/workspace/libreecho/private/dumps/20261110-lidar-readback/boot_a.bin"
OUT = "/workspace/libreecho/private/lab/phase-01/dtb"

FDT_MAGIC = 0xD00DFEED
HEADER_FIELDS = ["kernel_size", "kernel_addr", "ramdisk_size", "ramdisk_addr",
                 "second_size", "second_addr", "tags_addr", "page_size",
                 "header_version", "os_version"]


def parse_android_header(d):
    h = {"magic": d[:8].decode("latin1")}
    vals = struct.unpack("<10I", d[8:48])
    h.update(dict(zip(HEADER_FIELDS, vals)))
    h["name"] = d[48:64].split(b"\0")[0].decode("latin1")
    h["cmdline"] = d[64:576].split(b"\0")[0].decode("latin1")
    h["id"] = d[576:608].hex()
    h["extra_cmdline"] = d[608:1632].split(b"\0")[0].decode("latin1")
    return h


def align(x, p):
    return (x + p - 1) // p * p


def parse_fdt_header(d, off):
    magic, totalsize, off_dt_struct, off_dt_strings, off_mem_rsvmap, \
        version, last_comp_version, boot_cpuid_phys, size_dt_strings, size_dt_struct = \
        struct.unpack(">10I", d[off:off + 40])
    return dict(offset=off, magic=magic, totalsize=totalsize,
                off_dt_struct=off_dt_struct, off_dt_strings=off_dt_strings,
                off_mem_rsvmap=off_mem_rsvmap, version=version,
                last_comp_version=last_comp_version,
                boot_cpuid_phys=boot_cpuid_phys,
                size_dt_strings=size_dt_strings, size_dt_struct=size_dt_struct)


def fdt_strings(d, h):
    s = h["offset"] + h["off_dt_strings"]
    return d[s:s + h["size_dt_strings"]]


def fdt_walk(d, h):
    """Yield (path, {prop: bytes}) for every node; raises on malformed data."""
    blob = d[h["offset"]:h["offset"] + h["totalsize"]]
    strtab = fdt_strings(d, h)
    pos = h["off_dt_struct"]
    end = pos + h["size_dt_struct"]
    path = []
    nodes = []
    while pos < end:
        tok = struct.unpack(">I", blob[pos:pos + 4])[0]
        pos += 4
        if tok == 1:  # FDT_BEGIN_NODE
            e = blob.index(b"\0", pos)
            name = blob[pos:e].decode("latin1")
            pos = align(e + 1, 4)
            path.append(name)
            nodes.append({"path": "/" + "/".join(x for x in path if x), "props": {}})
        elif tok == 2:  # FDT_END_NODE
            if path:
                path.pop()
        elif tok == 3:  # FDT_PROP
            ln, nameoff = struct.unpack(">II", blob[pos:pos + 8])
            pos += 8
            val = blob[pos:pos + ln]
            pos = align(pos + ln, 4)
            nm = strtab[nameoff:strtab.index(b"\0", nameoff)].decode("latin1")
            if nodes:
                nodes[-1]["props"][nm] = val
        elif tok == 4:  # FDT_NOP
            continue
        elif tok == 9:  # FDT_END
            break
        else:
            raise ValueError(f"bad token {tok:#x} at {pos-4}")
    return nodes


def cstr(val):
    return val.split(b"\0")[0].decode("latin1")


def strlist(val):
    return [x.decode("latin1") for x in val.split(b"\0") if x]


def main():
    d = open(BOOT, "rb").read()
    h = parse_android_header(d)
    report = {"file": BOOT, "file_size": len(d),
              "file_sha256": hashlib.sha256(d).hexdigest(), "header": h}

    p = h["page_size"]
    off_kernel = p
    off_ramdisk = off_kernel + align(h["kernel_size"], p)
    off_second = off_ramdisk + align(h["ramdisk_size"], p)
    off_dt = off_second + align(h["second_size"], p)
    report["layout"] = {
        "page_size": p,
        "kernel": {"offset": off_kernel, "size": h["kernel_size"]},
        "ramdisk": {"offset": off_ramdisk, "size": h["ramdisk_size"]},
        "second": {"offset": off_second, "size": h["second_size"]},
        "dt_section": {"offset": off_dt, "size": h["header_version"]},
    }

    # Signature probes of each section start.
    report["section_magic"] = {
        "kernel": d[off_kernel:off_kernel + 0x20].hex(),
        "ramdisk": d[off_ramdisk:off_ramdisk + 0x20].hex(),
        "second": d[off_second:off_second + 0x20].hex(),
        "after_sections": d[off_dt:off_dt + 0x40].hex(),
    }

    # Scan whole image for FDT magic, walking each candidate.
    cands = []
    i = 0
    while True:
        i = d.find(struct.pack(">I", FDT_MAGIC), i)
        if i < 0:
            break
        cands.append(i)
        i += 4
    report["fdt_magic_hits"] = cands

    dtbs = []
    for off in cands:
        try:
            fh = parse_fdt_header(d, off)
            if fh["totalsize"] < 40 or off + fh["totalsize"] > len(d):
                raise ValueError("totalsize out of range")
            nodes = fdt_walk(d, fh)
        except Exception as e:
            report.setdefault("fdt_parse_failures", []).append({"offset": off, "error": str(e)})
            continue
        root = nodes[0]["props"] if nodes else {}
        blob = d[off:off + fh["totalsize"]]
        dtb = dict(fh)
        dtb["sha256"] = hashlib.sha256(blob).hexdigest()
        dtb["model"] = cstr(root.get("model", b"")) if "model" in root else None
        dtb["compatible"] = strlist(root.get("compatible", b"")) if "compatible" in root else []
        dtb["root_props"] = {k: strlist(v) if b"\0" in v else v.hex()
                             for k, v in root.items()}
        dtb["node_count"] = len(nodes)
        dtb["paths"] = [n["path"] for n in nodes]
        dtb["_blob"] = blob
        dtbs.append(dtb)

    os.makedirs(OUT, exist_ok=True)
    for idx, dtb in enumerate(dtbs):
        fn = os.path.join(OUT, f"dtb_{idx:02d}_{dtb['offset']:09x}.dtb")
        with open(fn, "wb") as f:
            f.write(dtb.pop("_blob"))
        dtb["saved_as"] = os.path.basename(fn)

    report["dtbs"] = dtbs
    with open(os.path.join(OUT, "boot-parse.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps({k: v for k, v in report.items() if k != "dtbs"}, indent=2))
    print("DTB count:", len(dtbs))
    for idx, t in enumerate(dtbs):
        print(idx, hex(t["offset"]), t["totalsize"], t["model"], t["compatible"], t["sha256"][:16])


if __name__ == "__main__":
    main()
