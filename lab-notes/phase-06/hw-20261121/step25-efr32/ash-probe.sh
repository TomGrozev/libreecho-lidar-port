#!/bin/sh
# ASH session: reset the link, then send one probe frame, printing the bytes
# received after each step as hex.
# Usage: ash-probe.sh <printf-format-of-second-frame>
TTY=${TTY:-/run/devtmpfs/ttyS1}
stty -F "$TTY" 115200 raw -echo -crtscts -ixon -ixoff || exit 1

exec 3<> "$TTY"
: > /tmp/ash.rst
timeout 2 cat <&3 > /tmp/ash.rst &
r=$!
printf '\032\300\070\274\176' >&3	# ASH CANCEL + RST (CRC 0xBC38)
wait "$r"
echo "rst->"
od -An -tx1 -v /tmp/ash.rst

: > /tmp/ash.reply
timeout 3 cat <&3 > /tmp/ash.reply &
r=$!
printf "$1" >&3
wait "$r"
echo "reply->"
od -An -tx1 -v /tmp/ash.reply
exec 3<&-
