# Coding standards

These rules apply to the published tree. `AGENTS.md` holds the operating contract and
`PLAN.md` the phase gates, so those rules are not repeated here. Ruff enforces the Python
style from `ruff.toml`, and `python3 tools/check.py` checks syntax and the JSON manifests.

## Code

- Keep `tools/` on the Python 3 standard library. A new dependency needs an ADR.
- Give each tool one file. Put its commands, inputs and outputs in the module docstring, and
  expose the commands as argparse subcommands.
- Emit one `PASS`, `FAIL`, `INFO` or `WARN` line per step, so the written log is the report.
- Pin every external build input in JSON by workspace-relative path and sha256, and verify it
  before use.

## Records

- Cite evidence as `path:line`. Mark a conclusion that no direct capture proves with
  `[INFERENCE]`.
- Close each experiment record with `## Unverified`, listing what was not run or could not be
  measured.

## Known inconsistencies

The two tools differ in these places. Treat this list as work for a later change, not as a
rule.

- A fatal error prints `error: <message>` and exits 2 in `tools/integrate.py`, and
  `ERROR: <message>` and exits 1 in `tools/lab-build.py`.
- The JSON read helpers are `load_json` and `read_json`.
- `tools/integrate.py` uses double quotes; `tools/lab-build.py` uses single quotes.
- The entrypoints are `sys.exit(main())` and `raise SystemExit(main(...))`.
