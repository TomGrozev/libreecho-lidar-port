#!/bin/sh
# Device-side timeline of Home Assistant voice turns, without rebuilding anything.
# esphomed logs nothing, so this stamps (with /proc/uptime, 10 ms) what is visible from outside:
#   waked log lines (wake_event, playback start), live TCP sockets other than 6053/5555
#   (the TTS fetch), esphomed's open fds (fetch socket, speaker FIFO), and
#   esphome-status.json changes.
# Usage on the device: sh probe.sh <out> <seconds>
out=${1:-/run/latency-probe.log}
secs=${2:-180}
L=/var/log/libreecho-waked.log
E=$(pidof libreecho-esphomed)
up() { cut -d' ' -f1 /proc/uptime; }

{
	echo "start uptime=$(up) epoch=$(date +%s) esphomed=$E"
} > "$out"

tail -n0 -f "$L" | while IFS= read -r l; do echo "$(up) waked $l"; done >> "$out" &
tailpid=$!

end=$(( $(cut -d. -f1 /proc/uptime) + secs ))
pc=""; pf=""; ps=""; pa=""
while [ "$(cut -d. -f1 /proc/uptime)" -lt "$end" ]; do
	t=$(up)
	# Live sockets only (skip LISTEN 0A and TIME_WAIT 06); local 17A5 = 6053 (HA API), 15B3 = 5555 (adb).
	c=$(awk 'NR>1 && $4!="0A" && $4!="06" { split($2,a,":"); if (a[2]!="17A5" && a[2]!="15B3") print $2">"$3"/"$4 }' /proc/net/tcp | sort | tr '\n' ' ')
	[ "$c" != "$pc" ] && echo "$t tcp [$c]" >> "$out" && pc=$c
	# The kernel has no per-task I/O accounting; esphomed's fd set shows the fetch socket and the speaker FIFO opening.
	f=$(ls -l /proc/$E/fd 2>/dev/null | awk 'NR>1 {print $NF}' | sort | tr '\n' ' ')
	[ "$f" != "$pf" ] && echo "$t fd [$f]" >> "$out" && pf=$f
	s=$(cat /run/libreecho/esphome-status.json 2>/dev/null)
	[ "$s" != "$ps" ] && echo "$t status $s" >> "$out" && ps=$s
	# The engine opens the speaker PCM only when audio arrives; trigger_time marks the DMA start.
	a=$(awk '/^state|^trigger_time|^closed/' /proc/asound/card0/pcm0p/sub0/status | tr '\n' ' ')
	[ "$a" != "$pa" ] && echo "$t pcm [$a] hw [$(tr '\n' ' ' < /proc/asound/card0/pcm0p/sub0/hw_params)]" >> "$out" && pa=$a
done
kill "$tailpid" 2>/dev/null
echo "end uptime=$(up)" >> "$out"
