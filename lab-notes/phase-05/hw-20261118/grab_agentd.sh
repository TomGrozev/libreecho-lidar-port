#!/bin/bash
# Poll the running boot until agentd's reconcile log exists, then save it with
# the audio socket state.
out=${1:?usage: grab_agentd.sh <file>}
for i in $(seq 1 30); do
  r=$(timeout 20 adb shell 'cat /proc/uptime; ls -l /run/libreecho/audio.sock 2>&1; ls /tmp/libreecho-agentd*.log 2>/dev/null && cat /tmp/libreecho-agentd*.log' 2>&1)
  echo "$r" > "$out"
  case $r in *libreecho-agentd*) exit 0 ;; esac
  sleep 8
done
echo "no agentd log after polling" >> "$out"
exit 1
