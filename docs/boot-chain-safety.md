# Boot-chain safety

These rules apply to every write on an Echo Plus 2nd Gen (`Lidar`). The port plan
kept them in one section, extracted here; [the port plan](plan.md) records the phases that
follow them, and [the install guide](install-new-lidar.md) repeats them for the install
procedure.

After Kaeru is installed, expdb holds the Kaeru LK stage (MTK magic
`88 16 88 58` at offset 0). The fastboot marker lives in `misc[0:16]`, not expdb. Never
erase expdb and never write `FASTBOOT_PLEASE` there on a v2 chain. Use Kaeru's own reboot
flow and preserve expdb.

The live restore drill runs before Kaeru installation, while expdb still has its stock
contents. After Kaeru installation, the plan does not authorize a stock expdb restore. Any
later stock recovery needs a separately reviewed full-chain BROM procedure. Never restore
expdb alone.

The plan also requires a verified stock backup before the first write, readback
verification after every write, and separate approval before each hardware write or reboot
([the port plan](plan.md), "Safety and evidence rules").
