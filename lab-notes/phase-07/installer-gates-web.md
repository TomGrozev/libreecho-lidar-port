# Phase 7: Lidar gates in the browser installer

Fork: `private/forks/LibreEcho-Installer-Web`, branch `feature/lidar-support`,
base `c7cac7c`, local commit `3e189f5710be9d7f3443c2846c944bee551092dd`,
not pushed.

Contract source: `private/lab/phase-07/installer-lidar-contract.json`
(`libreecho-lidar-installer-contract-v1`, written by the CLI installer work).
The web profile mirrors its `fastboot_product`, `hw_profile`,
`userdata_sectors`, `boot_slots`, `pin_rule` and `ota_plan` values.

## Gate map

The browser has no boot-chain flash path for a converted target. Its gates are:

1. `js/profiles.js` declares `lidar` with `pinRule: "already-converted"`, no
   `archive`, no `lkBuildMap` and no `fallbackPayload`. `payloadForProfile`
   returns null for it, so no LK build or operator opt-in can choose an Amonet
   payload. `payloadNameCandidates` now tolerates a profile without a map.
2. `js/stages.js` `readFastbootIdentity` reads `kaeru-version` and
   `partition-size:<slot>` only when the product resolves to a converted
   profile. Radar and Biscuit issue the same getvars as before.
3. `assessIdentity` requires a non-empty `kaeru-version`, a userdata size equal
   to `userdata_sectors * 512` and a reported size for every boot slot. A
   missing or wrong value is a finding. This is the fail-closed pin rule: a
   LIDAR product without Kaeru is refused, and no boot-chain write is offered.
4. `submitUnlockPayload` refuses a converted profile before `flash:brick`.
5. `js/app.js` `amonetRequirement` returns skip for a converted profile, so the
   archive controls never open. Unknown-product messages now list every profile.
6. `js/targets.js` accepts the Lidar board from a combined release and requires
   a Lidar bundle manifest to declare `soc=mt8167` and `userdata_sectors=9647071`.
   `hw_profile`, `architecture` and `image_profile` are checked when present.
7. expdb and the boot chain have no write path in this installer. The browser
   writes no partition directly; the recovery helper owns userdata and the boot
   slots, and the Lidar profile cannot reach `flash:brick`.

## Tests

Command (the repo's CI command, expanded because the runner blocks an unquoted
glob in this lab shell):

```
node --test js/test_recovery_races.mjs js/test_release.mjs js/test_report.mjs \
  js/test_resume_28.mjs js/test_safety.mjs js/test_stage_hardening.mjs \
  js/test_targets.mjs js/test_transports_release.mjs js/test_unpinned_lk.mjs \
  js/test_usb_single_owner.mjs js/test_amonet_visibility.mjs js/test_amonet.mjs \
  js/test_app.mjs js/test_auto_fetch.mjs js/test_device_choice_copy.mjs \
  js/test_direct_install.mjs js/test_direct_review_fixes.mjs \
  js/test_empty_identity_query.mjs js/test_fastboot_mode_refusal.mjs \
  js/test_post_install_app.mjs js/test_post_install.mjs \
  js/test_publication_trust.mjs js/test_recovery_entry.mjs \
  js/test_recovery_guided.mjs js/test_recovery_identity_322.mjs \
  js/test_recovery_metadata.mjs js/test_recovery.mjs js/test_lidar_gates.mjs
```

With the change: 394 tests, 392 pass, 2 skipped, 0 fail. The 19 Lidar tests are
`js/test_lidar_gates.mjs`. A baseline count was not taken; the suite passed
before the change and passes after it.

Lidar accept paths: profile and contract values, `LIDAR` product resolution,
Kaeru identity with the contract geometry, a matching combined-release target,
and a matching bundle manifest.

Lidar reject paths: missing or empty `kaeru-version`, wrong userdata size,
missing boot slot size, any `payloadForProfile` call with or without the opt-in,
`submitUnlockPayload` before `flash:brick`, a Radar product, SoC, geometry,
`hw_profile`, architecture or image profile, a missing SoC or userdata line, and
a target prefix outside `libreecho-lidar-`.

Radar and Biscuit: the pin rule defaults to `amonet-payload`, their profiles
gain no field, their payload pins are asserted unchanged, and a test asserts
Radar asks no `partition-size` getvar.

## UI check

The site is static. Served with `python3 -m http.server 8611` from the fork root
and opened in headless Chromium. The device selector lists Radar, Biscuit and
`lidar` ("Amazon Echo Plus 2nd Generation (2018)"). Selecting Lidar reports
"No build for Amazon Echo Plus 2nd Generation (2018) is available yet" because
no Lidar release is published, so the build step stays at NONE. Screenshot:
`installer-gates-web-target-choice.webp`.

No device was connected. No USB or fastboot action was performed.

## Unverified

- No Lidar release exists, so the release download, bundle verification and
  recovery phases were not run for Lidar.
- The Lidar recovery route is not declared. `RECOVERY_DEVICE_NAMES` still omits
  `lidar` because the platform has no recovery partition and no TWRP path for it
  has been established here. A Lidar install therefore has no browser route yet;
  this change adds the identity, pin, geometry and bundle gates only.
- `partition-size` values come from the reference `lidar_install.py` behaviour
  and contract; they were not read from hardware in this task.
- The contract file appeared during this task. The profile mirrors it now,
  including `ota_plan.schema`, and the focused Lidar test passed after that
  alignment.
