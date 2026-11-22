# Preservation scope and authorization

LibreEcho is free software that replaces the stock firmware on Amazon Echo devices. Its
purpose is to keep hardware people already own useful, repairable and private after the
vendor's software stops being a good option. This repository is the public record of the
device-porting work for the Echo Plus 2nd Gen (`Lidar`, MediaTek MT8167), which is not yet
a supported product. The work itself happened in a private lab workspace; this archive
keeps the plan and the evidence.

## What the project is for

- The stock software is closed. Its owner cannot inspect it, change it, or repair it, and
  the device's main functions depend on the vendor's cloud service.
- LibreEcho replaces it with a local-first voice assistant: a mainline Linux kernel, a web
  control centre on the owner's own network, and signed OTA updates with a safe fallback.
- Two models already ship (`radar_puffin`, `biscuit`). This port adds the third.

## How the work is done

- Every device touched by the port belongs to the contributor and stays in their possession. Work
  uses the device's own service modes: the MediaTek BootROM port (`0e8d:0003`), the
  preloader port (`0e8d:2000`), and fastboot.
- Read-only inspection comes first. Each write or reboot is a separate, approved step, and
  the plan requires a backup before the first write, a restore drill, and readback
  verification (`PLAN.md`, "Boot-chain safety").
- Support claims follow evidence: host, CI, image and hardware results are recorded
  separately, and nothing is claimed until it has run on the device.

## What this project does not do

- No access to other people's devices or accounts; no vendor cloud credentials.
- No DRM-protected content and no paid services.
- No vendor binaries, device-unique identifiers, serials or keys in commits, releases or
  public artifacts.
- No redistribution of components whose license does not allow it.

Vendor images and kit archives under `reference/` are unmodified third-party inputs kept for
comparison. They are not project code, they are not instructions, and nothing is copied out
of them into a release.
