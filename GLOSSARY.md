# Glossary

Terms a reader meets in the plan and the experiment notes. Boot-chain terms describe
the Echo Plus 2nd Gen (Lidar) unless stated otherwise.

- **A/B OTA**: An update scheme with two boot slots. The new image installs into the
  inactive slot, boots once unconfirmed, and is confirmed only after a health check;
  otherwise the bootloader falls back to the previous slot.
- **agentd**: The LibreEcho voice assistant daemon. It runs the local assistant turn
  and needs the audio socket from the audio profile.
- **amonet**: The MT8163-era boot-chain exploit toolkit LibreEcho used on earlier
  models. **Koboreru** is its MT8167 successor: a payload loaded through a signed
  preloader that patches the chain in RAM.
- **BCB** (bootloader control block): A small record in the `misc` partition holding
  slot priorities, tries and success flags. On Lidar it sits at `misc` offset 0x360,
  and the stock LK reads it to pick a slot.
- **BOOT0 / BOOT1**: The two eMMC boot partitions. The port installed a signed 2019
  preloader in area 1 of BOOT0 and never writes BOOT1.
- **boot_a / boot_b**: The two 16 MiB boot image slots in the GPT. Each holds a
  kernel, DTBs and the initramfs for one slot of the A/B scheme.
- **BROM** (boot ROM): The first-stage bootloader in the SoC mask ROM. It enumerates
  over USB (`0e8d:0003`) and downloads a payload; it does not verify signatures at
  this stage.
- **CDC ACM**: USB Communications Device Class Abstract Control Model, the serial
  profile of the development root shell (`ttyGS0`).
- **DA** (download agent): The second-stage loader BROM executes to read and write
  eMMC. mtkclient uses a proprietary MediaTek DA; it stays out of production scripts.
- **DTB** (device tree blob): The compiled hardware description the kernel reads at
  boot. A Lidar boot image carries the stock DTBs plus a Lidar DTB.
- **eFuse / SBC / SLA**: One-time programmable fuses in the SoC. SBC (secure boot
  chain) makes BROM verify the next stage's signature; SLA (secure download
  authentication) gates custom download agents. The unit reports secure boot enabled.
- **EFR32 / RCP**: The Silicon Labs EFR32MG21 radio on the board, reached on
  `ttyS2`. It runs one firmware at a time: Amazon's Zigbee NCP (EZSP) or an
  OpenThread RCP (Spinel), a co-processor driven by a host Thread stack.
- **eMMC**: The device's embedded flash storage. The GPT divides it into the
  partitions the boot chain and the system use.
- **ESPHome API**: The protocol that `libreecho-esphomed` speaks on TCP 6053. It lets
  Home Assistant use the speaker as a voice satellite.
- **expdb**: The eMMC partition that holds the Kaeru LK stage on this chain.
- **fastboot**: The USB flashing protocol Kaeru exposes after installation. On this
  chain it can flash and fetch partitions but rejects `fastboot boot`.
- **GPT** (GUID partition table): The partition table on the eMMC.
- **`[INFERENCE]`**: Tag used in the notes for a conclusion drawn from evidence
  without a direct capture proving it. It marks the claim as inferred, not observed.
- **Kaeru**: The custom second-stage bootloader (an LK derivative) LibreEcho
  installs in place of the stock LK. It provides fastboot and boots the slot chosen
  through the BCB.
- **Lidar**: The Amazon codename of the Echo Plus 2nd Gen, used as the target id.
- **LK** (little kernel): The MT8167 third boot stage. The stock LK verifies and
  loads the kernel and DTBs and applies the BCB slot decision; Kaeru replaces it.
- **Main**: The supervising agent in the AI coding workflow this port used, defined
  in `AGENTS.md`. Hardware writes and owner decisions were gated through the human
  owner; see the top-level README, "How this port was worked".
- **MT7668**: The MediaTek Wi-Fi/Bluetooth combo chip, on SDIO. Mainline has no WLAN
  driver for it, so the port carries a GPL driver ported from Amazon's gen4 drop;
  Bluetooth uses mainline `btmtksdio`.
- **MT8167**: The MediaTek ARM64 SoC of the Echo Plus 2nd Gen
  (`ro.board.platform=mt8167`), closely related to the MT8516/MT8163 family used by
  earlier Echo models.
- **preloader**: The first flash-based boot stage after BROM. The 2023 stock preloader
  verifies PL, TEE and LK signatures and enforces RPMB anti-rollback; the port
  replaces it with a signed 2019 preloader (area 1 of BOOT0).
- **ramoops**: A pstore backend that keeps the kernel console in reserved DRAM across
  a warm reboot. On Lidar it sits at `0x43810000`, which Kaeru's `fetch ramoops` can
  read; a cold power cycle loses it.
- **RPMB**: Replay-protected memory block, an authenticated eMMC region used for
  anti-rollback counters. Writing the wrong preloader generation can brick the chain
  against it.
- **Sendspin**: The streaming-audio protocol LibreEcho's Music Assistant player uses.
  The engine stages (`sendspin_stage()`, `render_period()`) appear in audio-engine
  records.
- **tee1 / TEE**: The trusted-execution-environment image (ATF plus OP-TEE). tee1
  sits in its own partition; its header lies outside the preloader's signature, which
  is what Koboreru loads first.
- **Thread / Zigbee**: The two mesh protocols the EFR32 can serve, one firmware at a
  time. Thread ran through an OpenThread RCP with a host `ot-cli`; Zigbee ran through
  the stock NCP over EZSP (EmberZNet 6.5.3.0), driven by the host tool `bellows`.
- **T-PHY**: MediaTek's combined USB/PCIe/SATA PHY (`phy-mtk-tphy.c`), a recurring
  subject in the USB bring-up records.
- **UART**: A serial console. Lidar exposes no UART that can recover a bad boot-chain
  write.
- **UDC** (USB device controller): The gadget-side controller the kernel binds
  functions to (on Lidar, MUSB). UDC rebind behaviour recurs in the adb stability
  work.
- **WMT**: MediaTek's Wireless Management Tool control channel over `/dev/stpwmt`,
  which the MT8163 Bluetooth bring-up uses. The Lidar mainline path skips it.
