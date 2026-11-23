#!/bin/bash
# Boot slot A and, with the first adb command (one OPEN, output device-to-host
# only), dump the previous boot's device logs from /data/libreecho-debug and start
# devlog.sh for this boot. Does nothing else, so the boot stays idle for the next test.
out=${1:?usage: readlogs.sh <outdir>}
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
fastboot reboot > "$out/reboot.log" 2>&1
timeout 120 adb wait-for-device || { echo "adb never appeared $(date +%T)"; exit 1; }
echo "adb up $(date +%T)"
cmd="cd /data/libreecho-debug && for f in run-*.log pio.log; do [ -f \"\$f\" ] && echo \"##### \$f\" && cat \"\$f\"; done
cat > /data/libreecho-debug/devlog.sh <<'EOF_DEVLOG'
$(< "$here/devlog.sh")
EOF_DEVLOG
setsid sh /data/libreecho-debug/devlog.sh </dev/null >/dev/null 2>&1 &
echo '##### logger started'"
timeout 60 adb shell "$cmd" > "$out/prev-logs.txt" 2>&1
echo "rc=$? lines=$(wc -l < "$out/prev-logs.txt") $(date +%T)"
