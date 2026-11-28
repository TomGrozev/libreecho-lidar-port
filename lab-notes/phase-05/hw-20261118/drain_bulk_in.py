"""Read and discard whatever Kaeru still has queued on the fastboot bulk-in endpoint.

A killed `fastboot fetch` client leaves Kaeru inside a 1 MiB DATA phase; the
next client then reads that payload as a command reply. This sends nothing to
the device.
"""
import usb.core
import usb.util

dev = usb.core.find(idVendor=0x0BB4, idProduct=0x0C01)
if dev is None:
    raise SystemExit('no 0bb4:0c01 device')
intf = dev.get_active_configuration()[(0, 0)]
ep_in = usb.util.find_descriptor(
    intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
usb.util.claim_interface(dev, intf.bInterfaceNumber)
total = 0
try:
    while True:
        try:
            data = bytes(ep_in.read(1 << 20, timeout=2000))
        except usb.core.USBTimeoutError:
            break
        total += len(data)
        if len(data) <= 64:
            print(f'short packet: {data!r}')
finally:
    usb.util.release_interface(dev, intf.bInterfaceNumber)
print(f'drained {total} bytes')
