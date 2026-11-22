# Step 18: buttons

Hardware evidence, 2026-11-21. Speaker path off (LOL/LOR/LO DAC Off), so no cues were audible.
Owner pressed volume up, volume down, action once each. Log: `buttons.log` (system.log grep).

- volume up: `buttond: volume up -> 55`, `audiod: set_volume 50 -> 55`. PASS.
- volume down: `buttond: volume down -> 50`, `audiod: set_volume 55 -> 50`. PASS.
- action: `buttond: action button (sound)`. PASS (chime/ring flash not checked: speaker off).
- `/run/libreecho/buttond-status` never changed during the presses (140 polls identical): it is a
  static capability file, not live state.

Mute-key log from step 17 (system.log 261-270): on latch ON buttond logged
`microphone unmuted` / `mute indicator off`; on latch release it logged `microphone muted` /
`mute indicator on`. buttond's mute state is inverted relative to `privacy_state`.
