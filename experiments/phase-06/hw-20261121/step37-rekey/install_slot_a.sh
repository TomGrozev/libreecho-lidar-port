#!/usr/bin/env bash
# Step 37: bootstrap the replacement OTA key by writing the new-key v0.2.28 boot image straight
# to the inactive slot (A, /dev/mmcblk0p10) over root adb. The supported path
# (`libreecho-update install`) cannot carry it: the running v0.2.27 trusts only the old key in
# its ramdisk, and that seed is lost. This is the owner-approved one-off deviation described in
# agent report AdbKeyRotation; the write and readback match libreecho-update:559-565.
#
# usage: install_slot_a.sh preflight|write|activate|reboot
#   preflight  read-only device state; refuses unless running slot b is confirmed
#   write      push image, check device hash, dd to p10, 16 MiB readback      (device write)
#   activate   libreecho-bootctl activate a (BCB at misc 0x360, tries 3)       (device write)
#   reboot     reboot, reconnect, wait for slot a and its first-boot confirm   (device reboot)
# Each device-changing subcommand needs its own owner approval (PLAN.md safety rule 4).
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$root"
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
S=${LIDAR_WIFI:-<DEVICE_IP_A>:5555}
img=artifacts/phase-06/images-step37-v0228/boot-lidar-v2.img
want=a7b266b74af89ae203d35b8460866ebb6d654d64742089ad5a4bbb0b838f82dc
remote=/data/libreecho/incoming/boot-v0228-rekey.img
part=/dev/mmcblk0p10
out=experiments/phase-06/hw-20261121/step37-rekey/hw
mkdir -p "$out"
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }
die() { t "ABORT $*"; exit 1; }
dev() { timeout "${2:-60}" adb -s "$S" shell "export PATH=/usr/local/sbin:\$PATH; $1" 2>&1 | tr -d '\r'; }
slot() { dev 'tr " " "\n" < /proc/cmdline | sed -n "s/^androidboot.slot_suffix=_//p"' 20; }
reconnect() {
  local deadline=$(( $(date +%s) + ${1:-1200} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    timeout 10 adb connect "$S" > /dev/null 2>&1
    timeout 15 adb -s "$S" shell 'true' > /dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}
state='uname -r; tr " " "\n" < /proc/cmdline; cat /proc/sys/kernel/random/boot_id; libreecho-bootctl status; libreecho-update status; echo current=$(cat /data/libreecho/update/current 2>/dev/null); cat /data/libreecho/update/boot-health /data/libreecho/update/pending 2>/dev/null; ip -4 addr show wlan0'

# Every subcommand re-checks that slot b is running and confirmed, and that p10 is boot_a.
guard() {
  reconnect 60 || die "no wifi adb at $S"
  local s; s=$(slot)
  [ "$s" = b ] || die "running slot is '$s', expected b"
  dev 'libreecho-bootctl status' > "$out/bootctl-$1.log"
  grep -q 'slot_b_success=1' "$out/bootctl-$1.log" || die "slot b is not confirmed"
  dev "cat /sys/class/block/${part#/dev/}/uevent; echo size=\$(cat /sys/class/block/${part#/dev/}/size)" > "$out/p10-$1.log"
  grep -q '^PARTNAME=boot_a$' "$out/p10-$1.log" || die "$part is not boot_a"
  grep -q '^size=32768$' "$out/p10-$1.log" || die "$part is not 32768 sectors"
}

case "${1:-}" in
  preflight)
    [ "$(sha256sum "$img" | cut -d' ' -f1)" = "$want" ] || die "host image hash mismatch"
    guard preflight
    dev "$state" > "$out/state-before.log"
    dev 'dd if=/dev/mmcblk0p11 bs=4096 count=4096 2>/dev/null | sha256sum' 120 > "$out/slot-b-hash.log"
    dev "dd if=$part bs=4096 count=4096 2>/dev/null | sha256sum" 120 > "$out/slot-a-hash-before.log"
    t "preflight ok: running b confirmed, p10=boot_a 32768; slot_b=$(cut -c1-16 "$out/slot-b-hash.log") slot_a_before=$(cut -c1-16 "$out/slot-a-hash-before.log")"
    ;;
  write)
    guard write
    dev 'mkdir -p /data/libreecho/incoming' > /dev/null
    timeout 600 adb -s "$S" push "$img" "$remote" > "$out/push.log" 2>&1 || die "push failed"
    got=$(dev "sha256sum $remote" 120 | cut -d' ' -f1)
    [ "$got" = "$want" ] || die "pushed image hash $got"
    t "pushed image, device hash ok"
    dev "dd if=$remote of=$part bs=4096 count=4096 conv=fsync; echo dd_rc=\$?" 300 > "$out/dd.log"
    grep -q 'dd_rc=0' "$out/dd.log" || die "dd failed (see dd.log); slot b untouched"
    back=$(dev "dd if=$part bs=4096 count=4096 2>/dev/null | sha256sum" 120 | cut -d' ' -f1)
    echo "$back" > "$out/slot-a-readback.log"
    [ "$back" = "$want" ] || die "readback $back != $want; do NOT activate"
    t "slot a written, readback ok $want"
    ;;
  activate)
    guard activate
    back=$(dev "dd if=$part bs=4096 count=4096 2>/dev/null | sha256sum" 120 | cut -d' ' -f1)
    [ "$back" = "$want" ] || die "slot a does not hold the step37 image ($back)"
    dev 'libreecho-bootctl activate a; echo activate_rc=$?; sync; libreecho-bootctl status' > "$out/activate.log"
    grep -q 'activate_rc=0' "$out/activate.log" || die "activate failed"
    t "activated: $(grep -o 'slot_a_[a-z]*=[0-9]*' "$out/activate.log" | tr '\n' ' ')"
    ;;
  reboot)
    [ "$(slot)" = b ] || die "not on slot b before reboot"
    dev 'libreecho-bootctl status' | grep -q 'slot_a_tries=3' || die "slot a not activated"
    last=$(dev 'cat /proc/sys/kernel/random/boot_id' 20)
    t "rebooting from b (boot_id $last)"
    timeout 15 adb -s "$S" shell reboot > /dev/null 2>&1
    sleep 30
    reconnect 1200 || die "no adb within 20 min; LK falls back to slot b after 3 failed tries"
    now=$(slot); t "back on slot $now (boot_id $(dev 'cat /proc/sys/kernel/random/boot_id' 20))"
    deadline=$(( $(date +%s) + 600 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
      dev 'libreecho-bootctl status' > "$out/bootctl-after.log"
      grep -q "slot_${now}_success=1" "$out/bootctl-after.log" && break
      sleep 15
    done
    dev "$state" > "$out/state-after.log"
    dev 'cat /etc/libreecho/ota-public-key.hex' > "$out/device-key.log"
    t "after: slot=$now $(grep -o "slot_${now}_[a-z]*=[0-9]*" "$out/bootctl-after.log" | tr '\n' ' ') key=$(cut -c1-16 "$out/device-key.log")"
    [ "$now" = a ] || die "booted slot $now, expected a"
    grep -q 'slot_a_success=1' "$out/bootctl-after.log" ||
      die "slot a not confirmed within 10 min; see boot-health in state-after.log"
    ;;
  *) echo "usage: $0 preflight|write|activate|reboot" >&2; exit 2 ;;
esac
