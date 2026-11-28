#!/usr/bin/env bash
# Step 27: reboot so wpa_supplicant starts with ctrl_interface=/tmp/wpa_ctrl, then check that
# Wi-Fi, networkd's control socket and the voice stack come back. Reboot only; no writes.
cd "$(dirname "$0")/../../../.." || exit 1
A=lab/phase-06/hw-20261121/bin/adb
S=<DEVICE_IP_A>:5555
log=lab/phase-06/hw-20261121/step27-websetup/reboot-check.log
"$A" -s "$S" shell reboot > "$log" 2>&1
sleep 30
for i in $(seq 1 40); do
  "$A" connect "$S" > /dev/null 2>&1
  up=$("$A" -s "$S" shell 'echo up' 2>/dev/null | tr -d '\r')
  if [ "$up" = up ]; then echo "adb back after try $i at $(date +%T)" >> "$log"; break; fi
  sleep 5
done
sleep 60
"$A" -s "$S" shell 'export PATH=/usr/local/sbin:$PATH; uptime; tr " " "\n" </proc/cmdline | grep slot_suffix; ls -la /tmp/wpa_ctrl; wpa_cli -p /tmp/wpa_ctrl -i wlan0 status | grep -E "^(wpa_state|ip_address)="; libreecho-update status | grep -E "^(state|generation)="; pidof libreecho-waked libreecho-agentd libreecho-sttd libreecho-ttsd' 2>&1 | tr -d '\r' >> "$log"
