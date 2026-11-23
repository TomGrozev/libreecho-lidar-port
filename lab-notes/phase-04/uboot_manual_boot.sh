#!/usr/bin/env bash
# RAM-boot a pack_boot.py Linux image through a running Lidar U-Boot without
# lidar_bootimg, whose DTB pick fails on unaligned FDTs (libfdt
# FDT_ERR_ALIGNMENT) and which never copies the ramdisk.  The fastboot buffer
# is 0x60100000; offsets of the "amzn,lidar-pvt" DTB and the ramdisk are read
# from the image.  The bootargs below drop the stock LK prefix only.
set -u
LOG=${1:?usage: uboot_manual_boot.sh <log> <image> [boot]}
IMG=${2:?usage: uboot_manual_boot.sh <log> <image> [boot]}
TOOLS=private/lab/phase-03/session-state/20261114/tmp/lidar-android-tools/usr
export LD_LIBRARY_PATH=$TOOLS/lib
fb() { timeout "$1" "$TOOLS/bin/fastboot" "${@:2}" 2>&1 | tee -a "$LOG"; }

read -r DTB_ADDR DTB_SIZE RD_ADDR RD_SIZE < <(python3 - "$IMG" <<'EOF'
import re, struct, sys
b = open(sys.argv[1], "rb").read()
ks, _, rs = struct.unpack_from("<3I", b, 8)
ps = struct.unpack_from("<I", b, 36)[0]
base = 0x60100000
for m in re.finditer(rb"\xd0\x0d\xfe\xed", b[ps:ps + ks]):
    o = ps + m.start()
    size = struct.unpack_from(">I", b, o + 4)[0]
    if b"amzn,lidar-pvt\0" in b[o:o + size]:
        break
else:
    sys.exit("no amzn,lidar-pvt DTB")
rd = ps + -(-ks // ps) * ps
print(hex(base + o), hex(size), hex(base + rd), hex(rs))
EOF
) || exit 1
echo "dtb $DTB_ADDR+$DTB_SIZE ramdisk $RD_ADDR+$RD_SIZE" | tee -a "$LOG"

fb 20 stage "$IMG"
for c in \
  'unzip 0x60100a00 0x40080000' \
  "cp.b $DTB_ADDR 0x4e000000 $DTB_SIZE" \
  "cp.b $RD_ADDR 0x44000000 $RD_SIZE" \
  'setenv b1 console=ttyS0,921600n1' \
  'setenv b2 earlycon=uart8250,mmio32,0x11005000' \
  'setenv b3 clk_ignore_unused lidar.autoreboot=240' \
  'setenv bootargs ${b1} ${b2} ${b3}' \
  'fdt addr 0x4e000000' \
  'fdt get value m / model' \
  'printenv m bootargs'; do
  echo ">>> $c" | tee -a "$LOG"
  fb 20 oem "run:$c"
done
echo ">>> console" | tee -a "$LOG"
for i in $(seq 1 40); do
  out=$(timeout 5 "$TOOLS/bin/fastboot" oem console 2>&1); echo "$out" >> "$LOG"
  case "$out" in *"Empty console"*|*FAILED*) break;; esac
done
[ "${3:-}" = boot ] || { echo "staged; rerun with 'boot' to jump"; exit 0; }
echo ">>> booti $(date -Is)" | tee -a "$LOG"
fb 10 oem "run:booti 0x40080000 0x44000000:$RD_SIZE 0x4e000000"
exit 0
