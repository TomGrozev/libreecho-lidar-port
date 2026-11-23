#!/usr/bin/env python3
"""Sweep TCP split positions over the reproduction harness and summarise."""
import subprocess, sys, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
REPRO = os.path.join(HERE, "repro")
HEADER = (b"HTTP/1.1 200 OK\r\n"
          b"Server: Home Assistant\r\n"
          b"Content-Type: audio/wav\r\n"
          b"Transfer-Encoding: chunked\r\n"
          b"Connection: close\r\n\r\n")


def wire_layout(body_n, chunk):
    """Return wire total length and the offsets just after each chunk-size line."""
    pos = len(HEADER)
    starts = []
    if chunk == 0:
        sizes = [body_n]
    else:
        sizes = [min(chunk, body_n - at) for at in range(0, body_n, chunk)]
    for n in sizes:
        line = b"%x\r\n" % n
        starts.append((pos, pos + len(line), n))
        pos += len(line) + n + 2
    starts.append((pos, pos + 5, 0))  # terminal chunk
    pos += 5
    return pos, starts


def run(body, framing, splits):
    argv = [REPRO, body, framing] + [str(s) for s in splits]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    line = (p.stdout + p.stderr).strip().splitlines()[-1]
    d = dict(re.findall(r"(\w+)=(\S+)", line))
    return d, p.returncode


def main():
    body = sys.argv[1]
    framing = sys.argv[2]
    maxk = int(sys.argv[3]) if len(sys.argv) > 3 else 400
    body_n = os.path.getsize(body)
    chunk = 0
    if framing.startswith("chunked:"):
        chunk = int(framing.split(":")[1])
    total, starts = wire_layout(body_n, chunk)
    print(f"body={body_n} wire={total} chunk={chunk} chunk_headers={len(starts)}")

    # 1. One split at every offset in the header + first chunk header region.
    results = []
    for k in range(0, min(maxk, total)):
        d, rc = run(body, framing, [k])
        if d.get("rc") == "-1":
            results.append((k, d.get("fail_line"), d.get("state"),
                            d.get("first_write_at"), d.get("fail_at")))
    print(f"single-split failures in 0..{min(maxk,total)-1}: {len(results)}")
    for k, fl, st, fw, fa in results[:60]:
        print(f"  split={k} fail_line={fl} state={st} first_write_at={fw} fail_at={fa}")

    # 2. Around every chunk-size line: split right after 'SIZE', after the CR,
    #    and inside the hex digits.
    around = set()
    for a, b, n in starts[:-1]:
        for delta in (-2, -1, 0, 1, 2):
            around.add(a + delta)              # inside/at the hex digits
        around.add(b - 1)                       # the '\n' of the size line
        around.add(b)                           # first payload byte
        around.add(a - 1)                       # CRLF of previous chunk
    for k in sorted(x for x in around if 0 <= x < total):
        d, rc = run(body, framing, [k])
        if d.get("rc") == "-1":
            bad.append((k, d.get("fail_line"), d.get("state"),
                        d.get("first_write_at"), d.get("fail_at")))
    print(f"chunk-header split failures: {len(bad)} of {len(around)}")
    for k, fl, st, fw, fa in bad[:40]:
        print(f"  split={k} fail_line={fl} state={st} first_write_at={fw} fail_at={fa}")


if __name__ == "__main__":
    main()
