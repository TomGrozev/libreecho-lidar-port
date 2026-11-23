# Read-only device poller for the announcement bug. Runs on the device via
# `adb shell sh -s < capture-device.sh`; writes nothing on the device, prints
# one line per change: uptime | esphome status | engine status | TCP peers | airplayd log lines.
end=$(( $(cut -d. -f1 /proc/uptime) + ${CAPTURE_SECONDS:-1200} ))
last=""
while [ "$(cut -d. -f1 /proc/uptime)" -lt "$end" ]; do
  s=$(cat /run/libreecho/esphome-status.json 2>/dev/null)
  a=$(cat /run/libreecho-audio/status.json 2>/dev/null)
  t=$(awk 'NR>1 && $4!="0A" {print $2">"$3"/"$4}' /proc/net/tcp | tr '\n' ' ')
  l=$(wc -l < /var/log/libreecho-airplayd.log)
  m=$(stat -c %Y /run/libreecho-audio/system.pcm)
  cur="$s|$a|$t|log=$l|sys_mtime=$m"
  if [ "$cur" != "$last" ]; then
    echo "$(cut -d' ' -f1 /proc/uptime)|$cur"
    last=$cur
  fi
  usleep 50000
done
