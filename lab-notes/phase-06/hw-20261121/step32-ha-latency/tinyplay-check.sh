
which tinyplay || exit 1
cat /proc/asound/card0/pcm0p/sub0/status | head -1
( i=0; while [ $i -lt 150 ]; do echo "$(cut -d' ' -f1 /proc/uptime) $(awk '/^state|^trigger_time|^closed/' /proc/asound/card0/pcm0p/sub0/status | tr '\n' ' ')"; i=$((i+1)); done > /run/tp-poll.log ) &
sleep 0.2; echo "tinyplay-start $(cut -d' ' -f1 /proc/uptime)"; tinyplay /run/silence.wav -D 0 -d 0 -p 2048 -n 2 >/run/tp.out 2>&1; echo "tinyplay-end $(cut -d' ' -f1 /proc/uptime)"; wait
uniq -f1 /run/tp-poll.log; cat /run/tp.out
