# Step 22: cue drain fix (OTA v0.2.17)

Platform fix/engine-drain-before-mute 0be90ed7e6 (base fc8e3c2a): drain the PCM ring before
muting LO DAC and play the padded sub-period tail. Engine 151fc045…, payload a2dc3941…,
bundle 918b0c13…, txn-a0cd2a02d88a49761d4be3f1, boot images-cue `12f31aed…`.
Install: verify_rc=0, signature PASS, install_rc=0 (`install.log`). Booted slot A, engine
`speaker chain lidar`, volume 50 (`after-boot.log`).

Owner, single volume-down then single volume-up press after a pause: both played the full
two-note cue; no click or pop at the end. PASS.
