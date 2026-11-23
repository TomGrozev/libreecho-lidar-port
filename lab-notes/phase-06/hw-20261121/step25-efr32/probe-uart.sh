#!/bin/sh
# Probe the EFR32 host UART (uart2 = ttyS1 on this image) without writing
# anything: set the line, send a carriage return, print whatever comes back
# as hex.  Mirrors reference/lidar-mainline tools/lidar-efr32.sh exchange().
TTY=${TTY:-/run/devtmpfs/ttyS1}
SECS=${1:-1}
stty -F "$TTY" 115200 raw -echo -crtscts -ixon -ixoff || exit 1
: > /tmp/efr32.rx
timeout "$SECS" cat < "$TTY" > /tmp/efr32.rx &
rx=$!
exec 3<> "$TTY"
printf '\r' >&3
wait "$rx"
exec 3<&-
echo "rx:"
od -An -tx1 -v /tmp/efr32.rx
