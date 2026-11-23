#!/bin/sh
# Send bytes to the EFR32 host UART and print the reply as hex.
# Usage: efr32-exchange <printf-format> <seconds>
# The line must already be configured by the caller (stty), as in
# reference/lidar-mainline tools/lidar-efr32.sh exchange().
TTY=${TTY:-/run/devtmpfs/ttyS1}
[ $# -eq 2 ] || { echo "usage: efr32-exchange <printf-format> <seconds>" >&2; exit 2; }
: > /tmp/efr32.rx
timeout "$2" cat < "$TTY" > /tmp/efr32.rx &
rx=$!
exec 3<> "$TTY"
printf "$1" >&3
wait "$rx"
exec 3<&-
od -An -tx1 -v /tmp/efr32.rx
