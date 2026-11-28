#!/usr/bin/env python3
"""Compare the first and latest sampler dumps and print what grew.

Usage: analyze.py [N]   compare sample 1 with sample N (default: latest)
"""
import collections
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sections(text):
    out, name = {}, None
    for line in text.splitlines():
        if line.startswith('@@'):
            name = line[2:].strip()
            out[name] = []
        elif name:
            out[name].append(line)
    return out


def kv_table(lines):
    """/proc/net/snmp style: header line then value line per protocol."""
    out = {}
    for head, vals in zip(lines[0::2], lines[1::2]):
        proto, keys = head.split(':', 1)
        for k, v in zip(keys.split(), vals.split(':', 1)[1].split()):
            out[f'{proto}.{k}'] = int(v)
    return out


def parse(path):
    s = sections(path.read_text(errors='replace'))
    m = {}
    m['uptime_s'] = float(s['uptime'][0].split()[0])
    m['load1'] = float(s['loadavg'][0].split()[0])
    m['last_pid'] = int(s['loadavg'][0].split()[4])
    for line in s['meminfo']:
        k, v = line.split(':', 1)
        m[f'mem.{k}'] = int(v.split()[0])
    for line in s['net/sockstat']:
        proto, rest = line.split(':', 1)
        f = rest.split()
        for k, v in zip(f[0::2], f[1::2]):
            m[f'sock.{proto}.{k}'] = int(v)
    for line in s['net/dev'][2:]:
        name, rest = line.split(':', 1)
        if name.strip() == 'wlan0':
            f = [int(x) for x in rest.split()]
            m.update({'wlan.rx_bytes': f[0], 'wlan.rx_pkts': f[1], 'wlan.rx_errs': f[2],
                      'wlan.rx_drop': f[3], 'wlan.tx_bytes': f[8], 'wlan.tx_pkts': f[9],
                      'wlan.tx_errs': f[10], 'wlan.tx_drop': f[11]})
    m.update(kv_table(s['net/snmp']))
    m.update(kv_table(s['net/netstat']))
    for line in s['net/wireless'][2:]:
        if 'wlan0' in line:
            m['wlan.level'] = float(line.split()[3].rstrip('.'))
    m['file_nr'] = int(s['sys/fs/file-nr'][0].split()[0])
    for line in s['softirqs'][1:]:
        name, rest = line.split(':', 1)
        m[f'softirq.{name.strip()}'] = sum(int(x) for x in rest.split())
    cpu = [int(x) for x in s['stat'][0].split()[1:]]
    m['cpu.busy'], m['cpu.total'] = sum(cpu) - cpu[3] - cpu[4], sum(cpu)
    m['unix_sockets'] = int(s['unix'][0]) - 1
    for line in s.get('vmstat', []):
        k, v = line.split()
        if k.startswith(('nr_slab', 'nr_kernel', 'nr_page_table', 'nr_free_pages', 'nr_shmem',
                         'nr_anon', 'nr_vmalloc')):
            m[f'vm.{k}'] = int(v)
    slab = {}
    for line in s['slabinfo'][2:]:
        f = line.split()
        slab[f[0]] = int(f[1]) * int(f[3])
    tcp = {}
    for name in ('net/tcp', 'net/tcp6'):
        for line in s[name][1:]:
            f = line.split()
            tcp[f[3]] = tcp.get(f[3], 0) + 1
            tx, rx = f[4].split(':')
            m['tcp.txq'] = m.get('tcp.txq', 0) + int(tx, 16)
            m['tcp.rxq'] = m.get('tcp.rxq', 0) + int(rx, 16)
    for state, n in tcp.items():
        m[f'tcp.state.{state}'] = n
    udp = {}
    for name in ('net/udp', 'net/udp6'):
        for line in s[name][1:]:
            f = line.split()
            port = int(f[1].split(':')[1], 16)
            udp[f'{name}:{port}'] = (int(f[4].split(':')[1], 16), int(f[-1]))
    for line in s['gwping']:
        if 'min/avg/max' in line:
            m['gw_rtt_avg'] = float(line.split('=')[1].split('/')[1])
    procs = {}
    for line in s['procs']:
        # the dump races exiting processes; their read errors land in the same stream
        if ' (' not in line or not line.split(' ', 2)[1].isdigit():
            continue
        nfd, rest = line.split(' ', 1)
        pid = int(rest.split(' ', 1)[0])
        comm = rest[rest.index('(') + 1:rest.rindex(')')]
        f = rest[rest.rindex(')') + 2:].split()
        procs[pid] = {'comm': comm, 'fds': int(nfd), 'state': f[0], 'cpu': int(f[11]) + int(f[12]),
                      'threads': int(f[17]), 'rss_kb': int(f[21]) * 4}
    return m, slab, udp, procs


def main():
    if len(sys.argv) == 3:
        first, last = Path(sys.argv[1]), Path(sys.argv[2])
        files, prev = [first, last], first
    else:
        files = sorted((HERE / 'raw').glob('*.txt'))
        files = [f for f in files if '@@end' in f.read_text(errors='replace')]
        last = files[int(sys.argv[1]) - 1] if len(sys.argv) > 1 else files[-1]
        first, prev = files[0], files[max(files.index(last) - 1, 0)]
    a, sa, ua, pa = parse(first)
    b, sb, ub, pb = parse(last)
    p, _, _, pp = parse(prev)
    hours = (b['uptime_s'] - a['uptime_s']) / 3600
    print(f'{len(files)} samples; {first.stem} (up {a["uptime_s"]/3600:.2f} h) -> {last.stem} '
          f'(up {b["uptime_s"]/3600:.2f} h), span {hours:.2f} h\n')
    print(f'{"metric":40} {"first":>14} {"last":>14} {"delta":>12}')
    for k in sorted(set(a) | set(b)):
        x, y = a.get(k, 0), b.get(k, 0)
        if x != y:
            print(f'{k:40} {x:>14} {y:>14} {y - x:>12}')
    print('\nslab growth (bytes, top 15)')
    for name, d in sorted(((n, sb.get(n, 0) - sa.get(n, 0)) for n in sb), key=lambda t: -t[1])[:15]:
        print(f'  {name:32} {sa.get(name, 0):>12} {sb.get(name, 0):>12} {d:>+12}')
    print('\nUDP sockets (rx_queue, drops)')
    for key in sorted(ub):
        print(f'  {key:24} first={ua.get(key)} last={ub[key]}')
    print('\nprocesses alive in both: fds / threads / rss_kb / cpu ticks per minute (first span vs last span)')
    early_min = (p['uptime_s'] - a['uptime_s']) / 60 or 1
    late_min = (b['uptime_s'] - p['uptime_s']) / 60 or 1
    for pid in sorted(pb):
        if pid not in pa:
            continue
        x, y = pa[pid], pb[pid]
        early = (pp[pid]['cpu'] - x['cpu']) / early_min if pid in pp else 0
        late = (y['cpu'] - pp[pid]['cpu']) / late_min if pid in pp else 0
        changed = (x['fds'], x['threads'], x['rss_kb']) != (y['fds'], y['threads'], y['rss_kb'])
        if changed or y['cpu'] - x['cpu'] > 100:
            print(f'  {pid:>6} {y["comm"]:18} fds {x["fds"]}->{y["fds"]} thr {x["threads"]}->{y["threads"]} '
                  f'rss {x["rss_kb"]}->{y["rss_kb"]} cpu/min {early:.0f}->{late:.0f}')
    count_a = collections.Counter(v['comm'] for v in pa.values())
    count_b = collections.Counter(v['comm'] for v in pb.values())
    print(f'\nprocess count {len(pa)} -> {len(pb)}; per-name changes:',
          {c: (count_a[c], count_b[c]) for c in count_a | count_b if count_a[c] != count_b[c]})


if __name__ == '__main__':
    main()
