import re
d = open("/workspace/libreecho/private/dumps/20261110-lidar-readback/lk_a.bin","rb").read()
lines=[]
for off in range(0x32fe0, 0x33070, 16):
    c=d[off:off+16]
    lines.append(f"{off:08x}  {c.hex(' ')}  " + "".join(chr(x) if 32<=x<127 else "." for x in c))
# also print the "selection" string cluster with surrounding bytes
lines.append("")
lines.append("== 0x2c7a0-0x2c960 ==")
for off in range(0x2c7a0, 0x2c960, 16):
    c=d[off:off+16]
    lines.append(f"{off:08x}  {c.hex(' ')}  " + "".join(chr(x) if 32<=x<127 else "." for x in c))
open("/workspace/libreecho/private/lab/phase-01/dtb/lk_window.txt","w").write("\n".join(lines)+"\n")
print("ok")
