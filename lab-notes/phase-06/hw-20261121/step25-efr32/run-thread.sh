#!/bin/bash
# Bring a Thread network up through the device RCP.
# A pty (bridged to the Echo's UART over adb forward) feeds ot-cli, a host
# OpenThread FTD; we form a fresh dataset and wait for the leader role.
# Output never includes the master key or the network key.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
LOG=${1:-/var/tmp/thread-form.log}
CLI=${CLI:-/var/tmp/ot-host/src/posix/ot-cli}

rm -f /var/tmp/pty-path
python3 "$HERE/ptytcp.py" 127.0.0.1 16638 > /var/tmp/pty-path 2>&1 &
PTPID=$!
for _ in $(seq 1 20); do
	[ -s /var/tmp/pty-path ] && break
	sleep 0.1
done
PTY=$(head -1 /var/tmp/pty-path)
echo "pty=$PTY"
[ -c "$PTY" ] || { echo "no pty"; kill $PTPID; exit 1; }

{
	sleep 1
	echo "dataset init new"
	sleep 1
	echo "dataset commit active"
	sleep 1
	echo "ifconfig up"
	sleep 1
	echo "thread start"
	for _ in $(seq 1 15); do
		sleep 2
		echo "state"
	done
	echo "channel"
	echo "panid"
	echo "extaddr"
	echo "dataset active"
} | LD_PRELOAD="$HERE/ioctl-shim.so" timeout 120 "$CLI" "spinel+hdlc+uart://$PTY" > "$LOG" 2>&1
rc=$?
kill $PTPID 2>/dev/null
echo "rc=$rc log=$LOG"
