#!/usr/bin/env bash
# Install the Lidar loudness lab OTA (v0.2.36) over Wi-Fi and confirm it, the
# way install_ota_v0235.sh did for v0.2.35. The OTA writes the inactive slot
# and reboots; the owner approved this install and reboot (2026-11-24).
#
# Captures before/after mixer and profile readbacks for the loudness check
# (LO Driver Gain, /etc/libreecho/audio-profile, the engine's startup line).
# Read-only apart from the documented install: no mixer writes, no playback.
#
# usage: install_ota_v0236.sh
set -u
root=$(cd "$(dirname "$0")/../../.." && pwd -P)
cd "$root"
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
dir=artifacts/phase-07/v0236/ota
ver=0.2.36
want_boot=$(sha256sum artifacts/phase-07/v0236/images/boot-lidar-v2.img | cut -d' ' -f1)
out=lab/phase-07/volume-quiet/install
tx=$(basename "$dir"/generations/txn-*)
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/sbin:/usr/sbin:/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }
reconnect() {
  local deadline=$(( $(date +%s) + ${1:-1200} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    timeout 10 adb connect "$S" > /dev/null 2>&1
    if timeout 15 adb -s "$S" shell 'true' > /dev/null 2>&1; then return 0; fi
    sleep 5
  done
  return 1
}
state='uname -r; tr " " "\n" < /proc/cmdline; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ls /data/libreecho/update; ip -4 addr show wlan0'
audio='echo "== LO/HP driver gain"; tinymix -c 0 contents | grep -E "Driver Gain Volume"; echo "== PCM Playback Volume"; tinymix -c 0 contents | grep "PCM Playback Volume"; echo "== profile"; cat /etc/libreecho/audio-profile; echo "== engine startup line"; grep "audio-engine: speaker chain" /var/log/libreecho-airplayd.log | tail -3; echo "== engine status"; cat /run/libreecho-audio/status.json 2>/dev/null; echo'

timeout 10 adb connect "$S" > "$out/connect.log" 2>&1
adb devices -l > "$out/devices.log" 2>&1
start=$(slot); [ -n "$start" ] || { t "no wifi adb at start"; exit 1; }
target=$([ "$start" = a ] && echo b || echo a)
t "start: bundle=v$ver tx=$tx slot=$start target=$target"
dev "$state" > "$out/state-before.log"
dev "$audio" > "$out/audio-before.log"
dev 'for p in 10 11; do printf "mmcblk0p%s " $p; dd if=/dev/mmcblk0p$p bs=4096 count=4096 2>/dev/null | sha256sum; done
echo "== payload sendspind"; sha256sum /run/libreecho/features/airplay2/root/usr/local/sbin/libreecho-sendspind 2>/dev/null
echo "== payload audio-engine"; sha256sum /run/libreecho/features/airplay2/root/usr/local/sbin/libreecho-audio-engine 2>/dev/null' 180 > "$out/state-before-hashes.log"

dev 'mkdir -p /data/libreecho/generations /data/libreecho/incoming' > /dev/null
timeout 600 adb -s "$S" push "$dir/generations/$tx" /data/libreecho/generations/ > "$out/push-gen.log" 2>&1 ||
  { t "push generation failed"; exit 1; }
timeout 600 adb -s "$S" push "$dir/lidar-lab-v$ver.ota.tar" /data/libreecho/incoming/local-install.ota.tar > "$out/push-tar.log" 2>&1 ||
  { t "push bundle failed"; exit 1; }
t "pushed: $(tail -n 1 "$out/push-tar.log")"
dev "g=/data/libreecho/generations/$tx
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-bootctl status" 600 > "$out/install.log"
t "install: $(sed -n 's/.*\(verify_rc=[0-9]*\).*/\1/p;s/.*\(install_rc=[0-9]*\).*/\1/p' "$out/install.log" | tr '\n' ' ')"
sed -n 's/.*ota_manifest_signature=\(.*\)/signature=\1/p' "$out/install.log" >> "$out/events.log"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }

last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
t "reboot requested; pre-reboot boot_id $last"
reconnect 1200 || { t "no adb after reboot"; exit 1; }
t "adb back on slot $(slot)"

deadline=$(( $(date +%s) + 1200 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  s=$(dev "$state" 20)
  { echo "== $(date +%T)"; printf '%s\n' "$s"; } >> "$out/polls.log"
  now=$(printf '%s\n' "$s" | sed -n 's/.*androidboot.slot_suffix=_\([ab]\).*/\1/p' | head -n 1)
  gen=$(printf '%s\n' "$s" | sed -n 's/^generation=//p' | head -n 1)
  cur=$(printf '%s\n' "$s" | sed -n 's/^current=//p' | head -n 1)
  st=$(printf '%s\n' "$s" | sed -n 's/^state=//p' | head -n 1)
  if [ "$now" = "$target" ] && [ "$st" = installed ] && [ "$gen" = "$tx" ] && [ "$cur" = "$tx" ]; then
    printf '%s\n' "$s" > "$out/state-after.log"
    t "CONFIRMED: slot=$now state=$st generation=$gen current=$cur"
    break
  fi
  sleep 15
done
[ -s "$out/state-after.log" ] || { t "FAIL: not confirmed on slot $target within 20 min"; exit 1; }

# Loudness readback: the profile must read 6,6, the payload engine must be this
# build, and the mixer LO gain may still be 0 until playback arms the output.
dev "$audio" > "$out/audio-after.log"
dev 'echo "== boot slots"
for p in 10 11; do printf "mmcblk0p%s " $p; dd if=/dev/mmcblk0p$p bs=4096 count=4096 2>/dev/null | sha256sum; done
echo "== payload audio-engine"; sha256sum /run/libreecho/features/airplay2/root/usr/local/sbin/libreecho-audio-engine 2>/dev/null
echo "== services"
ps | grep -E "libreecho-(web|airplayd|btd|timed|micd|waked|esphomed|audiod|sendspind)" | grep -v grep
echo "== uname"; uname -a; echo "== pstore"; ls /sys/fs/pstore 2>/dev/null' 180 > "$out/post-check.log"
t "post-check: $out/post-check.log audio-after: $out/audio-after.log"
got=$(sed -n 's/^mmcblk0p1[01] \([0-9a-f]*\).*$/\1/p' "$out/post-check.log")
printf '%s\n' "$got" | grep -qx "$want_boot" && t "slot boot image readback matches $want_boot" || t "WARN: a slot readback differs from $want_boot"
t "DONE"
