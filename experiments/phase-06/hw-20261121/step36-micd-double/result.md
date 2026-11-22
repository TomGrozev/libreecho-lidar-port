# Step 36: two libreecho-micd processes on the device

Read-only investigation. Device runs v0.2.27 (slot b, txn-b0a9e76b738c1b4d1b64ae8a),
adb over Wi-Fi `<DEVICE_IP_A>:5555`. No writes, restarts or audio actions were performed.

## Verdict

The second process is the **per-stream worker that micd forks on purpose**, not a respawn,
not a second launcher and not a boot race. No change is needed for it.

While proving that, the same code block turned out to contain a real defect: micd logs a
false `raw microphone stream stopped` on every boot. It is fixed at the root (commit below).

## Evidence: the two pids are one parent and its stream worker

From `ps -o pid,ppid,pgid,sid,stat,etime,args` (`ps.txt`):

```
PID   PPID  PGID  SID   STAT ELAPSED COMMAND
 5498     1  5498  5498 S     5:53   libreecho-micd --foreground --socket /run/libreecho/mic.sock --capture-bin /sbin/tinycap
 5832     1  5832  5832 S     5:52   libreecho-waked ...
 6870  5498  5498  5498 S     5:51   libreecho-micd --foreground --socket /run/libreecho/mic.sock --capture-bin /sbin/tinycap
 6872  6870                    S     5:58   tinycap -- -D 0 -d 1 -c 8 -r 16000 -b 32 -p 640 -n 4
```

- `6870`'s parent is `5498`, same process group and session: it is a `fork()` of the daemon,
  not a process the init script started (that would have PPID 1).
- The pidfile `/var/run/libreecho-micd.pid` holds `5498` (`pidfile.txt`), so the launcher
  recorded the parent only.
- File descriptors (`sockets.txt`, `netunix.txt`):
  - `5498` holds the listener `socket:[8901]` = `/run/libreecho/mic.sock` (state 01, LISTEN).
  - `6870` holds `socket:[1974]`, the accepted client connection on the same path, and
    `pipe:[1979]`, the PCM pipe to `tinycap` `6872`.
  - `6870` has the listening socket closed, as the worker path does.
- The device log (`system-log.txt`) shows one daemon start and one stream start, 2 s apart,
  which matches the 2 s etime difference (5498 at boot+36, 6870 at boot+38):

```
{"ts":1795301768,...,"service":"micd","msg":"microphone daemon listening on /run/libreecho/mic.sock (capture idle)"}
{"ts":1795301770,...,"service":"micd","msg":"micd: Lidar OCM capture path configured (PGA 65%)"}
{"ts":1795301770,...,"service":"micd","msg":"calibrated mono microphone stream started"}
```

- The client on that stream is waked (`5832`, started boot+36); it requests `stream_mono`
  (`repos/LibreEcho-UI/src/adapter/waked.c:165`) and has no reconnect path, so the stream is
  meant to live for the whole boot.

Source: `repos/LibreEcho-UI/src/adapter/micd.c`

- `micd.c:1591` / `micd.c:1627`: `worker = fork()` for `stream_raw` / `stream_mono`.
- `micd.c:1596-1601` / `1632-1638`: child closes `listen_fd`, runs `run_stream_worker()`,
  `_exit(0)`.
- `micd.c:1605` / `1641`: the parent logs the stream start and keeps serving `status`,
  `beams` and the accept loop.
- `micd.c:1613-1620`: the same worker later `fork()`s once more and `execv`s tinycap, which
  is pid `6872`.

So `ps` legitimately shows two processes whose `argv` is identical while a stream is open.
`libreecho-micd.init:71-79` matches daemons by `argv[0]`, so it also sees the worker; that is
harmless for `status`/`stop` (the child is in the same process group and `stop_service`
sweeps every match), and the pidfile still names the parent.

## Real bug found at the same site (fixed)

The device log has a `raw microphone stream stopped` at boot+36 with **no** matching start,
before waked's mono stream exists and before `libreecho-web` (boot+41) can ask for a raw
stream. Cause, `micd.c:1519-1529` on base `27a4363`:

```c
if (child_changed || stream_worker > 0) {
    pid_t result = waitpid(stream_worker, &child_status, WNOHANG);  /* -1 = any child */
    child_changed = 0;
    if (result == stream_worker) {                                  /* -1 == -1 on ECHILD */
        ... le_log_info("raw microphone stream stopped"); stream_worker = -1;
```

`stream_worker` is `-1` as "no worker", but `-1` also means "any child" to `waitpid`. The
capture setup forks and reaps tinymix (`micd.c:390`, `micd.c:410`), and every one of those
children raises `SIGCHLD` (`child_handler`, `micd.c:218`). On the first loop iteration
`waitpid(-1, ..., WNOHANG)` finds no child left (`system`-style children were already
reaped), fails with `ECHILD` and returns `-1`, which compares equal to the sentinel. Result:
a false "stream stopped" at every boot (and a pointless `beam_view` reset).

Reproduced on the host with the base binary and the fixed one, same stub mixer/capture, no
stream request:

```
== prefix  10:04:30.462 microphone daemon listening ... (capture idle)
           10:04:30.462 raw microphone stream stopped
== fixed   10:04:32.562 microphone daemon listening ... (capture idle)
           (no stopped line)
```

Fix: only call `waitpid` when a worker exists, and require `stream_worker > 0` for the
"stopped" branch (`micd.c:1519-1535`).

## Commit

- Repo: `repos/LibreEcho-UI`, branch `fix/lidar-port-identity`
- Base: `27a4363a7612010e68e9b63683d6cce6a36cae53`
- Commit: `f43dadef8d6616812c53b38b1e3690491a1cacce` (`fix(micd): stop logging a phantom stream stop`)

## Build and tests run (host)

```
make BUILD=/tmp/le-micd-host.XXXXXX /tmp/le-micd-host.XXXXXX/libreecho-micd   # clean, -Wall -Wextra -Wpedantic
cc -D_POSIX_C_SOURCE=200809L -std=c99 -Wall -Wextra -Wpedantic -Werror -Isrc -Isrc/adapter \
   tests/test_micd.c src/adapter/mic_array_render.c src/adapter/adapter_client.c \
   src/adapter/adapter_server.c src/log.c -lm -o build/test-micd && ./build/test-micd
cc ... tests/test_micd_lidar.c src/adapter/mic_beamformer.c src/adapter/voice_dsp.c \
   src/adapter/adapter_server.c src/log.c -lm -o build/test-micd-lidar && ./build/test-micd-lidar
```

Both passed (`test-micd rc=0`, `test-micd-lidar rc=0`). The existing
`repos/LibreEcho-UI/build/` holds aarch64 objects from the OTA build, so the host build was
done in a separate `BUILD=` directory and that shared directory was left untouched.
The aarch64 compile of the changed file was not run (budget); the change is plain C in one
block and compiles clean on the host.

## What Main must rebuild to ship

Only `libreecho-micd` from `repos/LibreEcho-UI` on `fix/lidar-port-identity` (source change
in `src/adapter/micd.c`). No init script, profile or packaging change, so the next OTA needs
the normal UI component rebuild; nothing else in the image depends on it.

## Residual observations (not acted on)

- The worker keeps the logd socket and inherits the daemon's `argv`; only `ps` readability
  suffers, and renaming it would break `running_pids` in the init script, so it stays.
- If the parent ever died while a stream worker lived, `status` would be answered by nobody
  but `is_running` would still match the worker's `argv[0]`. Not observed; out of scope.
