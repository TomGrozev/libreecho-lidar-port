# Phase 6 physical session: what needs Tom

Host-only procedure. The agent runs every command; Tom only listens, speaks, presses
buttons and moves the unit. Nothing here writes a partition: playback, capture, button and
LED checks are read-only, and the last step only enters and leaves Kaeru fastboot. Every
hardware write still follows PLAN.md's approval rules; none is part of this session.

Budget: about 15 minutes with Tom. Run the groups in order. If a group fails, finish
recording it, skip the groups that depend on it, and report the failure rather than retrying
into a different state.

## Before Tom arrives (agent, 2 minutes)

Work from the workspace root. `$A` below is `experiments/phase-06/adb.sh` and `$F` is
`experiments/phase-04/fb.sh`; both take a timeout as their first argument.

```sh
A=experiments/phase-06/adb.sh
$A 20 shell 'uname -r; head -3 /etc/libreecho/audio-profile; \
  ls -l /run/libreecho/audio.sock /run/libreecho/mic.sock \
        /run/libreecho/wakeword.sock /run/libreecho/agent.sock \
        /run/libreecho/led.sock; cat /run/libreecho/buttond-status; \
  ps w | grep -E "audiod|micd|waked|agentd|audio-engine"'
```

Pass preflight means: `/etc/libreecho/audio-profile` starts with `target_id=lidar` and names
`playback_card=0 playback_device=0 capture_device=1 capture_channels=8`; the five sockets
exist; `buttond-status` says `state=connected` with `volume=1 microphone_mute=1 action=1`;
and `audiod`, `micd`, `waked`, `agentd` and `libreecho-audio-engine` are running. Wi-Fi is the
LAN-only test network: check `ls /run/libreecho/wlan0-ready`, never print the Wi-Fi config.

Evidence: create `experiments/phase-06/hw-20261121/step16-audio/`, `step17-mics/`,
`step18-voice/`, `step19-buttons/`, `step20-recovery/` and tee every command's output there.
Append one section per step to that directory's README when the session ends.

Tell Tom: the unit stays on its stand, nothing is opened, and the only unplug is the
power lead in the last step.

## 1. Speaker playback (Tom, about 4 minutes)

Preparation: generate the test files on the host and push them. The tone files are 48 kHz
stereo S16, which is the Lidar playback format; `left` is the woofer channel and `right` the
tweeter channel per the Phase 6 audio decision.

```sh
python3 - <<'EOF'
import math, struct, wave
def wav(path, lf, rf, secs=4.0, rate=48000):
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(rate)
        for n in range(int(secs * rate)):
            l = int(9000 * math.sin(2*math.pi*lf*n/rate)) if lf else 0
            r = int(9000 * math.sin(2*math.pi*rf*n/rate)) if rf else 0
            w.writeframes(struct.pack('<hh', l, r))
wav('/tmp/lidar-left.wav', 440, 0)
wav('/tmp/lidar-right.wav', 0, 3000)
wav('/tmp/lidar-both.wav', 440, 3000)
# A short rising/falling phrase so Tom can recognise "music", not a beep.
with wave.open('/tmp/lidar-music.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
    notes = [262, 330, 392, 523, 392, 330, 262, 196] * 2
    for hz in notes:
        for n in range(24000):
            s = int(7000 * math.sin(2*math.pi*hz*n/48000) *
                    (0.5 - 0.5*math.cos(2*math.pi*n/24000)))
            w.writeframes(struct.pack('<hh', s, s))
EOF
for f in left right both music; do
  $A 60 push /tmp/lidar-$f.wav /tmp/lidar-$f.wav
done
```

Volume check through the product path. `test_tone` asks audiod for its built-in tone; the
audio engine applies the software volume.

```sh
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"set_volume\",\"args\":{\"volume\":80}}" | nc -U /run/libreecho/audio.sock'
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"test_tone\",\"args\":{}}" | nc -U /run/libreecho/audio.sock'
sleep 3
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"set_volume\",\"args\":{\"volume\":20}}" | nc -U /run/libreecho/audio.sock'
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"test_tone\",\"args\":{}}" | nc -U /run/libreecho/audio.sock'
sleep 3
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"set_volume\",\"args\":{\"volume\":80}}" | nc -U /run/libreecho/audio.sock'
```

Ask Tom: "Was the first beep clearly louder than the second, and did the second still
sound like a beep?" Both answers must be yes.

Woofer and tweeter. Play each channel alone, then both. If `tinyplay` answers `Resource busy`,
wait three seconds and retry once; the engine releases the PCM when idle.

```sh
for f in left right both music; do
  $A 30 shell "/sbin/tinyplay /tmp/lidar-$f.wav -D 0 -d 0" 2>&1 | tee -a experiments/phase-06/hw-20261121/step16-audio/play.log
  sleep 2
done
```

Ask Tom, in this order:

1. Left-only: is the sound low and full, as if from a woofer?
2. Right-only: is it thin and high, as if from a tweeter?
3. Both: are the two sounds present together, not just the louder one?
4. Music: is it a short rising-and-falling tune with no crackle, dropout or buzz?

Pass: all four yes. A left-only file that sounds thin, or a right-only file that sounds low,
means the DAC channels or the crossover biquads are swapped or unloaded; record the
observation, do not change the mixer to hide it.

## 2. Wake word and assistant, end to end (Tom, about 3 minutes)

This group runs before capture is touched, because `waked` holds the live mono stream.
Record the before counts:

```sh
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/wakeword.sock' | tee experiments/phase-06/hw-20261121/step18-voice/wake-before.json
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/agent.sock' | tee experiments/phase-06/hw-20261121/step18-voice/agent-before.json
```

Ask Tom to stand at normal speaking distance and say **"Alexa"** once, clearly. The
waked status must show `detected_count` one higher. Tom should hear the short rising
chirp and see the ring react. Then ask Tom to say:

> "Set a timer for one minute."

This request is handled inside agentd without a language model, so it is the one full
voice path that can pass on a LAN-only network. Pass requires, in order: chirp, ring
reaction, a spoken confirmation, and the timer sound one minute later.

```sh
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/wakeword.sock' | tee experiments/phase-06/hw-20261121/step18-voice/wake-after.json
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/agent.sock' | tee experiments/phase-06/hw-20261121/step18-voice/agent-after.json
$A 30 shell 'tail -40 /var/log/libreecho-waked.log; tail -40 /var/log/libreecho-agentd.log' | tee experiments/phase-06/hw-20261121/step18-voice/logs.txt
```

What cannot pass here: agentd's default provider is a cloud LLM (`openai-codex`), and the test
network has no internet beyond the LAN (Step 7: DNS and gateway work, external TCP does not).
A general question such as "what is the weather" therefore has no answer path. Ask it once,
record the failure as `blocked: no internet`, and do not count it against the device. A
general question passing here would instead prove that a LAN LLM endpoint was configured.

Also record whether the *wake* path itself survives the sequence: `wakeword.sock` still
exists and `waked` is still the same pid after the timer fires. A waked exit after one
playback is the known AEC suspect; the init script has no supervisor, so a lost socket is a
real failure, not a retry.

## 3. Microphones and the privacy latch (Tom, about 5 minutes)

Capture must own the PCM exclusively, so stop the two services that hold it. They are
restored at the end of this group.

```sh
$A 30 shell '/etc/init.d/libreecho-waked stop; /etc/init.d/libreecho-micd stop'
sleep 2
$A 30 shell 'ls -l /run/libreecho/mic.sock 2>&1; ls /dev/snd'
```

Baseline, then one clip per microphone. Tom does the physical part: the agent asks
for microphone 1, Tom rubs a fingertip firmly next to that opening for three seconds;
repeat clockwise through 7. Tom knows the openings; the agent only labels them 1 to 7.

```sh
$A 30 shell '/sbin/tinycap /tmp/mic-0.wav -D 0 -d 1 -c 8 -r 16000 -b 32 -t 3'
for n in 1 2 3 4 5 6 7; do
  echo "Owner: rub next to microphone $n for 3 seconds."
  sleep 1
  $A 30 shell "/sbin/tinycap /tmp/mic-$n.wav -D 0 -d 1 -c 8 -r 16000 -b 32 -t 3"
done
for n in 0 1 2 3 4 5 6 7; do
  $A 60 pull /tmp/mic-$n.wav experiments/phase-06/hw-20261121/step17-mics/
done
```

Analyse on the host. Each clip is 8-channel S32_LE at 16 kHz; lanes 0-6 are the microphones
and lane 7 is line-in.

```sh
python3 - experiments/phase-06/hw-20261121/step17-mics/mic-*.wav <<'EOF' | tee experiments/phase-06/hw-20261121/step17-mics/analysis.txt
import array, sys, wave
for path in sys.argv[1:]:
    w = wave.open(path); ch = w.getnchannels(); n = w.getnframes()
    a = array.array('i'); a.frombytes(w.readframes(n))
    rms = [(sum(x*x for x in a[c::ch]) / max(1, len(a[c::ch]))) ** 0.5 for c in range(ch)]
    print(path.split('/')[-1], ' '.join(f'{c}:{v:.0f}' for c, v in enumerate(rms)))
EOF
```

Pass: each `mic-1` to `mic-7` clip has one lane at least 6 dB above the `mic-0` baseline on
that lane and above the same clip's other six lanes, and the seven dominant lanes are all
different. A clip with no dominant lane means that opening is dead, blocked or Tom
missed it; ask once more for that number before recording a failure.

Privacy latch, with capture still stopped. The mute button drives a hardware latch that
cuts the microphones; software cannot release it. Read the kernel state, then capture while
Tom talks directly at the array in each state.

```sh
P=/sys/devices/platform/amz_privacy/privacy_state
[ -r "$P" ] || P=/sys/devices/platform/amz-privacy/privacy_state
$A 30 shell "cat $P"
echo "Owner: press the mute button once (lamp/ring should show muted)."
sleep 2
$A 30 shell "cat $P; cat /run/libreecho/buttond-status"
echo "Owner: talk loudly at the device for the next 3 seconds."
$A 30 shell '/sbin/tinycap /tmp/mic-muted.wav -D 0 -d 1 -c 8 -r 16000 -b 32 -t 3'
$A 60 pull /tmp/mic-muted.wav experiments/phase-06/hw-20261121/step17-mics/
echo "Owner: press the mute button again (lamp/ring returns to normal)."
sleep 2
$A 30 shell "cat $P; cat /run/libreecho/buttond-status"
echo "Owner: talk loudly at the device for the next 3 seconds."
$A 30 shell '/sbin/tinycap /tmp/mic-open.wav -D 0 -d 1 -c 8 -r 16000 -b 32 -t 3'
$A 60 pull /tmp/mic-open.wav experiments/phase-06/hw-20261121/step17-mics/
```

Analyse both files with the same script. Pass: with the latch on, `privacy_state=1` and all
seven lanes are at or near the silent baseline despite loud speech; with it released,
`privacy_state=0` and the lanes rise clearly. Tom must also confirm the visible muted
indication (lamp or ring) changes with the button.

Restore the voice services and confirm they come back:

```sh
$A 30 shell '/etc/init.d/libreecho-micd start; /etc/init.d/libreecho-waked start'
sleep 5
$A 30 shell 'ls -l /run/libreecho/mic.sock /run/libreecho/wakeword.sock; \
  ps w | grep -E "micd|waked"'
```

If an init file is absent on the running image, use
`/usr/local/sbin/libreecho-reconcile-features` and record which route was needed.

## 4. Buttons, LEDs and the privacy lamp (Tom, about 3 minutes)

Keys come from `gpio-keys`: volume up on GPIO7 (`KEY_VOLUMEUP`), volume down on GPIO12
(`KEY_VOLUMEDOWN`), action on GPIO42 (`KEY_HELP`), mic mute on GPIO108 (`KEY_MICMUTE`).
The agent watches the daemon state while Tom presses each key once, slowly.

```sh
echo "Owner: press volume up once."; sleep 2
$A 30 shell 'cat /run/libreecho/buttond-status; printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/audio.sock'
echo "Owner: press volume down once."; sleep 2
$A 30 shell 'cat /run/libreecho/buttond-status; printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"status\",\"args\":{}}" | nc -U /run/libreecho/audio.sock'
echo "Owner: press the action button once."; sleep 2
$A 30 shell 'tail -20 /var/log/libreecho/system.log | grep buttond'
```

Pass: volume up and down each produce a short rising or falling cue, the reported volume
moves by one step in the right direction, and the action press logs `buttond: action button`
and plays a chime with a ring flash. A press with no log line and no cue is a dead key.

LED visual test, covering all twelve RGB positions of the IS31FL3236A ring:

```sh
$A 30 shell 'printf "%s\n" "{\"v\":1,\"id\":1,\"cmd\":\"test\",\"args\":{}}" | nc -U /run/libreecho/led.sock'
```

Ask Tom: "Did the whole ring light, with no dark segment, and did the colours change
through the test?" Both parts must be yes. One dark position is a channel or solder fault,
not a software pass.

The mic-mute hardware check was already made objectively in group 3; here only confirm what
Tom sees: the mute press lights the lamp or shows the muted ring, and the second press
clears it. Record the `lamp_control` value from `buttond-status` (1 means the kernel accepted
lamp control, 0 means the physical latch owns it, -1 means untested or unreadable).

## 5. Button-combo recovery entry (Tom, about 1 minute)

This is the recovery floor: hold the Action button while applying power. The device does not
boot LibreEcho; it waits in Kaeru fastboot. Tom performs the physical step; the agent
confirms the USB side.

```sh
echo "Owner: unplug the power lead. Hold the Action button down, plug the lead back in,"
echo "keep holding for 2 seconds after the lead is in, then release."
sleep 15
$F 60 devices
$F 60 getvar kaeru-version
```

Pass: `fastboot devices` lists one device and `getvar kaeru-version` answers with a Kaeru
version. Then leave fastboot without writing anything:

```sh
$F 60 reboot
sleep 20
$A 30 shell 'cat /proc/cmdline; cat /run/libreecho/buttond-status'
```

The unit must return to the same slot and the same confirmed state it had before the session.
Record `misc`'s BCB location only if the agent already has a read-only fetch; this session
must not flash or reset it.

Note for the record: the in-system equivalent,
`/usr/local/sbin/libreecho-bootctl reboot-bootloader`, was proven in Phase 5. The button
combo is the route that works when the system will not start, which is why it is the one
tested physically here.

## Result sheet

| Group | Tom does | Agent checks | Pass wording |
|---|---|---|---|
| Speaker | listens | audiod tone at 80 and 20, tinyplay L/R/both/music | louder then quieter; low-left, high-right, both, recognisable tune |
| Wake word | says "Alexa", then a timer request | waked/agentd status and logs | chirp, ring, spoken confirmation, timer sound; wake survives |
| Assistant (cloud) | asks one general question | agentd log | recorded as blocked on the LAN-only network, not a device failure |
| Microphones | rubs by mics 1-7 | 8-channel captures | seven distinct dominant lanes, each above baseline |
| Privacy latch | presses mute on, speaks, mute off, speaks | `privacy_state`, `buttond-status`, captures | muted capture is silent, released capture is not; visible indication follows |
| Buttons | volume up/down, action | `buttond-status`, audiod status, log | cue and state change per key; action chime and ring flash |
| LEDs | watches the ring | ledd `test` | full ring, no dark segment, colours change |
| Recovery entry | holds Action at power-on | fastboot `devices`, `getvar kaeru-version` | Kaeru answers; reboot returns to the same confirmed slot |

Anything Tom could not do, or the agent did not run, is recorded as unverified rather
than passed. A failed check stays a result; it does not loosen a Phase 6 gate.
