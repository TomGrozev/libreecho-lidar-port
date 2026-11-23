#!/bin/sh
# Upload an application GBL to the EFR32 through the Gecko bootloader's own
# XMODEM upload, mirroring reference/lidar-mainline tools/lidar-efr32.sh.
# Only the application area is written, through the bootloader.
#
# Usage: efr32-flash.sh <file.gbl>
#
# Hardware notes for this board:
#  - holding EFR32_SWCLK low keeps the bootloader in its menu;
#  - RESET_N must be driven high again after the low pulse, because the line
#    has no pull-up and a released line holds the chip in reset.
TTY=${TTY:-/run/devtmpfs/ttyS1}
GBL=$1

log() { echo "efr32-flash: $*" > /dev/kmsg; }

[ -r "$GBL" ] || { echo "usage: efr32-flash.sh <file.gbl>" >&2; exit 2; }

stty -F "$TTY" 115200 raw -echo -crtscts -ixon -ixoff || exit 1

# Drop any holder of the two lines, then set the bootloader condition.
killall efr32-gpio 2>/dev/null
sleep 0.5
setsid /run/efr32-gpio set EFR32_SWCLK 0 600 </dev/null >/dev/null 2>&1 &
sleep 0.3
/run/efr32-gpio set EFR32_RESET_N 0 1
setsid /run/efr32-gpio set EFR32_RESET_N 1 600 </dev/null >/dev/null 2>&1 &
sleep 1

# Probe the menu up to three times.
: > /tmp/efr32.rx
exec 3<> "$TTY"
i=0
ok=0
while [ "$i" -lt 3 ]; do
	: > /tmp/efr32.rx
	timeout 1 cat <&3 > /tmp/efr32.rx &
	r=$!
	printf '\r' >&3
	wait "$r"
	if od -An -tx1 -v /tmp/efr32.rx | tr -s ' \n' ' ' | awk '/ 42 4c 20 3e /{f=1} END{exit !f}'; then
		ok=1
		break
	fi
	i=$((i + 1))
	sleep 0.5
done
if [ "$ok" != 1 ]; then
	log "the bootloader does not answer"
	exit 1
fi

log "uploading ${GBL##*/}"
printf 1 >&3	# upload gbl: the bootloader now waits for XMODEM
if ! /run/lidar-xmodem "$TTY" "$GBL"; then
	log "upload of ${GBL##*/} failed"
	exit 1
fi
exec 3<&-

# Start the new application: SWCLK high, reset pulse with the line driven
# high afterwards.
killall efr32-gpio 2>/dev/null
sleep 0.3
setsid /run/efr32-gpio set EFR32_SWCLK 1 86400 </dev/null >/dev/null 2>&1 &
sleep 0.2
/run/efr32-gpio set EFR32_RESET_N 0 1
setsid /run/efr32-gpio set EFR32_RESET_N 1 86400 </dev/null >/dev/null 2>&1 &
sleep 1.5
log "${GBL##*/} uploaded and started"
