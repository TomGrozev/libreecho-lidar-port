# Phase 6 hardware session, 2026-11-21

First boot of the 6.18.64 Lidar kernel, and the rerun of the Phase 4/5 kernel-dependent
checks. Procedure source: `experiments/phase-05/README.md` steps 2-7 and
`experiments/phase-05/hw-20261118/`. Scripts and logs here are copies and adaptations; I
edited no phase-05 file.

Device: Echo Plus 2nd Gen (Lidar, MT8167), adb serial `<SERIAL_A>`, starting on slot `_b` with the
Phase 5 6.1.178 v2 image.

Helpers: `bin/adb` and `bin/fastboot` wrap the saved android-tools build; the workspace root
is resolved from the script location. I used `experiments/phase-06/adb.sh`/`phase-04/fb.sh`
for read-only captures before the wrappers existed.

## Step 1: starting state (read-only). PASS

| Item | Value |
|---|---|
| slot | `androidboot.slot_suffix=_b`, `libreecho.lab=v2` |
| kernel | 6.1.178+ |
| boot_id | `16685468-a96b-4ab9-a391-d63dbd26a0d6` |
| BCB at misc 0x360 | `00 41 42 42 01 8e 8f 00 ...` = slot A priority 14 tries 0 success 1, slot B priority 15 tries 0 success 1 |
| boot_a sha256 | `9da8886ca63696c5dc13f968f356f499732c072b1dec5d991df8d025737a239a` |
| boot_b sha256 | `7e73d1b800cfa46aee50abe6cf580f8e5927d8777801c3a2fcb0339d48f8c4b0` |
| misc sha256 | `1c53c1f0ab54c0151c3205b986540fa4fbd8119840be973fb08bb52e90a630bd` |

Logs: `step1-state/state.log`. I read the hashes from the device block nodes
(`sha256sum /dev/mmcblk0p10 /dev/mmcblk0p11`) on 6.1, and they matched the Phase 5 values.

## Step 2: flash boot_a and verify. PASS

Commands (`step2-flash.sh`):
`libreecho-bootctl activate a`; `libreecho-bootctl reboot-bootloader` (watchdog NONRST2
route, landed in Kaeru 2.0.0-g66704e6-dirty); `fastboot oem fetch-enable`;
`fastboot flash boot_a artifacts/phase-06/images/boot-lidar-dev.img`;
`fastboot fetch boot_a|boot_b|misc` and sha256.

| Partition | Readback sha256 | Verdict |
|---|---|---|
| boot_a | `e702f095df11fb2c4005f45d62d3dccc7879f10be4f05dad5ae296493e9274a1` | matches the image |
| boot_b | `7e73d1b800cfa46aee50abe6cf580f8e5927d8777801c3a2fcb0339d48f8c4b0` | unchanged fallback |
| misc | `60e3d3358ffb327118ea5da32d423cb98bc288bd2c515be6855b534c0c65507d` | changed by `activate a` only |

I then issued `fastboot reboot` with slot A selected (A priority 15 tries 3 success 0,
B priority 14 tries 0 success 1).

## Step 3: boot slot A on 6.18. FAIL (stopped here)

### Boot 1, image `e702f095…` (first-boot image; superseded)

`uname -r` reported `6.18.64+`, so the kernel booted. `libreecho.lab=dev` was on the
command line, not `libreecho.lab=p6-dev` (the marker bug is fixed in the rebuilt images).
`libreecho-bootctl status a` failed with `ERROR: /dev/mmcblk0p8 is not a block device`
because no MSDC host had probed. The first full state capture hung for 300 s, then
`adb shell` returned `error: closed` and the unit vanished from adb while still on USB
(`18d1:d001`, device 066). Main identified the root cause of the missing eMMC: the board
DTS overrides both MSDC nodes with a compatible only the 6.1 mtk-sd matched. I rebuilt the
DTB on `fix/lidar-6.18-boot` `a8e7d8264ce7`.

### Boot 2, image `c383c600…` (new DTB). FAIL: adb dies on the first shell

From Kaeru fastboot: `fastboot flash boot_a` then fetch. boot_a readback
`c383c60030cc64b28321b2bd35a530986ca8d7c4819f1f4760b554fdd5344ae1` matched the image;
boot_b readback `7e73d1b8…` unchanged. BCB set-active A through `lidar_install.py bcb
set-active A` (A 15/3/0, B 14/0/1, one byte changed at 0x360), then `fastboot reboot`.

`grab.sh` waited for adb: `get-state` answered `device` at 13:32:03. The very first shell
read, `id; uname -r; cat /proc/uptime` with a 20 s timeout, returned rc=124; every later
command (cmdline, dmesg, partitions, mmc, deferred, mounts, bootctl) returned `adb: no
devices/emulators found`. The unit still enumerates on USB as `18d1:d001` (device 074).
Fastboot is not active either (`fastboot devices` empty), so no `fetch ramoops`, dmesg,
partition list or bootctl state could be captured for this boot.

That isolates the failure to the adb/functionfs path on 6.18: the gadget enumerates and
adbd accepts the host connection, then the first shell spawn wedges adbd. Whether eMMC and
MT7668 SDIO now probe is unknown because dmesg was not obtained.

Logs: `step3c-boot2/flash.log`, `bcb-set-active.log`, `events.log`, `grab.sh`, plus empty
or one-line captures for the commands that failed.

I ran no Phase 4/5 rerun (ACM, ADB stress, pstore, reboot-to-fastboot, A/B fallback),
started no OTA, and never wrote boot_b.

## Device state at hand-off

Booted on slot A, `6.18.64+`, `libreecho.lab=p6-v1` (v1 image `f56aa977...` in `boot_a`),
adb up. BCB: A `14/0/1` confirmed, B `0/0/0` (unbootable after the failed OTA confirm);
`boot_b` holds the v2 image `6e262b20...` written by the OTA. I ran no production OTA.

## Step 4: ramoops fetch in Kaeru (read-only). No 6.18 console recovered

After I held Action through a cold power cycle, the unit was in Kaeru fastboot. I ran
`step4-ramoops/fetch.sh`: `oem fetch-enable`, `getvar partition-size:ramoops` (`0x60000`),
`fastboot fetch ramoops` -> `step4-ramoops/ramoops.bin` (393,216 bytes, sha256
`c6ba2b2d06d691f22421a6688e9083f51ea5fef855cf01bb66c8be691bafa859`).

Scan (`step4-ramoops/analysis.txt`): no `DBGC` header and no `Linux version`, `6.18.64`,
`libreecho`, `pstore`, `msdc`, `mmc0` or `adbd` text. Every byte is non-zero but the content
is a repeating 32-bit pattern, so it is decayed DRAM and not a pstore zone.

Verdict: the boot-2 6.18 kernel console did **not** survive the cold cycle. Only a warm
reset from the running 6.18 system (`libreecho-bootctl reboot-bootloader`) leaves ramoops at
`0x43810000` readable in Kaeru. I left the device in Kaeru fastboot and did not reboot into A.

## Boot 3: 6.18 with the MUSB rx_kick fix (PASS)

I flashed dev image `99e6e10b...` (kernel `6c0f771e...`, built from `fix/lidar-6.18-boot`
`15e16539a61d`) to `boot_a`; the readback matched and `boot_b` was still `7e73d1b8...`.
`set-active A` refused because slot A was selected but unconfirmed, so the boot consumed the
last try. I ran `libreecho-bootctl confirm a` immediately after boot; slot A is now `tries=0
success=1`, B `success=1`.

ADB held for every command, including the first push. Evidence in `step3d-boot3/`:
- `dmesg.txt` (296 lines, 6.18.64+): eMMC `mmc0` HS200 7.13 GiB with all 16 partitions,
  `mmc1` SDR104 SDIO card, fn1 `037a:7608` and fn2 `037a:7668`, `btmtksdio` bound to fn2 and
  `hci0` up, machine model MT8167B.
- `audio.txt`: ALSA card 0 `amazon-lidar`, playback and two captures.
- `net_input.txt`: `gpio-keys` as `input0`; only `lo`/`sit0` (WLAN has no driver yet, Phase 6
  work); `amz_privacy` registered in dmesg.
- `leds_pstore.txt`: 12 ring LEDs x 3 colours under `/sys/class/leds`.
- `stress/`: 10 host-to-device 1 MiB pushes and 10 pulls all hash-clean, adb server restart ok.
- `ramoops-warm.bin`: after `libreecho-bootctl reboot-bootloader`, ramoops holds the 6.18
  console (`DBGC` x3, `Linux version 6.18.64+`, marker `P6-PSTORE-MARKER`); booting back to A
  shows `console-ramoops-0` and `pmsg-ramoops-0` in `/sys/fs/pstore`.
- `boot4.txt`: back on A, `selected_slot=a`, `slot_a_success=1`.
- `dmesg-scan.txt`: `mtk-power-controller` domain 4 fails `-110`, `tsl2540` fails `-22`,
  vendor WLAN init logs `num_different_channels` and `prGlueInfo is NULL` (no driver port
  yet), `mt7668_sdio` probe deferred before the firmware import and never rebound, no
  WARN/oops.

ACM shell and A/B fallback followed in the Step 4 sections below.

## Step 4: A/B fallback on 6.18 (PASS)

`step4-ab-fallback.sh`, logs in `step4-ab-fallback/`. I started on A (A `15/0/1`, B `14/0/1`),
`activate b` set B `15/3/0`, A `14/0/1`. Boots 1 to 3 ran slot B (`6.1.178+`,
`androidboot.slot_suffix=_b`), boot 4 returned to slot A on `6.18.64+` with
`libreecho.lab=p6-dev`. LK therefore exhausted B's tries and fell back to the confirmed A.
Final BCB: A `14/0/1` confirmed, B `0/0/0` (LK marked it unbootable after the fallback);
`selected_slot=a`.

## Step 4: ACM shell on 6.18 (PASS)

I rebuilt the Phase 4 ACM diagnostic initramfs image with the 6.18 kernel and DTB, using the
unchanged `experiments/phase-04/pack_boot.py`:
`artifacts/phase-06/acm/boot-lidar-acm-618.img`, sha256
`2c39e2ea66c8c65a9145b123ff8065c4fa922b897167c2271f2a826f9186bcf3`, `--verify` OK. I built it
with Image `6c0f771e...`, DTB `049ae29a...`,
`artifacts/phase-04/initramfs/lidar-test-initramfs-setsid.cpio.gz`
and `--cmdline-append clk_ignore_unused`; the builder needed no source changes.

I flashed it to `boot_a`, the readback matched, and it booted. Over `/dev/ttyACM0` the Phase 4
helper
(`experiments/phase-04/acm_shell.py`, now with a `USBDEVFS_DISCONNECT_CLAIM` fallback for the
host's bound `cdc_acm`) ran `uname -a` -> `Linux (none) 6.18.64+ #5 SMP ... aarch64`, the full
6.18 cmdline, uptime 100 s, `/sys/fs/pstore` with `console-ramoops-0` and `pmsg-ramoops-0`,
and wrote `P6-ACM-MARKER` to `/dev/kmsg`. Logs: `step4-acm/acm-shell.log`, `acm-host.log`.

Return to fastboot: no software path from that initramfs uses `libreecho-bootctl`, and the
kernel `RESTART2 "bootloader"` notifier alone does not arm Kaeru (verified: a tiny helper
rebooted back into the dev image). The proven Phase 4 watchdog sequence via busybox `devmem`
(`0x10007008` kick, `0x10007024` bit 2, mode `0x22000014`, SWRST `0x1209`) did reach Kaeru
fastboot (`step4-acm/`). I then reflashed `boot_a` with the dev image `99e6e10b...` and the
readback matched. The device booted back on A, 6.18.64+, adb up; A `14/0/1` confirmed.

## Step 5: OTA v1 to v2 on 6.18 (install and boot PASS, confirm FAIL on agentd)

`ota_step6_618.sh`, logs in `step6-ota-618-run3/` (runs 1 and 2 failed on fastboot entry and
a relative-path bug before any device write beyond `boot_a`; see their `events.log`).
Setup: `libreecho-bootctl reboot-bootloader` from the dev image reached Kaeru; I flashed the
v1 image `f56aa977...` to `boot_a`, read it back identical, and booted it
(`6.18.64+`, `libreecho.lab=p6-v1`, `_a`). From there I pushed the v2 generation
`txn-505d0389288fc4f9de2112c3` and bundle `lidar-lab-v0.2.14.ota.tar` (`398b9843...`) and ran
`libreecho-update install`, which reported
`verify_rc=0 ota_manifest_signature=PASS UPDATE_READY slot=b version=0.2.14 install_rc=0`
(`install.log`). The next boot ran slot B: `6.18.64+`, `libreecho.lab=p6-v2`, `_b`, audio
profile active, features staged.

Confirm failed at the `ota-confirm` step on all three probes: `failure-236-1.log` and
`/data/libreecho/update/boot-health` record `last_check=ota-confirm`,
`detail=ota-confirm:ERROR:feature_target_not_ready`. The init log shows the cause:
`feature-reconcile-service-ready:waked/sttd/airplayd/ttsd`,
`feature-reconcile-service-start-failed:agentd:1`, so startup-ready never appeared and the
probe ran degraded. A manual `/etc/init.d/libreecho-agentd.init start` was still waiting on
its dependency sockets after 90 s; `/run/libreecho` had `stt.sock`, `audio.sock`, `tts.sock`
but no `wakeword.sock`, and no `waked` process was alive on that boot. Wake word had been
reported ready on the first B boot, then was gone; the assistant's audio gate therefore
cannot be satisfied and `libreecho-update confirm` refuses with `feature_target_not_ready`.
Network was also absent (`wifi-worker-failed`, only `lo`), which the assistant needs, but the
recorded failing check is the agentd service start, not the UI or data plane.

No confirm rule was changed. LK exhausted slot B's tries; the device is back on slot A,
`6.18.64+`, `libreecho.lab=p6-v1`, BCB `selected_slot=a`, A `14/0/1` confirmed, B `0/0/0`.
`boot_b` holds the v2 image written by the OTA, but the BCB marks it unbootable. `/data`
survived: the existing generation `txn-508529626fbd711fdbf6bf1c`, `/data/libreecho/config`
and the feature payload hashes are unchanged (`data-before.log` vs `data-after.log`); only
the OTA state, boot counters and the new generation/bundle were added. Final status still
reports `state=boot-validating`, `ota_transaction_state=pending` for transaction
`txn-505d0389288fc4f9de2112c3`.

## Step 7: Wi-Fi on 6.18 (PASS) and waked (root cause found, not fixed)

**Wi-Fi PASS.** The v1 image had no `/sbin/wpa_supplicant`, so `libreecho-wifi` exited 3
(`supplicant-missing` in `/tmp/wifi.log`) even though `mt7668_sdio` bound `mmc1:0001:1` and
`wlan0` existed. I fixed it on `feature/lidar-support` commit `c07b4fab00`: a new builder flag
`--wpa-supplicant` stages a static ARM32 wpa_supplicant 2.10 at `/sbin/wpa_supplicant`, the
verifier pins it, and `build_images.sh` passes both. The binary (sha256 `43b2933a...`) is in
`artifacts/phase-06/components/wpa-supplicant/`; `udhcpc` was already the BusyBox applet.
Rebuilt images: dev `3be0ce42...`, v1 `7b37a6ef...`, v2 `94256765...`, all
`lidar_recovery_image_contract=PASS`. I flashed the new v1 to `boot_a` (readback identical); it
boots `6.18.64+`, `libreecho.lab=p6-v1`, `_a`. With
`/data/libreecho/config/wpa_supplicant.conf` (0600, contents never printed), init logged
`wifi-profile-present`, `lidar-bt-ready-before-wlan`, `lidar-wlan-bound:mmc1:0001:1`,
`wifi-client-rc:0`, `wifi-activation-complete:0`; `wlan0` is UP with DHCP
`<DEVICE_IP_A>/26` via `<LAN_GATEWAY_A>`, and DNS resolves `example.com` via `<LAN_GATEWAY_A>`.
Gateway ping works; external ICMP is blocked on this network (1.1.1.1 and 8.8.8.8 time out)
and port 80 to the resolved address was refused, so IPv4 TCP reachability beyond DNS is not
proven. Logs: `step7-wifi/` (`after-boot.txt`, `wifi-detail.txt`, `wifi-rc3.txt`,
`wifi-up.txt`, `agent-wake-state.txt`).

**waked root cause.** `waked` starts, then exits 255 about six seconds later with
`waked: microphone stream: Protocol error`, zero frames, and removes `wakeword.sock`;
manual rerun reproduces it (`/var/log/libreecho-waked.log`, `step7-wake/waked-diag.txt`).
`micd` runs with `--capture-bin /sbin/tinycap`, but `/sbin/tinycap` is absent from the image
(`step7-wake/audio-diag.txt`), so capture cannot open and micd answers EPROTO. This is the
same class of image gap as the missing supplicant: the Lidar builder never stages the tinyalsa
tools (`tools/mt8163-arm32/audio-tools/build_audio_tools.sh`), and `build_components.sh`
builds no tinyalsa binary. Not fixed in this run (budget stop); my next step was to build
tinyplay/tinycap/tinymix for ARM32 musl and stage them with a verifier pin, then recheck
waked for five minutes.

**OTA rerun not done.** The rebuilt images change the v1/v2 boot hashes, so
`experiments/phase-06/ota/build_ota.sh` must regenerate both bundles before the Phase 5
step 6 procedure is rerun. The previous run (`step6-ota-618-run3/`) failed confirm with
`detail=ota-confirm:ERROR:feature_target_not_ready` because `agentd` did not start; with
waked/tinycap fixed and Wi-Fi up, that check should be retried.

## Step 8: tinyalsa tools and waked on 6.18

Step 7 confirmed the root cause: `micd` starts with `--capture-bin /sbin/tinycap`, and the
ramdisk never staged any tinyalsa tool, so every capture attempt returned EPROTO and waked
exited 255. I fixed it on `feature/lidar-support` commit `fc8e3c2a3e`: builder options
`--tinyplay/--tinycap/--tinymix` stage the pinned MT8163 audio-tools build at `/sbin` and
record each ELF contract; the verifier pins all three with `--expected-tiny*-sha256` and
`build_images.sh` passes them. Binaries from `build_audio_tools.sh` (pinned TinyALSA
`e43025bb`, kernel UAPI from the same kernel tree): tinycap `eabe84ef…` 71,056 B, tinymix
`7310a2f7…` 50,324 B, tinyplay `e31e4979…` 75,296 B, all static ARM32.

Rebuilt images: dev `1888cce6…`, v1 `856a9f81…`, v2 `692b5757…`, all verifier PASS.

I flashed the new v1 to `boot_a`, readback identical; the boot cmdline was
`libreecho.lab=p6-v1`, `_a`.

On the device `/sbin/tinycap`, `/sbin/tinymix` and `/sbin/tinyplay` exist (71,056 / 50,324 /
75,296 B). `micd` (pid 3611, `--capture-bin /sbin/tinycap`) and waked start from the wakeword
feature payload; `wakeword.sock` and `mic.sock` exist. waked logged `waked: running (16 kHz,
frame=10 ms, AEC tail=200 ms, preroll=3 s, vad-floor=16 RMS, wake=openwakeword-onnx)` and kept
that line only; on SIGTERM it reported `frames=22465 aec_frames=0 vad_active_frames=15115
wake_scores=1931 wake_events=0 max_wake_score=0.047701 ... wake_failed=false` after 224 s,
with a second restart losing 25 s per the log and a later direct soak recorded in
`step8-audio/waked-5min3.txt` and `waked-stop3.log`. `tinycap -D 0 -d 1` reports Resource
busy because micd holds the capture PCM, which is independent proof the capture device is
open and serving.

Logs: `step8-audio/` (`events.log`, `v1-hashes.txt`, `audio-after-boot.log`, `state*.log`,
`capture-test*.log`, `waked-5min*.txt`, `waked-stop*.log`).

## Step 9: OTA v1 to v2 rerun on 6.18 (PASS)

`ota_step6_618.sh`, logs in `step9-ota/`. The v1 image `856a9f81...` was already on `boot_a`
from Step 8; I reflashed it through Kaeru (`flash-v1.log`, readback identical in
`v1-hashes.txt`), booted `6.18.64+` / `libreecho.lab=p6-v1` / `_a`, and installed the v2
generation `txn-7303218adf4646e5decf1908` from the local bundle (`push-gen.log`,
`push-tar.log`). `install.log`: `verify_rc=0 ota_manifest_signature=PASS UPDATE_READY slot=b
version=0.2.14 install_rc=0`. The next boot ran slot B: `6.18.64+`, `libreecho.lab=p6-v2`,
`androidboot.slot_suffix=_b`.

Confirm ran and succeeded on that boot. `/tmp/ota-confirm.log` holds `UPDATE_CONFIRMED
slot=b`; the init log shows `feature-reconcile-service-ready:waked/sttd/airplayd/ttsd/agentd`,
`feature-services-reconciled`, `ota-health-probe-passed:1..3` and `ota-slot-confirmed`;
`/data/libreecho/update/boot-health` is `state=confirmed`, `running_slot=b`,
`last_check=none`, `boot_count=59`. Final evidence: `step9-ota/verify-final.log`.

| Item | Value |
|---|---|
| boot-health | `confirmed`, `mode=ota`, running/selected `b`, `last_check=none` |
| BCB | selected `b`, A `14/0/1`, B `15/0/1` |
| misc sha256 | `1c53c1f0ab54c0151c3205b986540fa4fbd8119840be973fb08bb52e90a630bd` (BCB at 0x360 `00 41 42 42 01 8e 8f 00`, same layout as Step 1) |
| boot_a sha256 | `856a9f81f0270a561e313dcfa43596b6370b41abb453278f0c036d9ce9d954cb` (v1) |
| boot_b sha256 | `692b575709b111ed6688840168f525633ef09ab2fa40acaec4ced7e4f72a5b99` (v2) |
| update state | `state=installed progress=100 detail=b`, `current=generation=txn-7303...`, `previous=txn-5085...`, no `pending` |
| features | all five `effective=present`; `libreecho-agentd` (pid 9507), `waked`, `sttd`, `ttsd`, `libreecho-audio-engine` running |
| Wi-Fi | `wlan0-ready-recorded`, `wifi-activation-complete:0` |

`/data` was preserved (`data-diff.txt`): `config/web-config.json`,
`config/wpa_supplicant.conf`, `config/led-state.json` and the payload/manifest hashes of the
retained `txn-5085...` generation are unchanged. Only the expected OTA records changed: the
new generation `txn-7303...` was added, `txn-505d...` was pruned, `staging/` retains the v2
write/BCB files, and `incoming/` is empty after the install.

Three fields in `libreecho-update status` look like a failed run but are not live state:

- `events.log:7` was captured while the transaction was still `pending`/`state=boot-validating`.
  The poll matched `transaction_id` from the pending record plus `slot_b_success=1`, but
  `libreecho-update confirm` writes the BCB (`bootctl confirm`) *before* the feature commit
  and the `installed` state (`libreecho-update:621-625`), so both appear mid-confirm. The
  harness now waits for the terminal record: `state=installed`, `generation=` and `current=`
  equal to the transaction, `slot_b_success=1`, and no `ota_transaction_pending=1`. That
  condition matches the recorded terminal state (`verify-final.log`).
- `restart_record=1 reason=ota-health-confirm-failed ... epoch=237
  failure_log=failure-236-1.log` is run3's record, written by the failure branch
  (`libreecho-init:3573-3597`). `epoch=237` is `1970-01-01 + 237 s` (the clock was unset on
  that boot); it is persistent triage evidence for Issue #41 and is not rewritten on a later
  success.
- `ota_transaction_state=rollback` / `ota_transaction_rollback=1` comes from the retained
  `/data/libreecho/update/rolled-back` marker of run3 (`txn-505d...`). The marker is rollback
  history by design: `transaction_status()` only lets a live `pending`/`commit` mask it
  (`libreecho-update:460-476`, commit `2114114db`), and a successful confirmation does not
  delete it. It does not name a live transaction: the pending record is gone and the
  generation is the confirmed `txn-7303...`.

No Platform change was needed; the only edit I made is the terminal-state check in
`ota_step6_618.sh` (syntax-checked, `bash -n`). I left the device booted on confirmed slot B.

## Step 10: validations that need no physical step (networking, Bluetooth, LEDs, UI, recovery, updates)

I started on confirmed slot B, `6.18.64+`, `libreecho.lab=p6-v2`, adb up. Every check below
uses the LAN-only test network; no external egress is expected.

**Networking: PASS.** Before and after a normal software reboot (`adb reboot`/busybox
`reboot`, adb back at ~4 s uptime), `wlan0` is UP and associated, DHCP `<DEVICE_IP_A>/26` via
`<LAN_GATEWAY_A>`, default route present, DNS resolves `example.com` via `<LAN_GATEWAY_A>`, and the
gateway answers ping with 0% loss. `ip link set wlan0 down` then `up` re-associated
(`CTRL-EVENT-CONNECTED`) and kept the lease; `/etc/init.d/libreecho-networkd.init restart`
started a new `wpa_supplicant` (pid 808) and the same address, gateway and DNS worked 25 s
later. `startup-ready` and `wlan0-ready` both appear after the reboot; `startup-ready` is
late (~134 s) because the web init waits on `agent.sock`. Logs: `step11-net/` (`pre-reboot.log`,
`post-reboot.log`, `link-flap.log`, `supplicant-restart.log`).

**Bluetooth: FAIL (software).** `btd` is ready and registers SDP/A2DP-sink/AVRCP, and
`hci0` exists under `/sys/class/bluetooth`, but the adapter is not enabled:
`GET /api/v1/bluetooth` reports `enabled=false`, `activation_attempted=false`, `hci=none`.
`PUT /api/v1/bluetooth {"enabled":true}` returns 501 and the next status records
`state=activation-attempted`, `last_error=wmt_configure failed`; `POST /api/v1/bluetooth/scan`
returns 501 ("discovery could not start"). Step 3d had `hci0` up on 6.18, so this is a
regression on this boot, most likely the MT7668 combo `wmt`/WLAN coexistence path when WLAN is
already active. I did not investigate it further in this run. Logs: `step13-ui/bt-test.log`.
(A foreground `libreecho-btd` probe left a second instance; `init stop`/`start` restored one
instance, `step13-ui/btd-fix.log`.)

**LEDs: software PASS, visual result unverified.** All 36 channels are writable through
`/sys/class/leds/ring{1..12}:{red,green,blue}/brightness` (max 255): all-red, all-green,
all-blue and mixed white wrote 255/128 and read back exactly, then all channels were set to 0;
dmesg has `is31fl32xx 0-003f: LibreEcho 36-channel atomic frame interface ready`
(`step12-leds/sysfs-test.log`). The daemon path also works: `PUT /api/v1/led` (blue, 80%) and
`POST /api/v1/led/test` return 200, `ledd` logged the green startup animation, and the new
colour is in `GET /api/v1/led` and `/data/libreecho/config/led-state.json`
(`step13-ui/api-test.log`). I still need to confirm it visually.

**UI: PASS for serving and control API.** `GET /` serves the setup page (200, 12,715 bytes);
`/api/v1/config` reports `bootstrap-required`, `LibreEcho OS 0.14.5`. I created a temporary
local account through `POST /api/v1/auth/bootstrap` to exercise the authenticated API
(`/api/v1/status` with `features_state=ready`, LED endpoints as above, Bluetooth endpoints),
then I removed the users file and the daemon is back to `bootstrap-required` with `GET /`
and `/api/v1/config` working (`step13-ui/after-cleanup.log`, `final-ui.log`). Caveat: the
web init's startup gate needs both `agent.sock` and `startup-ready`, which took ~134 s this
boot. Logs: `step13-ui/`.

**Reboot and recovery entry: PASS for the software paths.** Normal reboot returns on the
confirmed slot B (above). `libreecho-bootctl reboot-bootloader` from B landed in Kaeru
fastboot `2.0.0-g66704e6-dirty`, `product: LIDAR`; `fastboot reboot` returned to slot B,
`_b`, `6.18.64+`, `libreecho.lab=p6-v2`, BCB `selected_slot=b`, `slot_b_success=1`
(`step14-recovery/reboot-bootloader.log`, `final-state.log`). `fastboot fetch misc` was not
captured (Kaeru needs `oem fetch-enable` first; the fetch produced an empty file, deleted).
The Action-held button-combo recovery entry needs me at the unit, and it remains untested in
this run.

**Updates: already evidenced, not rerun.** Step 9 covers the v1→v2 install, boot, health
probe and confirmed slot on 6.18. The failed-confirm rollback is the run3 result recorded
under Step 5/`step6-ota-618-run3/` (`feature_target_not_ready`, LK fallback to A). The A/B
tries fallback is Step 4/`step4-ab-fallback/`. No new OTA or feature-payload update was run
here; the current device reports `state=confirmed`, `boot_count=60`, no pending transaction.

Final state: slot B, `6.18.64+`, `p6-v2`, BCB B `15/0/1` A `14/0/1`, adb up, Wi-Fi
associated with gateway and DNS working, `startup-ready` present.

## Step 15: Bluetooth (mainline btmtksdio on Lidar)

**Root cause of the Step 10 Bluetooth failure.** `libreecho-init:1204-1208` creates the
`/dev/stpwmt` WMT nodes and the Bluetooth character device on every target, so `btd`'s
`wmt_present()` gate was true on Lidar and it ran the MT8163 WMT activation helpers. The
Lidar kernel runs the mainline `btmtksdio` driver, which brings up `hci0` itself, so
`wmt_configure` failed and the adapter stayed disabled (`last_error=wmt_configure failed`,
`hci=none`). LibreEcho-UI `c09551f3618b` (`btd: use the mainline btmtksdio controller on
Lidar`, `src/adapter/btd.c`) selects the transport from the image target file
(`target_id=lidar`) instead of `/dev/stpwmt`, skips the WMT helpers there and powers the
controller at startup; MT8163 keeps its WMT choreography.

**Flash and boot: PASS.** I booted the confirmed slot B, entered Kaeru with
`libreecho-bootctl reboot-bootloader`, flashed `artifacts/phase-06/images/boot-lidar-v2.img`
(`9587e2b99891c112044d1c3751d5415d522cd28478de3e6031782698de571b97`) to `boot_b`, fetched it
back (`oem fetch-enable` + `fetch boot_b`) and the readback hashed to the same value.
`fastboot reboot` returned on B with `6.18.64+`, `androidboot.slot_suffix=_b`,
`libreecho.lab=p6-v2`; `/dev/mmcblk0p11` hashes to `9587e2b9…` too. Slot B stayed selected
and confirmed, BCB `selected_slot=b`, B `15/0/1`.

**Bluetooth: PASS (with two environment/sequencing caveats).** `hci0` is bound through the
mainline `mt7668_sdio` -> `btmtksdio` path; dmesg shows `Bluetooth: MGMT ver 1.23`,
`hci0: Firmware already downloaded` and `Device setup in 14036 usecs`, and btd logs no WMT
helper attempt. Through the UI API (`step15-bt/bt-test.py`, temporary account created and
removed) `PUT /api/v1/bluetooth {"enabled":true}` returns 200 with `state=up`,
`enabled=true`, `hci=hci0`, `transport=mainline-btmtksdio-hci`; the status is already up
within the first 1 s poll. Profile registration is `profile_state=ready` with
`sdp`, `a2dp_sink` and `avrcp` true ("SDP, A2DP sink, and AVRCP profile services
registered"). `POST /api/v1/bluetooth/scan` returns 200 and `scanning=true` for ~10-15 s
before the daemon's inquiry window ends; the discovered list stayed empty in this
environment, so "nearby devices listed" is unverified rather than failed. Interleaved
discovery is rejected (`MGMT_OP_START_DISCOVERY` 0x0023, status 0x0b) and btd falls back to
classic BR/EDR inquiry, the behaviour documented in `btd.c` for controllers whose LE scan
is disabled. A `POST /api/v1/bluetooth/scan/stop` after the window returns 501 because
discovery is already stopped.

Discoverable: the plain `PUT /api/v1/bluetooth {"discoverable":true}` returns 501. The
kernel rejects `MGMT_OP_SET_DISCOVERABLE` with `MGMT_STATUS_REJECTED` when
`HCI_CONNECTABLE` is clear (`net/bluetooth/mgmt.c`), and btd's standalone discoverable
setter does not set connectable first; this path is independent of the Lidar/WMT change.
The UI pairing flow works: `POST /api/v1/bluetooth/pairing-mode {"enabled":true}` returns
200 with `pairing_mode=true`, `capabilities.connectable/discoverable/bondable=true` and
`local_name=LibreEcho`, and it disables cleanly. The adapter `address` field stays empty in
status (not part of the acceptance).

**Wi-Fi coexistence: PASS.** While the 30 s scan was running, `wlan0` stayed UP at
`<DEVICE_IP_A>/26` with the default route, gateway ping was 0% loss (1.0-1.6 ms) and
`nslookup example.com <LAN_GATEWAY_A>` resolved. `wlan0-ready` and `startup-ready` are present.

**Cleanup and final state.** I removed the `phase6-verify` users file and restarted
`/etc/init.d/libreecho-web.init`, which restored `authentication=bootstrap-required`,
`user_count=0`, `GET /` serving. I deleted both host probes `/tmp/le-mgmt-probe`,
`/tmp/le-btd-probe` and their device copies. The device is on slot B with the new v2 image,
adb up, Wi-Fi associated with gateway and DNS working. BCB record `00 41 42 42 01 8e 8f`, misc
sha256 `1c53c1f0ab54c0151c3205b986540fa4fbd8119840be973fb08bb52e90a630bd`.

Logs: `step15-bt/` (`bt-test.log`, `bt-pairing.log`, `btd-device.log`, `wifi-coexist.log`,
`bcb-final.log`, `cleanup.log`).

## Step 16: speaker volume (PASS)

**Root cause.** `PCM Playback Volume` writes reached the codec but mostly not page 0. The
AIC32x4 page-select register is write-only and reads back `0x00` on every page
(`step16-audio/volume-debug/raw-regs-1.log`). regmap's `_regmap_select_page` switches pages
with `_regmap_update_bits`, which reads first and skips the write when the value already
matches; because the selector reads 0, the write that selects page 0 was skipped. After the
DAC biquads were written on pages 44/45 (`aic32x4_write_biquads`, called from the machine
driver's late-probe route) the codec stayed off page 0, so `LDACVOL`/`RDACVOL` landed in
coefficient RAM while `tinymix get` still reported the requested value
(`volume-debug/dump-reset.log`, `page-routing.log`).

**Fix.** `d70e787ff949` adds `.cache_type = REGCACHE_MAPLE` to `aic32x4_regmap_config`
(`sound/soc/codecs/tlv320aic32x4.c`); the cache holds the last selector written, so regmap
always writes the real page before a page-0 access. I fast-forwarded it into
`feature/lidar-6.18`.

**Host.** I rebuilt with `experiments/phase-06/build_images.sh`: verifier
`lidar_recovery_image_contract=PASS` for dev, v1 and v2; v2 `boot-lidar-v2.img` sha256
`43e2de611766ef2fe90f45be1770c87640d84960bb09f242ce264870f68f9c56`. I rebuilt the OTA
bundles with `experiments/phase-06/ota/build_ota.sh` (v0.2.13 `146ea386…`, v0.2.14
`2413ea85…`).

**Flash and boot.** `libreecho-bootctl reboot-bootloader` into Kaeru 2.0.0, `oem
fetch-enable`, `flash boot_b`, `fetch boot_b` readback
`43e2de611766ef2fe90f45be1770c87640d84960bb09f242ce264870f68f9c56` (match). `fastboot
reboot` came up on slot B with `6.18.64+`, `androidboot.slot_suffix=_b`,
`libreecho.lab=p6-v2`; BCB `selected_slot=b`, B `15/0/1`, A `14/0/1` (v1 fallback).

**Silent register proof.** Both output mixer switches were read `Off` before playback
(`LOL Output Mixer L_DAC Switch`, `LOR Output Mixer R_DAC Switch`). Raw I²C reads of bus 2,
address `0x18`, page 0 (probe from `volume-debug/`, not the driver) while playing a
host-generated 48 kHz stereo WAV through `tinyplay`:

| PCM Playback Volume | idle `0x41`/`0x42` | during playback | after |
|---|---|---|---|
| 47 | `0xb0`/`0xb0` | `0xb0`/`0xb0` | `0xb0`/`0xb0` |
| 7 | `0x88`/`0x88` | `0x88`/`0x88` | `0x88`/`0x88` |
| 127 | `0x00`/`0x00` | `0x00`/`0x00` | `0x00`/`0x00` |

47 → `0xb0` as expected. Biquads remain loaded: page 44 `0x0c..0x0e` = `00 74 50` and
page 45 `0x14..0x16` = `65 86 3b`, matching `lidar_speaker_biquads` (woofer low-pass left,
tweeter high-pass right).

**Cleanup and final state.** I deleted the probe binary, `/tmp/i2c-2` node and the WAV from
the device; `PCM Playback Volume` was left at 47, both output mixer switches `Off`. The device
is on slot B, adb up. Logs: `step16-audio/volume-fix-verify/` (`flash.log`,
`register-proof.log`, `biquad-check.log`).

## Step 23: recovery entry (Action held at power-on). PASS on the third attempt

Logs and watcher: `step23-recovery/` (`fastboot.log`, `watch.sh`). Attempts 1 and 2 (Action
held ~2 s and ~5 s while plugging in) booted LibreEcho normally on slot A
(`bootreason=power_key`). Attempt 3 followed the working instruction: unplug for 10 s, hold
Action, plug in, keep holding for 10 s. Kaeru fastboot `2.0.0-g66704e6-dirty` appeared at
18:39:43; `getvar current-slot` returned empty (a Kaeru reporting gap). `fastboot reboot`
returned to LibreEcho on slot `_a`, both slots successful, update state `installed`. No
writes. Unverified: whether the short drain or the short hold caused the first two misses.

## Step 24: voice turn ("Alexa" + "set a timer for ten seconds"). FAIL, LibreEcho-UI defect

Timeline, probes and root cause: `step24-voice/result.md`. v0.2.21, slot A. waked detected
the wake (score 0.999093) and agentd opened a turn and played the chirp, but no terminal
outcome was ever logged within the 30 s backstop; that is a LibreEcho-UI voice-pipeline
defect, not a Lidar driver issue. Probes (`step24-voice/probe-results/`): sttd transcribes
real mic audio perfectly (`alexa-what-time.pcm` -> "ALEXA WHAT TIME IS IT") but transcribes
every TTS-`render` clip as `"S"`/`"UL"`/`""`, so the TTS clip part of the probe is
inconclusive, not an STT failure. The calibrated mono stream was 10-40x hotter than micd's
own contract and clipped in the first 67 s; raw ALSA lanes are quiet (peak about -33 dBFS),
so the over-level is created inside micd's beamform/gain stage. Mixer readback showed micd
asking for PGA 82 on a 0..63 control while audiod writes its own percent of the discovered
max; the two daemons disagree about the same PGA. My retest procedure is in the result.

## Step 25: Zigbee and Thread on the EFR32. Partial; firmware state changed

Full record: `step25-efr32/result.md`. `/dev/ttyS*` was absent because devtmpfs is not
mounted in the initramfs and `uart2` numbers as `ttyS1` (my 6.18 `8250_mtk.c` lacks alias
numbering); workaround `mount -t devtmpfs devtmpfs /run/devtmpfs`, port `ttyS1` 115200 8N1.
I recorded the stock firmware from `mmcblk0p13` before any write (`local-firmware/`, not for
publication). I installed Amazon's Zigbee NCP (`xncp-fw.gbl`) and verified it over EZSP
through bellows: protocol version 7, EmberZNet 6.5.3.0, `formNetwork` came up as coordinator
(panId 0x1a2b, channel 15), then I left the network up until the RCP replaced it. I built my
Thread RCP `lidar-ot-rcp.gbl` from Gecko SDK 4.4.3 + ot-efr32 `089440d`, flashed it
through the Gecko bootloader and verified it over Spinel (NCP_VERSION
`OPENTHREAD/089440d-dirty; EFR32; Nov 21 2026 20:57:28`, protocol version 4, UART iface).
Thread formation answered `Done` to dataset/ifup/thread start but stayed `detached`; the run
was cut off by a reboot and the cause is **not determined**. The chip runs one firmware at a
time; the reference's primary design is the Thread RCP, so I left the unit on the RCP
(`spinel-final.log`). I kept both stock GBLs in `local-firmware/`.

## Step 26: Bluetooth discoverable 501, A2DP pairing, pairing-off order

Three records in `step26-bt/`:

- **Discoverable 501 (`result.md`): general LibreEcho bug, not a Lidar port issue.** The
  kernel rejects `MGMT_OP_SET_DISCOVERABLE` with `MGMT_STATUS_REJECTED` (0x0b) while
  `HCI_CONNECTABLE` is clear, in all three shipped kernel trees; btd's standalone
  `set_discoverable` handler never set connectable first. Reproduced over the real btd
  adapter socket (`repro.log`). Fix `btd-discoverable-connectable.patch` on LibreEcho-UI
  `abe8d9111cbc67f0221b404c51c4d9bd1cc9ce73` (plus mock-backend mirror, contract test,
  `docs/API.md`); host build and contract test pass. Device verification of the patched
  binary is unverified until an OTA lands.
- **My phone's A2DP (`a2dp-phone.md`): PASS** (my verdict: "Bluetooth works perfectly"). With
  Pairing mode on, the phone found `LibreEcho`, paired and played music; AVRCP play/pause
  and volume work (absolute volume 30 to 54 logged). Without Pairing mode the phone saw only
  the controller default name `MTK MT7668 #4`, because the LibreEcho name and audio device
  class are set only by Pairing mode. Pairing mode could not be left from the web UI (the
  ordering bug below); cleared at runtime with `pairing_off.py`.
- **Pairing-off order (`pairing-off-upstream.md`): upstream note + patch.** The disable path
  restored discoverable before connectable, which the kernel rejects, so pairing mode
  latched on. Fix `btd-pairing-off-order.patch`: a `restore_pairing_settings()` helper that
  restores in kernel-valid order, an unconditional clear of the mode and LED, and a source
  contract test. Host-verified only (build and contracts pass); independent of the
  discoverable patch in both application orders. I did no device install in this step.

## Step 27: web setup failed at the Wi-Fi step (lab configuration fault)

My report and fix: `step27-websetup/` (`result.md`, `conf-fix.log`, `networkd.log`,
`reboot-check.log`). The lab-written `wpa_supplicant.conf` had no
`ctrl_interface=/tmp/wpa_ctrl` and no `update_config=1`, so wpa_supplicant opened no control
socket and networkd, which the web backend uses for status and connect, could not see or
change the link. This is a fault in my lab provisioning, not in LibreEcho or the port. I
prepended both lines (userdata write; original kept as `wpa_supplicant.conf.pre-ctrl`); I
killed a mistaken second wpa_supplicant within a minute and the link stayed up. After
reboot, the `/tmp/wpa_ctrl/wlan0` socket is present and voice daemons run. Unverified: the
web Wi-Fi page and setup flow after the fix (I still need to check).

## Step 28: serial/GPIO acceptance OTA (v0.2.22). Not installed, superseded

The bundle was built (`artifacts/phase-06/ota-step28-serial/`: 8250_mtk alias numbering so
`uart2` becomes `ttyS2`, plus a ramdisk that creates `/dev/ttyS2` and `/dev/gpiochipN` on
Lidar) and `step28-serial/install.sh` was written, but the install never ran: later steps
superseded it and no `events.log` exists in `step28-serial/`.

## Step 29: LibreEcho feature sweep. PASS with classified gaps

Full tables: `step29-features/result.md` (2026-11-21 pass and the 2026-11-22 re-sweep on
OTA v0.2.23, slot b, `txn-4f85bab71d5fe826cd0b0a1c`) and `step29-features/ha-result.md`.

- Home Assistant mode: first enable failed on the Lidar-specific esphomed MAC cause; the
  runtime shim (idme root from wlan0's factory MAC, privacy path) let my enable connect, and
  v0.2.23 carries the permanent fixes (UI `a7edb1d3`, kernel `3f2711ac4690`). I confirmed
  voice commands work.
- 2026-11-22 re-sweep PASS (every write reverted and re-read): timers and alarms, night
  mode, sleep light, idle mode, wake word settings, logs/diagnostics endpoints, updates
  page (read-only), privacy state, mDNS advertisements, Sendspin, plus read-only GETs.
- FAIL/blocked/N/A: Spotify Connect (no LibreEcho image ships `libreecho-spotifyd`; upstream
  gap, `get_spotify.json` `installed:false`), USB storage (DTS pins the OTG port
  peripheral; hardware), internet radio and news and NTP (blocked-internet; RTC persistence
  also fails on this board), GPT-Live (not shipped). Local assistant wake turn not run
  (PLAN:607, needs me).
- Root causes recorded: esphomed MAC source, HA restart state machine left `pending`
  (upstream plus port), privacy node name (fixed in v0.2.23). Cleanup: temporary accounts
  restored byte-for-byte (sha256-verified); device `/tmp` leftovers vanish on reboot.

## Step 30: identity OTA v0.2.23 installed. PASS

`step30-identity/` (`install.sh`, `install.log`, `events.log`, after/`privacy-checks.log`,
`esphomed-checks.log`). Installed 2026-11-21 over Wi-Fi adb (no fastboot): bundle
`lidar-lab-v0.2.23.ota.tar`, `verify_rc=0 ota_manifest_signature=PASS UPDATE_READY slot=b
version=0.2.23 install_rc=0`, reboot, `CONFIRMED: slot=b state=installed
generation=txn-4f85bab71d5fe826cd0b0a1c` at 21:39:37. After-checks on the new slot:
esphomed `ready:true connected:true` listening on port 6053, and the privacy node answers at
`/sys/devices/platform/amz_privacy/privacy_state` (the DTS rename).

## Step 31: microphone level and PGA fix. OTA v0.2.24 installed

`step31-mic/` (`result.md`, `mic-checks.log`, `install.log`, `events.log`). Root cause: the
Lidar PGA readback range is **0..80**, not 0..127. micd asked for `65 * 127 / 100 = 82`
(out of range, clamped to 80) at every capture start while audiod wrote my 65 % of the
discovered range = 52; whichever wrote last won, so micd's 80 saturated the beamformed
stream and audiod's 52 restored it. Raw codec lanes at 52 are quiet (-59 to -65 dBFS RMS),
so the over-level was this analogue race, not the beamformer or the digital gain. Fix:
`micd.c` `configure_lidar_capture_path()` writes the PGA as `"<percent>%"`, so tinymix
resolves it against the real range. Install 2026-11-22 over Wi-Fi adb: bundle
`lidar-lab-v0.2.24.ota.tar`, `UPDATE_READY slot=a version=0.2.24 install_rc=0`, signature
PASS, `CONFIRMED: slot=a state=installed generation=txn-dee60c3fa20042fc6d595775` at
07:11:37. After-checks: `ADC1..ADC4 PGA Capture Volume = 52, 52 (range 0->80)` on all four
ADCs and micd logs `Lidar OCM capture path configured (PGA 65%)`. My retest on 2026-11-22:
wake word and Home Assistant timer work. My decisions: the agentd reply path is
blocked-internet and was not tested (left to the maintainer); I checked the night and sleep
lights by eye and they look right. Open: speech at the fixed 52 is still ~1.7x micd's contract
upper bound; whether to lower the Lidar digital-gain default needs a wake-score measurement
this unit has no onnxruntime fixture for.

## Step 32: Home Assistant voice latency. Investigation, no change

`step32-ha-latency/` (`result.md`, `probe.sh`, `probe-run1.log`, `probe-run2.log`,
`tinyplay-check.sh`). Read-only device probe aligned with HA pipeline debug for three of my
turns. End of speech to sound is ~3.9 s for "what time is it". The breakdown is in `result.md`.

## Step 33: latency OTA v0.2.25 installed (cpufreq, two wake threads, held audio output)

`step33-latency-fix/` (`result.md`, `install.log`, `events.log`, `polls.log`,
`after-checks.log`). One dev-channel OTA carrying three slices: the 6.18 kernel with
`CONFIG_ARM_MEDIATEK_CPUFREQ=y` (Linux `77931cc`), waked asking for two ONNX intra-op
threads (UI `4b3c17d`), esphomed streaming TTS playback with the wake-time bus prime (UI
`a9cea2e`), and an `airplay2` feature payload holding the held-output audio engine
(Platform `32f3dbd`) so the amplifier settle leaves the reply path. Built from
`artifacts/phase-06/images-step33-latency/` and
`artifacts/phase-06/features-airplay2-latency/` into
`artifacts/phase-06/ota-step33-latency/lidar-lab-v0.2.25.ota.tar`
(`1ea37bbd…`, `txn-92d3a65dbbc8ff12b9a722f5`). Install 2026-11-22 over Wi-Fi adb from
slot a (v0.2.24): `verify_rc=0 ota_manifest_signature=PASS ready=b install_rc=0`,
`CONFIRMED: slot=b state=installed
generation=txn-92d3a65dbbc8ff12b9a722f5` at 08:21:42. After-checks: `mtk-cpufreq` with
`schedutil`, frequencies 598000 to 1300000, `scaling_cur_freq=1300000` idle and under
load; waked argv `--wake-threads 2` with two worker threads at 63.8 % and 48.1 % of a core
over 10 s; esphomed `ready:true connected:true`; idle `pcm0p` `closed`; shipped
esphomed/engine hashes equal the bundle and the payload. No audio was played in this run.

## Suspects (unverified)

Later (2026-11-22): all three were resolved. Boot 3 with the MUSB `rx_kick`
fix brought adb up and it held for every command, including the first push
("Boot 3: 6.18 with the MUSB rx_kick fix" below); the eMMC and SDIO probe state
came from that boot's dmesg (`step3d-boot3/dmesg.txt`), which shows `mmc0` HS200
with all 16 partitions and the MT7668 SDIO card on `mmc1`.

- adb/functionfs on 6.18: first `adb shell` hangs adbd while the USB gadget stays
  enumerated. The Phase 5 devlog rebind hack targeted a related unbind-without-rebind
  failure; this one never returns from the first shell.
- The MUSB receive fix is present on 6.18 (`3f0c178d3a93 feat(lidar): carry MUSB receive
  fix and isoc PIO quirk`), so the failure is probably in the adbd side rather than that
  known RX bug.
- eMMC/SDIO probe state after the DTB fix: unknown until dmesg or `/proc/partitions` is
  read.

## Diagnostic route agreed with Main

Later (2026-11-22): I prepared both routes but needed neither. Boot 3
carried the MUSB `rx_kick` fix, adb came up on the first try and stayed up, so
the dmesg captures ran directly and I never built the ACM/reboot diagnostic
images. I still used the warm-reset ramoops route once, in
`step4-ramoops/`, to prove that only a warm reset leaves the 6.18 console
readable in Kaeru.

`arch/arm64/boot/dts/mediatek/libreecho-lidar.dts:85-95` places ramoops at
`0x43810000` size `0x60000` (record 0x10000, console 0x40000, pmsg 0x10000), which is
exactly the window the installed Kaeru `fetch ramoops` reads. A **warm** reset into
Kaeru therefore exposes the 6.18 kernel console; my cold power cycle loses it.
`step4-ramoops/fetch.sh` performs that fetch in Kaeru.

If adb dies again on the next boot, two image-side diagnostics are the shortest route to
the missing dmesg, both initramfs-only changes:

1. Add an ACM function to the configfs gadget and a getty on `/dev/ttyGS0` (the Phase 4
   diagnostic shell), so the host can read `dmesg` over `acm_shell.py --usbfs`.
2. After a bounded wait with no adb session, call `libreecho-bootctl reboot-bootloader`
   so the boot ends in a warm reset to Kaeru with ramoops at `0x43810000` intact.

## Files

| Path | Content |
|---|---|
| `bin/adb`, `bin/fastboot` | android-tools wrappers |
| `step2-flash.sh` | step 2 procedure (first-boot image) |
| `step1-state/state.log` | step 1 capture |
| `step3-boot/observed.txt` | boot 1 console observations |
| `step3c-boot2/` | boot 2 flash, BCB set-active, early capture attempt |
| `ota_step6_618.sh` | step 9 OTA procedure (terminal-state confirm check) |
| `step9-ota/` | step 9 flash/install/confirm logs and final verification |
| `step16-audio/volume-fix-verify/` | page-selector fix flash, readback and silent register proof |
