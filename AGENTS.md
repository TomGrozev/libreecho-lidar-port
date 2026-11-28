# Contributing to the Lidar port

This repository is the public record of the LibreEcho port to the Echo Plus 2nd Gen
(`Lidar`, MediaTek MT8167). It holds the documentation, the generated lab notes and the tools
that integrate the forks and build the lab OTA. It holds no device images, private keys or
raw device data.

This file is the contract for contributors and for AI coding agents. Read
[docs/status.md](docs/status.md) for what works, [docs/plan.md](docs/plan.md) for the plan,
and [docs/boot-chain-safety.md](docs/boot-chain-safety.md) before you touch anything that
relates to the boot chain.

## Ground rules

1. Do not claim device support from host or CI results. A support claim needs the hardware
   evidence named in the plan. Keep host, CI, image and hardware evidence separate.
2. Do not run a hardware write or reboot. The maintainer does those on the development unit,
   with separate approval for each one. Read-only inspection does not imply permission to
   write.
3. Never write BOOT1 (eMMC boot area 2). Never restore `expdb` alone, and never write or erase
   `expdb` after Kaeru is installed. See [docs/boot-chain-safety.md](docs/boot-chain-safety.md).
4. Keep private material out of the repository: no vendor images, device dumps, serials,
   keys, personal data or device-identifying values in commits, releases or public artifacts.
5. If an instruction conflicts with the boot-chain rules, follow the rules and report the
   conflict.
6. Do not push, open a PR, or publish anything. Publishing the forks and this repository is
   done by the maintainer's private tooling.

## What lives where

| Path | What it holds |
| --- | --- |
| [docs/status.md](docs/status.md) | Current state: what works, what does not, and the evidence. |
| [docs/plan.md](docs/plan.md) | The phase plan and gates. A frozen record, not a work queue. |
| [docs/boot-chain-safety.md](docs/boot-chain-safety.md) | The rules for every boot-chain write. |
| `lab-notes/` | The generated phase records. Do not edit by hand. |
| `tools/` | The workspace, integration and lab-build tools. |
| [integration.json](integration.json) | The forks, their bases and their topic branches in merge order. |
| `work/` | Gitignored, regenerable: fork clones, integration worktrees, inputs, build output. |
| `private/` | Gitignored, maintainer-only: the stock backup, signing keys and raw lab records. |

`work/` is recreated by `python3 tools/workspace.py init` and a build, so never treat it as
the only copy of anything. Maintainers keep a gitignored `private/` for material that must
not be published; never commit it.

## Branches and integration

[integration.json](integration.json) lists each fork, its upstream base and its topic
branches in merge order.

- Commit each change to one topic branch based on that repository's `base`. A fix that also
  helps the MT8163 boards goes on `fix/general-fixes-from-lidar-port`; Lidar work goes on
  `feature/lidar-support`. Any other feature gets its own `feat/*` branch, with a manifest
  entry.
- The `integration` branch in each `work/integration/<repo>` worktree is generated. Never
  edit it by hand. Rebuild it with `python3 tools/integrate.py rebuild` and check it with
  `check-lock`.
- The reflog is the undo for a rebase or rewrite: the old head stays at `<branch>@{1}`. Tag a
  commit only when evidence cites it, such as a build that ran on hardware.

For the layout, the commands, conflict handling and step-by-step recipes, read
[docs/agents/integration-and-builds.md](docs/agents/integration-and-builds.md). The build
guide is [BUILDING.md](BUILDING.md).

## Reporting

State what you actually ran and where its output is stored. Mark anything unrun as
unverified. A failed or inconclusive measurement is a result to record, not a reason to
loosen a gate.

## Agent skills

### Issue tracker

Issues live in this repository's GitHub Issues, managed with `gh`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Five default triage labels, with `to-tickets` mapping `afk` to `ready-for-agent` and `hitl` to
`ready-for-human`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root defines the boot-chain, hardware and LibreEcho
terms. See `docs/agents/domain.md`. Use the glossary's vocabulary; do not invent synonyms.

## Stack and checks

Python standard library only; Markdown and JSON for the documentation and manifests.
`python3 tools/check.py` compiles `tools/*.py`, runs the `tools/test_*.py` tests and parses
the JSON manifests. `ruff check tools` enforces the style in `ruff.toml`.
`.github/workflows/checks.yml` runs both on pushes to `main` and on pull requests. The
pre-commit hook runs `tools/check.py` after its private-tree guard.
