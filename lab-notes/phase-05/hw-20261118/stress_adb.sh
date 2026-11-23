#!/bin/bash
# Boot slot A, install the device logger with one adb command (inline, no push),
# then stress adb in both directions: first with MUSB DMA (stock), then after a
# runtime switch to PIO. Each failure waits for the logger's gadget rebind.
out=${1:?usage: stress_adb.sh <outdir> [rounds]}
rounds=${2:-20}
here=$(cd "$(dirname "$0")" && pwd)
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
ok_push() {
  timeout 30 adb push "$blob" /tmp/blob.bin > /dev/null 2>&1 || { t "push failed"; return 1; }
  got=$(timeout 15 adb shell 'sha256sum /tmp/blob.bin' 2>&1 | cut -c1-64)
  [ "$got" = "$want" ] || { t "push hash mismatch: $got"; return 1; }
}
recover() {
  t "waiting for rebind"
  if timeout 45 adb wait-for-device && ok_shell; then t "recovered"; return 0; fi
  t "not recovered"; lsusb | grep -E '18d1|0e8d' >> "$out/events.log" || t "not on USB"
  return 1
}
stress() {
  label=$1; fails=0
  for ((k = 1; k <= rounds; k++)); do
    if ok_push && ok_shell; then :; else
      fails=$((fails + 1)); t "$label round $k failed"
      recover || return 1
    fi
    if [ $((k % 5)) -eq 0 ]; then
      adb kill-server; sleep 2; adb start-server > /dev/null 2>&1
      if timeout 30 adb wait-for-device && ok_shell; then :; else
        fails=$((fails + 1)); t "$label server restart at round $k failed"
        recover || return 1
      fi
    fi
  done
  t "$label done: $rounds rounds, $fails failures"
}

# RESUME=1 skips the reboot and logger install (logger already running).
if [ "${RESUME:-0}" != 1 ]; then
fastboot reboot > "$out/reboot.log" 2>&1
timeout 120 adb wait-for-device || { t "adb never appeared"; exit 1; }
t "adb up"
install="mkdir -p /data/libreecho-debug
cat > /data/libreecho-debug/devlog.sh <<'EOF_DEVLOG'
$(< "$here/devlog.sh")
EOF_DEVLOG
cat > /data/libreecho-debug/pio.sh <<'EOF_PIO'
$(< "$here/pio.sh")
EOF_PIO
REBIND=${REBIND:-1} setsid sh /data/libreecho-debug/devlog.sh </dev/null >/dev/null 2>&1 &
echo installed"
r=$(timeout 20 adb shell "$install" 2>&1 | tr -d '\r')
t "install: $r"
[ "$r" = installed ] || exit 1
sleep 2
fi

stress dma || { t "stopped in dma phase"; exit 1; }
if [ "${NOPIO:-0}" = 1 ]; then
  timeout 30 adb shell 'cat /data/libreecho-debug/run-*.log; dmesg | grep -iE "musb|udc|ffs|rebind"' > "$out/devlog.log" 2>&1
  t "done"; exit 0
fi
t "switching to PIO"
timeout 15 adb shell 'setsid sh /data/libreecho-debug/pio.sh </dev/null >/dev/null 2>&1 &'
sleep 8
recover || { t "no adb after PIO switch"; exit 1; }
timeout 15 adb shell 'cat /data/libreecho-debug/pio.log' >> "$out/events.log" 2>&1
stress pio || { t "stopped in pio phase"; exit 1; }
timeout 30 adb shell 'cat /data/libreecho-debug/run-*.log' > "$out/devlog.log" 2>&1
t "done"
