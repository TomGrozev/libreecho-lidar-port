# Step 21: cue level matched to music (OTA v0.2.16)

UI abe8d9111c (LE_CHIRP_AMPLITUDE 16384), boot-lidar-v2 `12f31aed…`, bundle `0b058770…`,
txn-0283eca3548303cfb36d2090. Install: verify_rc=0, signature PASS, install_rc=0 (`install.log`).
Booted slot B, boot-validating, engine 97867ec9 with `speaker chain lidar` (`after-boot.log`).

Owner, product path, first audible since the fixes:
- Volume down 50→45: cue "quiet but clear" (expected ≈ −46 dBFS peak).
- A few steps up: louder each step. Volume buttons + speaker path PASS.
- Fault: the volume-change cue is sometimes cut off. Open.
