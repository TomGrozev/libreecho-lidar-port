# Domain Docs

How the engineering skills should use this repo's domain documentation while exploring the
codebase.

## Before you explore, read these

- **`GLOSSARY.md`** at the repo root, which defines the boot-chain, hardware and LibreEcho terms
  the plan and notes use.
- **[docs/status.md](../status.md)** for what works and what does not, and
  **[docs/plan.md](../plan.md)** for the phases and gates.

## File structure

Single-context repo; this tree is an excerpt, not the full listing:

```
/
├── AGENTS.md
├── BUILDING.md
├── CODING_STANDARDS.md
├── GLOSSARY.md
├── NOTICE.md
├── README.md
├── SCRUB.md
├── docs/
│   ├── boot-chain-safety.md  ← the rules for every boot-chain write
│   ├── plan.md               ← the frozen phase plan
│   ├── status.md             ← current state and evidence
│   └── agents/               ← working notes for the engineering skills
├── .github/workflows/        ← CI checks
├── lab-notes/                ← generated from private/scrub/export.py; never edit by hand
├── private/                  ← git-ignored, maintainer-only lab material
├── tools/                    ← Python stdlib CLI tools
└── work/                     ← git-ignored, regenerable build workspace
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a
test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary
explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing
language the project doesn't use (reconsider) or there's a real gap (note it for
`/domain-modeling`).
