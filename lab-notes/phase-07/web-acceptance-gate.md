# Phase 7: per-board hardware acceptance gate in the web installer

Fork: `private/forks/LibreEcho-Installer-Web`, branch `feature/lidar-support`,
base `3e189f5` plus the concurrent Lidar stage-plan test commit `fef736c`.
Local commit `5b6477ec2c`, not pushed.

PLAN.md requires Lidar to stay out of the normal web installer until hardware
acceptance. `release/targets/lidar.json` (product repo) has
`"hardware_accepted": false`, which `3e189f57` did not mirror.

## Behaviour

- `js/profiles.js` now carries `hardwareAccepted` on each profile: Radar and
  Biscuit `true`, Lidar `false` (comment ties it to the product descriptor).
  `targetHardwareAccepted(profile)` treats an absent field as not accepted, so
  a new profile opts in explicitly.
- `js/targets.js`:
  - `installableBoards()` filters unaccepted profiles, so Lidar is absent from
    the device chooser.
  - `offeredBoards(release)` filters them, so a release that publishes Lidar
    assets still offers no Lidar build.
  - `parseTargetsJson` accepts an optional boolean `hardware_accepted` per
    target entry and ANDs it with the profile. A release descriptor can refuse
    an accepted board, but cannot revive one the local mirror marks unaccepted.
  - `targetsForRelease` drops unaccepted targets, so download, manual-file and
    convenience paths cannot resolve one.
  - `targetForBoard` refuses a named unaccepted board with
    `hardwareAcceptanceError`, even if forced with a hand-set board or crafted
    descriptor.
- `js/app.js`: `fetchBundleAutomatically` names the acceptance refusal for a
  hand-set board; `installReadinessReason` and `unmetPrerequisites` keep the
  same check as defence in depth. The existing bundle-level
  `build.hardware_accepted` gate is unchanged, so a bundle that lies about
  acceptance still verifies but cannot install.
- No developer/lab mode exists in the repo (no query parameter, localStorage
  switch or config flag), so no mode was added: Lidar is hidden entirely.

Radar and Biscuit behaviour is unchanged (same options, same gates).

## Tests

Command (the lab shell blocks an unquoted glob, so the files are listed):

```
node --test js/test_amonet.mjs js/test_amonet_visibility.mjs js/test_app.mjs \
  js/test_auto_fetch.mjs js/test_device_choice_copy.mjs js/test_direct_install.mjs \
  js/test_direct_review_fixes.mjs js/test_empty_identity_query.mjs \
  js/test_fastboot_mode_refusal.mjs js/test_lidar_gates.mjs js/test_post_install.mjs \
  js/test_post_install_app.mjs js/test_publication_trust.mjs js/test_recovery.mjs \
  js/test_recovery_entry.mjs js/test_recovery_guided.mjs js/test_recovery_identity_322.mjs \
  js/test_recovery_metadata.mjs js/test_recovery_races.mjs js/test_release.mjs \
  js/test_report.mjs js/test_resume_28.mjs js/test_safety.mjs js/test_stage_hardening.mjs \
  js/test_targets.mjs js/test_transports_release.mjs js/test_unpinned_lk.mjs \
  js/test_usb_single_owner.mjs
```

Result: 399 tests, 397 pass, 2 skipped, 0 fail. Five new assertions live in
`js/test_targets.mjs`:

- an unaccepted board is not in `installableBoards()`, is not offered for a
  release that publishes its assets, and `targetForBoard` refuses it with or
  without a descriptor;
- a release descriptor with `hardware_accepted: false` drops an otherwise
  accepted board, and a non-boolean value is refused;
- flipping the profile flag to `true` offers and resolves the board again, and
  restoring `false` hides it, proving the flag is the gate.

`js/test_lidar_gates.mjs` was updated in the same fork; those edits were
swept into the concurrent `fef736c`, which already includes
"Lidar is declared but not offered while hardware acceptance is pending" and
the forced-selection refusal. Its Lidar descriptor/geometry tests now read the
parsed targets.json entry directly, so contract coverage no longer needs the
selection gate to be open.

## Browser check

Static site served with `python3 -m http.server 8971` from the fork root and
opened in headless Chromium. The device selector offers only
"Amazon Echo 2nd Generation (2017)" and "Amazon Echo Dot 2nd Generation (2016)";
Lidar is absent. No console errors. Screenshot:
`web-acceptance-gate.png`.

No device was connected; no USB, fastboot or write action was performed.

## Unverified

- No Lidar release exists, so the accepted-board download and recovery paths
  were not exercised in a browser; the acceptance flip is covered by unit tests
  only.
- The product repo's combined `targets.json` does not emit per-target
  `hardware_accepted` yet. The web gate therefore relies on the mirrored
  profile (fail-closed); per-entry support is ready if the publisher adds it.
- `release/targets/lidar.json` itself is not fetched by the browser; the profile
  comment records the mirror relationship, but nothing verifies the two files
  agree at runtime.
