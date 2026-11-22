#!/usr/bin/env bash
# Step 33: install the v0.2.25 latency lab OTA over Wi-Fi and wait for the
# terminal confirmed state (PLAN.md Phase 6, "Validate development updates
# over Wi-Fi").  Every device command goes to adb over TCP; USB is never
# addressed.
#
# Bundle: artifacts/phase-06/ota-step33-latency/ -- OTA-profile v2 boot from
# the rebuild that carries the cpufreq-enabled kernel (Linux 77931cc, so
# mediatek-cpufreq binds and the OPP table reaches 1.3 GHz), waked asking for
# two ONNX intra-op threads, and esphomed streaming TTS playback with the
# bus prime on wake (UI a9cea2e).  Plus a derived feature catalog whose
# airplay2 payload carries the held-output audio engine (Platform 32f3dbd) so
# the amplifier settle leaves the reply path.  Writes userdata (generation
# tree, incoming bundle) and, through libreecho-update, the inactive boot slot
# and the BCB.  No fastboot.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
dir=artifacts/phase-06/ota-step33-latency
ver=0.2.25
out=experiments/phase-06/hw-20261121/step33-latency-fix
tx=$(basename "$dir"/generations/txn-*)
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }
# The old TCP session dies with the reboot; reconnect until a shell answers.
reconnect() {
  local deadline=$(( $(date +%s) + ${1:-1200} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    timeout 10 adb connect "$S" > /dev/null 2>&1
    if timeout 15 adb -s "$S" shell 'true' > /dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}
state='uname -r; tr " " "\n" < /proc/cmdline; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ls /data/libreecho/update; ip -4 addr show wlan0'

timeout 10 adb connect "$S" > "$out/connect.log" 2>&1
adb devices -l > "$out/devices.log" 2>&1
start=$(slot); [ -n "$start" ] || { t "no wifi adb at start"; exit 1; }
target=$([ "$start" = a ] && echo b || echo a)
t "start: bundle=v$ver tx=$tx slot=$start target=$target"
dev "$state" > "$out/state-before.log"

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
t "install: $(sed -n 's/.*\(verify_rc=[0-9]*\).*/\1/p;s/.*\(UPDATE_READY[^ ]*\) slot=\([ab]\).*/ready=\2/p;s/.*\(install_rc=[0-9]*\).*/\1/p' "$out/install.log" | tr '\n' ' ')"
sed -n 's/.*ota_manifest_signature=\(.*\)/signature=\1/p' "$out/install.log" >> "$out/events.log"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }

last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
t "reboot requested; pre-reboot boot_id $last"
[ "$(dev 'cat /proc/sys/kernel/random/boot_id' 20)" != "$last" ] || true
reconnect 1200 || { t "no adb after reboot"; exit 1; }
t "adb back on slot $(slot)"

# Terminal confirmed state: the target slot runs, the transaction is installed,
# and generation/current agree.  Same check as ota_step6_618.sh.
deadline=$(( $(date +%s) + 1200 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  s=$(dev "$state" 20)
  {
    echo "== $(date +%T)"
    printf '%s\n' "$s"
  } >> "$out/polls.log"
  now=$(printf '%s\n' "$s" | sed -n 's/^androidboot.slot_suffix=_//p' | head -n 1)
  [ -z "$now" ] && now=$(printf '%s\n' "$s" | sed -n 's/.*androidboot.slot_suffix=_\([ab]\).*/\1/p' | head -n 1)
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

# Read-only after-checks.  No audio is played: the ALSA check only reads the
# idle PCM state, and the cpufreq load is synthetic (`yes`).
dev 'CP=/sys/devices/system/cpu/cpu0/cpufreq
echo "== kver"; uname -r
echo "== cpufreq_dir"; ls -l "$CP" 2>&1
for f in scaling_driver scaling_governor scaling_available_governors \
    scaling_available_frequencies scaling_min_freq scaling_max_freq scaling_cur_freq
do
  printf "%s=" "$f"; cat "$CP/$f" 2>&1
done
echo "== load"
pids=""
for i in 1 2 3 4; do yes >/dev/null & pids="$pids $!"; done
sleep 4
printf "scaling_cur_freq_under_load_1="; cat "$CP/scaling_cur_freq" 2>&1
sleep 2
printf "scaling_cur_freq_under_load_2="; cat "$CP/scaling_cur_freq" 2>&1
kill $pids 2>/dev/null
wait 2>/dev/null
sleep 3
printf "scaling_cur_freq_after_load="; cat "$CP/scaling_cur_freq" 2>&1
echo "== dmesg_cpufreq"; dmesg | grep -i -E "mtk-cpufreq|cpufreq|OPP" | tail -n 20
echo "== services"
ps | grep -E "libreecho-(esphomed|audio-engine|waked|audiod|micd)" | grep -v grep
echo "== esphome_status"; cat /run/libreecho/esphome-status.json 2>&1
echo "== waked"
WP=$(pidof libreecho-waked 2>/dev/null)
echo "waked_pid=${WP:-none}"
if [ -n "${WP:-}" ]; then
  tr "\0" " " < /proc/$WP/cmdline; echo
  for tk in /proc/$WP/task/*/stat; do
    awk "{printf \"%s %s %s\n\", \$1, \$14, \$15}" "$tk"
  done > /tmp/waked-t1
  sleep 10
  for tk in /proc/$WP/task/*/stat; do
    awk "{printf \"%s %s %s\n\", \$1, \$14, \$15}" "$tk"
  done > /tmp/waked-t2
  awk "NR==FNR{u[\$1]=\$2;s[\$1]=\$3;next}
       {d=(\$2+\$3)-(u[\$1]+s[\$1]); printf \"tid=%s delta_ticks_10s=%d cpu_pct=%.1f\n\", \$1, d, d/10}" /tmp/waked-t1 /tmp/waked-t2
fi
echo "== hashes"
sha256sum /usr/local/sbin/libreecho-esphomed /usr/local/sbin/libreecho-audio-engine 2>&1
EP=$(pidof libreecho-audio-engine 2>/dev/null | awk "{print \$1}")
if [ -n "$EP" ]; then
  echo "engine_pid=$EP exe=$(readlink /proc/$EP/exe 2>/dev/null)"
  sha256sum "$(readlink /proc/$EP/exe 2>/dev/null)" 2>&1
  tr "\0" " " < /proc/$EP/cmdline; echo
fi
echo "== alsa_idle"
printf "pcm0p_status="; head -n 1 /proc/asound/card0/pcm0p/sub0/status 2>&1
ls /proc/asound/card0/pcm0p/sub0/ 2>&1
printf "pcm0c_status="; head -n 1 /proc/asound/card0/pcm0c/sub0/status 2>&1
echo "== open_fds"
for p in $EP $WP; do
  [ -n "$p" ] || continue
  ls -l /proc/$p/fd 2>/dev/null | grep -c pcm
done
' 600 > "$out/after-checks.log"
t "after-checks: $out/after-checks.log"
