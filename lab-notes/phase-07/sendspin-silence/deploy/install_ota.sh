#!/usr/bin/env bash
# Generic Lidar lab-OTA installer: push one artifact directory over adb and
# prove the new slot is actually booted and healthy before reporting success.
#
# usage: install_ota.sh <artifact-dir|version> <usb:SERIAL|host:PORT>
#   install_ota.sh v0233 usb:<SERIAL_A>
#   install_ota.sh 0.2.33 host:<SETUP_AP_HOST_A>:5555
#
# Pre-flight refuses an artifact whose verify log is not clean or whose OTA tar
# does not match SHA256SUMS. Post-check fails hard after 10 minutes. Logs go to
# deploy/v<ver>/.
#
# Host-only until run: every device-changing step needs Main's go-ahead
# (PLAN.md rule 4).
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
export PATH=$root/lab/phase-06/hw-20261121/bin:$PATH

usage() { echo "usage: $0 <artifact-dir|version|vVER> <usb:SERIAL|host:PORT>" >&2; exit 2; }
[ $# -eq 2 ] || usage
arg=$1 transport=$2

case $arg in
  0.*.*) dir=artifacts/phase-07/v$(printf '%s' "$arg" | tr -d '.') ;;
  v[0-9]*) dir=artifacts/phase-07/$arg ;;
  *) dir=$arg ;;
esac
[ -d "$dir" ] || { echo "missing artifact dir: $dir" >&2; exit 1; }
ver=$(basename "$dir")
[ -n "$ver" ] || { echo "cannot name the artifact dir" >&2; exit 1; }
out=lab/phase-07/sendspin-silence/deploy/$ver
mkdir -p "$out"

case $transport in
  usb:*) S=${transport#usb:} ;;
  host:*) S=${transport#host:}; adb connect "$S" > "$out/adb-connect.log" 2>&1 ;;
  *:*:*) S=$transport; adb connect "$S" > "$out/adb-connect.log" 2>&1 ;;
  *) S=$transport ;;
esac
[ -n "$S" ] || usage

t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }

# adb prints errors such as "adb: device 'X' not found" on the same channel as
# command output. Only a UUID can be a boot_id.
is_uuid() {
  printf '%s\n' "$1" | grep -Eq '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
}
wait_boot_id() {
  local old_id=$1 deadline=$(( $(date +%s) + ${2:-1200} )) id
  while [ "$(date +%s)" -lt "$deadline" ]; do
    id=$(dev 'cat /proc/sys/kernel/random/boot_id' 15)
    if is_uuid "$id" && [ "$id" != "$old_id" ]; then echo "$id"; return 0; fi
    sleep 5
  done
  return 1
}

mapfile -t otas < <(find "$dir/ota" -maxdepth 1 -name '*.ota.tar' -type f 2>/dev/null)
[ "${#otas[@]}" -eq 1 ] || { t "expected exactly one OTA tar under $dir/ota, found ${#otas[@]}"; exit 1; }
ota=${otas[0]}
ota_rel=${ota#"$dir"/}
verify_log=$dir/verify-$ver.log
[ -f "$verify_log" ] || { t "missing verify log: $verify_log"; exit 1; }
if grep -Eq '^(FAIL|ERROR)' "$verify_log"; then
  t "refusing: verify log contains failures"; exit 1
fi
grep -q '^PASS ' "$verify_log" || { t "refusing: verify log has no PASS lines"; exit 1; }
want=$(awk -v p="$ota_rel" '$2 == p { print $1 }' "$dir/SHA256SUMS")
[ -n "$want" ] || { t "refusing: $ota_rel is not in SHA256SUMS"; exit 1; }
got=$(sha256sum "$ota" | cut -d' ' -f1)
[ "$got" = "$want" ] || { t "refusing: OTA sha256 $got != SHA256SUMS $want"; exit 1; }
t "preflight OK: $ota_rel sha256=$got verify=$(basename "$verify_log")"

adb devices -l > "$out/devices.log" 2>&1
# dev() pipes through tr, so its status cannot show whether adb reached the device.
[ "$(adb -s "$S" get-state 2>/dev/null)" = device ] || { t "no adb for $S"; exit 1; }
start=$(slot); [ -n "$start" ] || { t "cannot read the running slot"; exit 1; }
case $start in a) target=b ;; b) target=a ;; *) t "unknown running slot: $start"; exit 1 ;; esac
t "start: artifact=$ver slot=$start target=$target ota=$(basename "$ota")"
dev 'uname -r; tr " " "\n" < /proc/cmdline; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ip -4 addr show wlan0' > "$out/state-before.log"

tx=$(basename "$(find "$dir/ota/generations" -maxdepth 1 -mindepth 1 -type d | head -n 1)")
[ -n "$tx" ] || { t "no generation under $dir/ota/generations"; exit 1; }
dev 'mkdir -p /data/libreecho/generations /data/libreecho/incoming' > /dev/null
timeout 600 adb -s "$S" push "$dir/ota/generations/$tx" /data/libreecho/generations/ > "$out/push-gen.log" 2>&1 ||
  { t "push generation failed"; exit 1; }
timeout 600 adb -s "$S" push "$ota" /data/libreecho/incoming/local-install.ota.tar > "$out/push-tar.log" 2>&1 ||
  { t "push bundle failed"; exit 1; }
t "pushed generation $tx"

dev "g=/data/libreecho/generations/$tx
chmod 0400 \$g/target.manifest \$g/target.manifest.sig \$g/COMPLETE \$g/features/*/manifest.json \$g/features/*/payload.squashfs
chmod 0500 \$g \$g/features \$g/features/*
libreecho-generation verify \$g; echo verify_rc=\$?
libreecho-update install /data/libreecho/incoming/local-install.ota.tar; echo install_rc=\$?
sync; libreecho-bootctl status" 600 > "$out/install.log"
grep -q 'install_rc=0' "$out/install.log" || { t "install failed"; exit 1; }

last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
is_uuid "$last" || { t "cannot read a UUID pre-reboot boot_id: $last"; exit 1; }
timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
t "reboot requested; pre-reboot boot_id $last"
new=$(wait_boot_id "$last" 1200) || { t "no changed UUID boot_id after reboot"; exit 1; }
t "adb back with new boot_id $new on slot $(slot)"

deadline=$(( $(date +%s) + 600 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  s=$(dev 'printf "slot=%s\n" "$(tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p")"
printf "ipv4=%s\n" "$(ip -4 -o addr show wlan0 2>/dev/null | grep -c "inet ")"
[ -e /run/libreecho/startup-ready ] && echo startup_ready=yes || echo startup_ready=no
grep -q "boot-animation handover" /var/log/libreecho/ledd.log 2>/dev/null && echo ledd_handover=yes || echo ledd_handover=no
printf "update_state=%s\n" "$(sed -n "s/^state=//p" /data/libreecho/update/state 2>/dev/null)"
printf "boot_state=%s\n" "$(sed -n "s/^state=//p" /data/libreecho/update/boot-health 2>/dev/null)"' 30)
  { echo "== $(date +%T)"; printf '%s\n' "$s"; } >> "$out/post-polls.log"
  now=$(printf '%s\n' "$s" | sed -n 's/^slot=//p' | head -n 1)
  ipv4=$(printf '%s\n' "$s" | sed -n 's/^ipv4=//p' | head -n 1)
  ready=$(printf '%s\n' "$s" | sed -n 's/^startup_ready=//p' | head -n 1)
  led=$(printf '%s\n' "$s" | sed -n 's/^ledd_handover=//p' | head -n 1)
  ustate=$(printf '%s\n' "$s" | sed -n 's/^update_state=//p' | head -n 1)
  bstate=$(printf '%s\n' "$s" | sed -n 's/^boot_state=//p' | head -n 1)
  if [ "$now" = "$target" ] && [ "${ipv4:-0}" -ge 1 ] && [ "$ready" = yes ] &&
     [ "$led" = yes ] && [ "$ustate" = installed ] && [ "$bstate" = confirmed ]; then
    printf '%s\n' "$s" > "$out/state-after.log"
    t "CONFIRMED: slot=$now wlan0=ipv4 ready=yes ledd-handover=yes update=installed boot=confirmed"
    t "DONE"
    exit 0
  fi
  sleep 15
done
t "FAIL: slot $target not confirmed within 10 minutes (slot=${now:-?} ipv4=${ipv4:-0} ready=${ready:-?} ledd=${led:-?} update=${ustate:-?} boot=${bstate:-?})"
exit 1
