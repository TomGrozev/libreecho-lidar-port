# Step 27: web setup failed at the Wi-Fi step (lab configuration fault)

My report, 2026-11-21: the setup wizard asked for a Wi-Fi network although the unit was on
Wi-Fi, and the last step failed with a Wi-Fi connection error.

Cause: the lab-written `/data/libreecho/config/wpa_supplicant.conf` (Nov 20) had no
`ctrl_interface=/tmp/wpa_ctrl` or `update_config=1`. `libreecho-wifi` starts wpa_supplicant
from that file, so no control socket existed (`networkd.log`), and networkd, which the web
backend uses for status and `connect` (`backend_linux.c:1774-1796`), could not see or change the
link. The product writes both lines (`wpa_supplicant.conf.example:3`,
`network_recovery.c:1230`). This is a fault in our lab provisioning, not in LibreEcho or the
port. The failed attempt did not change the config file.

Fix (userdata write, approved class): both lines prepended, original kept as
`wpa_supplicant.conf.pre-ctrl` (`conf-fix.log`). Operator error during the check: a second
wpa_supplicant was started by mistake (pid 12904) and killed within a minute; the link stayed
up throughout.

Reboot (`reboot-check.sh`, `reboot-check.log`): adb back at 21:03:34, slot A,
`generation=txn-219f…`, `/tmp/wpa_ctrl/wlan0` socket present, voice daemons running.
Unverified: the web Wi-Fi page and setup flow after the fix (Tom to check).
