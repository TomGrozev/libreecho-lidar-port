#!/usr/bin/env bash
# Short 6.18 ADB stress: host-to-device pushes (the direction that hung before the MUSB
# fix) and device-to-host pulls, with a server restart in the middle.
set -u
root=$(cd "$(dirname "$0")/../../../.." && pwd)
export PATH=$root/experiments/phase-06/hw-20261121/bin:$PATH
out=$root/experiments/phase-06/hw-20261121/step3d-boot3/stress
mkdir -p "$out"
blob=$out/blob.bin
head -c 1048576 /dev/urandom > "$blob"
want=$(sha256sum < "$blob" | cut -c1-64)
t() { echo "$(date +%T) $*" | tee -a "$out/events.log"; }

ok_shell() {
  r=$(timeout 15 adb shell 'cat /proc/uptime' 2>&1 | tr '\n' ' ')
  case $r in *.*' '*.*) return 0 ;; esac
  t "shell failed: $r"; return 1
}
for k in $(seq 1 10); do
  if timeout 30 adb push "$blob" /tmp/blob.bin >/dev/null 2>&1; then
    got=$(timeout 15 adb shell 'sha256sum /tmp/blob.bin' 2>&1 | cut -c1-64)
    [ "$got" = "$want" ] || { t "push round $k hash mismatch"; exit 1; }
  else t "push round $k failed"; exit 1; fi
  ok_shell || exit 1
done
t "push 10/10 ok"
timeout 20 adb shell 'dd if=/dev/zero of=/tmp/zero.bin bs=1M count=1 2>/dev/null; sha256sum /tmp/zero.bin' > "$out/zero.txt" 2>&1
for k in $(seq 1 10); do
  if timeout 30 adb pull /tmp/zero.bin "$out/pull.bin" >/dev/null 2>&1; then
    got=$(sha256sum < "$out/pull.bin" | cut -c1-64)
    want2=$(cut -c1-64 "$out/zero.txt")
    [ "$got" = "$want2" ] || { t "pull round $k hash mismatch"; exit 1; }
  else t "pull round $k failed"; exit 1; fi
  ok_shell || exit 1
done
t "pull 10/10 ok"
adb kill-server; sleep 2; adb start-server >/dev/null 2>&1
timeout 30 adb wait-for-device && ok_shell || { t "server restart failed"; exit 1; }
t "server restart ok"
timeout 20 adb shell 'cat /proc/uptime; dmesg | tail -20' > "$out/devlog.txt" 2>&1
t "done"
