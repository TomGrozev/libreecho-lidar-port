# UiApiFixes: step-33 API/UI port gaps

Base commit: `a9cea2ea5a0b605d574e1fb2ce9e407262c7fde3`
Branch: `fix/lidar-port-identity` (not committed; Main commits)

## Changed files

- `repos/LibreEcho-UI/src/service_env.h`: `LE_SERVICE_COMMAND_TIMEOUT_MS`
  (60000) and `le_service_command_timeout(path, argv, timeout_ms)`.
- `repos/LibreEcho-UI/src/service_env.c`: bounded single command, monotonic
  deadline, child `setpgid(0,0)`, SIGTERM then SIGKILL to the group on timeout,
  reaped result. `le_service_command` delegates with the default bound.
- `repos/LibreEcho-UI/src/api.c`
  - `run_init_command_timeout()`; `run_init_command()` delegates with default.
  - Voice-pipeline restart state machine: `voice_pipeline_restart_advance()`
    (collect-only when `allow_rollback == 0`), 90 s job deadline, 20 s
    per-command cap, TERM/KILL escalation, `voice_pipeline_rollback_needed`,
    `voice_pipeline_restart_timed_out`, `voice_pipeline_restart_phase()`.
    Reads (`api_handle`, `api_persist_configuration`) never fork or persist;
    the once-a-second `api_tick()` and the write handlers start rollback.
  - `voice_pipeline_json` emits `restart.phase` (`""`, `starting`,
    `rolling-back`).
  - `api_tick()` added; declared in `src/api.h`; called by the existing
    one-second tick in `src/http_server.c`.
  - `apply_voice_pipeline_mode` uses `advance(1)`, sets the job deadline and
    child process group.
  - Config import: removed the mock-only guard; errors map to
    400/501/503 (invalid / unsupported / failed apply).
  - Baby monitor: `baby_monitor_source_align()` rewrites the first micd source
    entry to the audio profile's capture card/device before returning status,
    so the stream endpoint's source matches the Lidar 0:1 profile.
- `repos/LibreEcho-UI/web/openapi.json`: `VoicePipelineRestart.phase` enum.
- `repos/LibreEcho-UI/web/js/integrations-ui.js`: pending label shows
  `Rolling back` when `restart.phase === "rolling-back"`.
- `repos/LibreEcho-UI/docs/API.md`: phase in both restart samples and the
  description of the read-only GET / tick-driven rollback.
- `repos/LibreEcho-UI/tests/test_service_env_isolation.c`: wedged script +
  `le_service_command_timeout(..., 200)` bounded-wait assertion.
- `repos/LibreEcho-UI/tests/test_voice_pipeline_restart.c`: failed forward
  reaped with `advance(0)` leaves `pending`/`rolling-back` and pid <= 0; the
  tick then starts rollback and it reports `failed`.
- `repos/LibreEcho-UI/tests/test_config_import_linux.c` (new): export then
  import with a Linux-mode backend; rejects `{}` as invalid; restored file is
  regular and mode 0600; re-export still parses.
- `repos/LibreEcho-UI/Makefile`: `build/test-config-import-linux` rule and
  `clean` entry.
- `repos/LibreEcho-UI/tests/run_tests.sh`: runs the new config-import test.
- `repos/LibreEcho-UI/tests/test_voice_pipeline_restart_contract.sh`: greps
  for advance/phase/tick contract.

## Snapshot-vs-rollback check

`voice_pipeline_restart_pending()` returns true for both a running child and a
queued `rollback_needed` state. Both callers (`api.c:2653`, `api.c:2916`) test
it before `voice_transition_capture()`, so a new write gets 409 and cannot
overwrite the saved snapshot. A GET calls only `advance(0)`, which leaves the
snapshot and `rollback_needed` intact.

## Verification

- `make build/test-service-env-isolation && ./build/test-service-env-isolation`:
  pass (including the 200 ms wedged-script bound).
- Direct compile of `tests/test_voice_pipeline_restart.c` (same flags as its
  Makefile rule) and run: pass, including the read-only phase case.
- `make build/test-config-import-linux && ./build/test-config-import-linux`:
  pass.
- `sh tests/test_voice_pipeline_restart_contract.sh`: pass.
- `jq -e . web/openapi.json` and `node --check web/js/integrations-ui.js`:
  pass.
- `cc ... -c src/api.c` and `src/http_server.c`: compile clean (only
  pre-existing warnings; repo host build does not use `-Werror`).
- `make build/libreecho-web` cannot link in this shared tree: `build/*.o`
  contains ARM objects from an earlier cross build
  (`build/inherited_fds.o: file in wrong format`). Not caused by these edits.

## Not done

- No device access, no commit/push.
- Full `make test` not run (same stale cross-object tree and scope).
