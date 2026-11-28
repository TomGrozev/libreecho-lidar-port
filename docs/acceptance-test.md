# Acceptance test on a second unit

This page maps the final acceptance checklist in [plan.md](plan.md) to the steps in
[install-new-lidar.md](install-new-lidar.md) and to the evidence to send back. It is for an
external tester with a second Echo Plus 2nd Gen. The port has run on one development unit;
this is the first end-to-end run on another unit.

Read the install guide first. It carries the warnings, the safety rules and the exact
commands. Stop at any refusal (exit code 2) and report it. Do not work around a refusal.

## Evidence kinds

Label every result as host, CI, image or hardware. A hardware claim needs a capture from
the unit.

- Host: a command that ran on your workstation, with its output.
- CI: a workflow run URL. The maintainer supplies these.
- Image: a digest or verifier result for a built image or OTA bundle.
- Hardware: a device observation: a log, an API response, a photo or a recording.

## What to send back

One directory with:

1. The preparation session directory from the install guide: `identify` output, the
   `backup/` manifest and hashes, the `PASS` line of the `boot_a` read (step 4), the image
   digests (step 5), `drill-report.json`, `stock-boot-report.json` and `prepare.jsonl`.
   Leave out the `.bin` and `.img` files: they are Amazon firmware.
2. The product installer log from step 11.
3. The update state under `/data/libreecho/update/`: `boot-health`, `boot-history`,
   `installed` and `state`.
4. `SHA256SUMS` and `provenance.json` from the build that was installed.
5. The API captures, photos and notes named in the table.
6. A short note of what worked, what refused, and the exact commands.

Remove serials, MAC addresses and Wi-Fi credentials before you share anything.

## Checklist to steps to evidence

| Checklist item | Steps in the install guide | Evidence to send back | Kind |
| --- | --- | --- | --- |
| Installation from BROM through the one-command path | 1 to 10, or 1 to 6 and then the `run` aside after step 10 | `prepare.jsonl`, the `identify` output, and the `confirm` output showing `product: LIDAR` | host and hardware |
| Boot-chain backups with a passing restore drill | 3 `backup`, 4 `boot_a` read, 7 `drill`, 8 `stock-boot` | `backup-manifest.json`, the step 4 `PASS` line, `drill-report.json`, `stock-boot-report.json`, and a note that the unit booted stock after the drill | host and hardware |
| Recovery and reinstall | 9 `install` after a partial run, or 11 with `one-shot --reinstall`; see Recovery | the rerun log and `boot-history` | host and hardware |
| OTA updates | 11 and 12 | `boot-health` with `state=confirmed`, `boot-history`, `installed` and `state` | image and hardware |
| Networking | 12 | The `adb` output and a `GET /api/v1/network` capture; note DHCP, DNS and one access point | hardware |
| UI | 12 | Photos of the setup page and the Device page; note which views loaded | hardware |
| Audio playback | 12 | A note that you heard the cues and the validation tones, with the volume steps you used | hardware |
| Microphones | 12 | One voice capture, a note for each of the 7 lanes, and the `tinycap` output if you have it | hardware |
| Buttons and LEDs, privacy latch | 12 | Photos of the ring at boot and while latched, and the output of each button test | hardware |
| Evidence separated into kinds | all | Your directory with every result labelled host, CI, image or hardware | host, CI, image, hardware |
| No proprietary data in the return | all | Your confirmation that serials, MACs, keys and credentials are removed | host |
| Licensed components with complete source | 6 and 11 | `provenance.json` and `SHA256SUMS` | image |

The one-command path is the `run` aside after step 10. It needs the images from step 5, so
it cannot start before step 5. Run it with `--dry-run` first, and keep the stock boot
confirmation (step 8) outside it.

## Before you start

- Use a stock unit that has never run this port. Write down its model, region and stock
  build string.
- Have the USB pads, a data cable and a Linux host with the tools in the install guide.
- Keep the stock backup. It is the only way back to stock.
- Do not send the unit, the USB adapter or the storage with your data.

## If a step fails

Report the stage, the exit code, the log and the unit state. A failed install can leave the
unit in Kaeru fastboot; the install guide's Recovery table says what each failure allows.
Do not retry a refused stage with different inputs.
