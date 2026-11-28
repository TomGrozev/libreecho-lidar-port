# Lidar Wi-Fi slowdown, 2026-11-26

Cause: the unit joins whichever `<SSID_A>` BSS it picks at association and never
roams. One of them is an Espressif device (`<MAC_WLAN_NEIGHBOUR_A>`, ch 1, about -68 dBm, GTK TKIP).
On it everything is 10 to 18 times slower. The main AP (ch 11, about -44 dBm) is fast.

## Evidence

- Boot 17:41 (main AP, signal 211 = -45 dBm, samples 1-71): page 0.40 s, adb 2 MiB 1.8 s down
  and 1.7 s up, gateway RTT 3.4 ms. Flat for 2 h; no memory, CPU or fd growth.
- Boot 19:43 (v0.2.45 deploy reboot, Espressif AP, -68 dBm, samples 77-102): page 6.3 s,
  adb 2 MiB 28 s down and 18 s up, gateway RTT 21 ms. Slow from the first minute.
- networkd `scan` at 19:50 saw the NNI SSID at -44 dBm on ch 11 while the unit stayed on ch 1.
  No roam followed (`/tmp/wpa_supplicant.wlan0.log`, dmesg).
- `/sbin/wpa_supplicant` (v2.10) has no bgscan module (`strings`: no simple/learn), and
  `/data/libreecho/config/wpa_supplicant.conf` sets no `bgscan`, so it scans only to connect.
- Deploy push speeds alternate per boot: v0.2.41 first try, v0.2.42 and v0.2.44 at
  0.1 to 0.2 MB/s; v0.2.41 retry, v0.2.43 and v0.2.45 at 1.2 to 1.5 MB/s.
- Samples 72-75 (19:40-19:43) were slower because the v0.2.45 deploy pushed about 250 MB then.

## Side findings, not the cause

- DHCP is one-shot (`udhcpc -n -q` in Platform `libreecho-wifi` and UI `networkd.c`); the
  7200 s lease is never renewed. Effect after expiry not observed: the deploy rebooted the unit
  two minutes after expiry.
- MT7668 `get_station` sends 3 blocking firmware queries per `/proc/net/wireless` read.

## Files

`summary.tsv` and `raw/` hold the samples; `sample.py`, `analyze.py`, `stress.py` are the
throwaway tools. Pstore of the 19:43 reboot: `private/dumps/20261126-pstore-reboot-1943/`.
