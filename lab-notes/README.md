# Lab notes

This is my working record of the Lidar port: what I tried in each phase, what the device
did, and which evidence settled it. It is an archive of the work, not a tutorial. To install
LibreEcho on a unit, read
[the install guide](../docs/install-new-lidar.md); for what the port does and does not do
yet, read the project [README](../README.md) and [the status page](../docs/status.md).

## Phases

| Phase | Topic | What it established | Start here |
| --- | --- | --- | --- |
| 0 | Experimental workspace | I had the repositories, host tools and the workspace layout in place before any device work. Host only. | [notes.md](phase-00/notes.md) |
| 1 | Read-only boot-chain inventory | I read stock BOOT0/BOOT1, GPT, tee1, expdb, LK and boot partitions without writing, and pinned down the production Lidar DTB. | [notes.md](phase-01/notes.md) |
| 2 | Boot-chain construction and restore tooling | I built and tested Kaeru, Koboreru and the restore tool on the host against synthetic images. No device was written. | [notes.md](phase-02/notes.md) |
| 3 | Boot chain and fastboot | I proved the restore drill, the custom boot chain install and fastboot on the unit; the chain survived a true power cycle. | [notes.md](phase-03/notes.md) |
| 4 | Kernel and DTB bring-up | I built, packed and brought up the ARM64 kernel and Lidar DTB, and isolated the missing eMMC, USB and entry faults. | [notes.md](phase-04/notes.md) |
| 5 | Platform, install, recovery and OTA | I got LibreEcho-Platform running on Lidar; install, reinstall from the recovery floor and A/B OTA passed on hardware. | [README.md](phase-05/README.md) |
| 6 | Hardware and core feature bring-up | I brought up Wi-Fi, Bluetooth, audio, microphones, buttons, LEDs, UI, voice and the EFR32 radio on 6.18, through the feature sweep and lab OTAs. | [README.md](phase-06/hw-20261121/README.md) |
| 7 | Product integration and production tooling | I rebased the forks onto current upstreams, added production tooling and gates, and built and installed lab OTAs through v0.2.68 alongside read-only device checks. In progress. | [README.md](phase-07/README.md) |
| 8 | Validation and PR preparation | Validation and the drafted PR stack; the Wi-Fi slowdown was traced to the access point the unit joined. In progress. | [notes.md](phase-08/wifi-slowdown-20261126/notes.md) |

Phase state, gates and close dates stay in [the status page](../docs/status.md);
[the port plan](../docs/plan.md) is authoritative for scope and gates.

## Evidence kinds

I keep four kinds of evidence apart, and a hardware claim needs the last one:

- **Host:** a test or build on my workstation; says nothing about the device.
- **CI:** a pass in a repository workflow.
- **Image:** a verifier checking a built boot image.
- **Hardware:** a capture or observation on the Echo Plus 2nd Gen itself.

## Placeholders

Device and personal values appear as placeholders such as `<SERIAL_A>` or
`/workspace/libreecho`; [SCRUB.md](../SCRUB.md) lists them. Some paths the notes mention
were never published, so links into them do not resolve.
