# Deploy v0.2.29 (Sendspin fix): outcome and evidence

Version-by-version summary: [`../versions.md`](../versions.md).

Date: 2026-11-22. Image: boot cd979c08…, OTA adaffa40…, generation txn-cc95a15ac3b7e1c89d9dc5cb,
feature payload cd5e9d60… (sendspind 4198d62a…, audio engine 84e5ae9b…).

## What ran
The hand install script for this series (now removed; `tools/lab-build.py` replaces it)
ran the step-37 OTA path
(check → signed bundle verify → install → activate slot a → reboot). Logs: install.log,
ota-build.log, install.log tail in deploy-run.log.

## Result
- Install: signature PASS, verify rc0, slot a written and read back cd979c08, BCB activation OK, reboot.
- Slot a booted 3 times; each boot: `ota-health-probe-passed:1..3`, then
  `ota-health-confirm-failed-rebooting`. LK rolled back to slot b (v0.2.28, a7b266b7).
- LK state: slot a priority 0 success 0; slot b confirmed. No try counter burned on b.
- Persistent evidence: `failure-1795338568-1.log` (pulled excerpt in failure-detail.log).

## Confirm failure
`ota-confirm:ERROR:feature_target_not_ready`: `libreecho-update confirm` → schema-3 path
→ `libreecho-feature-transaction verify-running` failed. That tool checks, in order:
candidate-bcb, boot image hash, feature mount, required-service probes. The inner reason token
was written only to /tmp/ota-confirm.log on slot a and is gone (tmpfs across rollback).

Context from the same boot (init.log excerpt in failure-detail.log):
- `ota-health-waiting-startup-ready`, `feature-services-deferred-until-staged`
- `ui-service-start:ttsd:0`, `ui-service-start:airplayd:0`, `ui-service-start:esphomed:1`
- `feature-reconcile-service-start-failed:esphomed`, `feature-service-topology-reconcile-failed`
- `first-boot-startup-ready-timeout-degraded`, `startup-ready-marker-missing`

## Postmortem (2026-11-22, read-only; owner stays on v0.2.28, no writes/reboot)

### Proven delta v0.2.28 (a7b266b7) → v0.2.29 (cd979c08), layer by layer
- Kernel `Image`, kernel config, source DTB, stock DTBs, OTA keys/trust, feature and generation
  manifests: identical. Only derived fields differ: the DTB chosen initrd-end and the Android id
  hash, because the new ramdisk is a different size (5,767,292 B).
- UI bundle: f43dade → d63a58a (svc code + `share/libreecho/ui-manifest.txt`).
- airplay2 payload: identical tree (1073 entries), only `libreecho-sendspind` bytes differ
  (4198d62a, the trial binary from UI d63a58a). The other four payloads are byte-identical.
- **Not UI-only**: eight ramdisk platform files came from a newer Platform worktree:
  `/init`, `/libreecho-init`, `usr/local/sbin/{libreecho-update,-update-fetch,-reconcile-features}`,
  `etc/init.d/libreecho-mdnsd.init`, `sbin/ueventd`, `sbin/watchdogd`
  (the saved diffs were session output and have been deleted). Step 37's bytes are only in the v0.2.28 ramdisk (`/tmp/rd-old`).

### Cause of the failed confirm gate
`libreecho-reconcile-features` (new) adds `tts` to `persisted_features` and stops calling
`stop_service ttsd`; `init` (new) adds `ttsd` to the HA boot service list and drops it from
`stop_owners`. In `reconcile()`, `reconcile_topology` runs **before** the
`for feature in $persisted_features` loop and `return 1` aborts the whole function. On slot a
esphomed did not become ready, so the topology reconcile failed and **no** persisted feature was
started, airplay2 included. `verify-running`'s airplay2 probe therefore failed and
`libreecho-update confirm` refused with `feature_target_not_ready`. v0.2.28 never starts ttsd at
boot (its init lists `airplayd radiod esphomed web` and stops ttsd in HA), and its esphomed is up.
Why esphomed itself was not ready within its 2 s window is not recoverable: its log lives on
tmpfs and the rollback erased it. ttsd is a correlated new neighbour, not a proven trigger.

### Rebuild attempt (host, this session): blocked
Staged the eight step-37 bytes from the v0.2.28 ramdisk into a throwaway copy of
`tools/{mt8163-arm32,mt8167-arm64}` (`/tmp/pf-old2`) and ran a hand image-building
script (now removed): the builder refused with `LibreEcho recovery /init SHA-256 mismatch`,
expected `cc61a51b…` (current Platform), actual `0c673386…` (step 37/v0.2.28).
So the current tooling hard-pins a **newer** init than the deployed image: v0.2.28 is not
reproducible from the tree, and a UI-only delta cannot be built against the step-37 overlay
without patching a Platform hash contract. Build log: `images-rebuild.log`. No image produced.

### Options (need Main/owner decision)
1. Fix the Platform regression and rebuild from current HEAD: make the confirm gate independent
   of one daemon (do not abort `persisted_features` when `reconcile_topology` fails; or make
   esphomed readiness non-fatal for topology), then rebuild images + generation and OTA.
2. Re-pin the full step-37 Platform tool tree (including its hash constants) for the rebuild, so
   the only delta is UI d63a58a + sendspind; needs the exact step-37 commit/tool snapshot.
3. Diagnose esphomed on a fresh candidate boot first (its log is only on tmpfs; a read-only
   console capture during the next attempt would settle the trigger).

### Redeploy commands (proposed, not run)
```
# after rebuilding boot-lidar-v2.img + generation from the chosen tree
# the hand install script is gone; use tools/lab-build.py deploy or the step-37 OTA path
```
Device untouched: no writes, no reboot, no service change this session.

## Rebuild v0.2.30 (Platform fix + UI 715dd4f), host only
Platform branch `fix/reconcile-topology-nonfatal` off `d7ad2ac4`, commit `07549ae3`.
UI `feature/lidar-support-0.14.6` at `715dd4f` (worktree `/tmp/wt-lidar2`).
- sendspind rebuilt from 715dd4f: `36572977d9221f…` (previous trial binary was `4198d62a…`).
- airplay2 payload rebuilt from the previous payload root with only that binary replaced:
  payload `29aacb6699c9b0a943ffadb6d6a905e1de4958feebfb0ea2b458bb0033f37d8c`,
  manifest `504949f812c64349ca6a70fd483912b32fc4de6cbbef670e28c655cb9d878276`.
- UI bundle manifest `4c544b2c…` at `artifacts/phase-07/components-715dd4f`.
- images `artifacts/phase-07/images-715dd4f`: v2 `df8e382d98b4a04d2cafe891e82a2570974f6fa56e64578315923845d3a0223e`,
  v1 `927d3cd4…`, dev `0b0187cb…`.
- OTA `artifacts/phase-07/ota-715dd4f/lidar-lab-v0.2.30.ota.tar`,
  txn `txn-3a14da94f8809657a44538a0`, bundle `359f8df5e5a8a7c01c2e787c18422276d7afd97a2cb0cc3ad82fd49679084825`.
- Host verification with the hand v0.2.30 build script (now deleted): all PASS (size/magic, ramdisk key, UI commit,
  sendspind and engine hashes, reconciler fix present in ramdisk, new-key signature PASS,
  old-key rejected). Producer: `experiments/phase-05/ota/make_lab_ota.py` (as `run_step37.sh:59-67`).
- UI 715dd4f changed only service wrappers (`init/libreecho-{agentd,esphomed,lived,mdnsd,waked}.init`,
  `src/adapter/mdnsd.c`); esphomed's start readiness is unchanged, ttsd's init is unchanged.
  The pairing matters because `/etc/init.d/*` ship in the UI bundle while the boot policy
  (ttsd started and persisted) comes from the Platform ramdisk.

