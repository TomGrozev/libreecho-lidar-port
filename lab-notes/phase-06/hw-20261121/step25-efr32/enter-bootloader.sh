#!/bin/sh
# Try to land the EFR32 in its Gecko bootloader menu: hold SWCLK low, pulse
# RESET_N, then knock on the UART for a few seconds.
TTY=${TTY:-/run/devtmpfs/ttyS1}
HOLD=${1:-60}
stty -F "$TTY" 115200 raw -echo -crtscts -ixon -ixoff || exit 1

setsid /run/efr32-gpio set EFR32_SWCLK 0 "$HOLD" </dev/null >/dev/null 2>&1 &
sleep 0.5
/run/efr32-gpio pulse EFR32_RESET_N 500
sleep 0.5

: > /tmp/efr32.rx
timeout 6 cat < "$TTY" > /tmp/efr32.rx &
rx=$!
exec 3<> "$TTY"
n=0
while [ "$n" -lt 16 ]; do
	printf '\r' >&3
	sleep 0.3
	n=$((n + 1))
done
wait "$rx"
exec 3<&-
od -An -tx1 -v /tmp/efr32.rx
