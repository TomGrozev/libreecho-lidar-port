#!/bin/sh
# Runs on the device, detached. Re-probes the MUSB controller with DMA disabled
# (musb_core.c reads use_dma only at probe, musb_core.c:2481). The configfs gadget
# loses its UDC on unbind; devlog.sh binds it again once adbd has FunctionFS ready.
exec >> /data/libreecho-debug/pio.log 2>&1
dev=musb-hdrc.3.auto
drv=/sys/bus/platform/drivers/musb-hdrc
echo "== pio $(cat /proc/uptime) use_dma=$(cat /sys/module/musb_hdrc/parameters/use_dma)"
sleep 2
echo 0 > /sys/module/musb_hdrc/parameters/use_dma
echo "$dev" > "$drv/unbind"; echo "unbind rc=$?"
sleep 2
echo "$dev" > "$drv/bind"; echo "bind rc=$?"
echo "== pio done $(cat /proc/uptime) use_dma=$(cat /sys/module/musb_hdrc/parameters/use_dma) udc=$(ls /sys/class/udc)"
sync
