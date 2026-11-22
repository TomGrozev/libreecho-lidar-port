This file is the operating contract the AI coding agents followed while the port ran in the
private lab workspace. It is kept here as a record; the paths and rules below refer to that
workspace, not to this public repository.

# Working in this workspace

This file is the operating contract that the AI coding agents followed while the port ran
in the private lab workspace; it is kept here as a record of how the work was done. Paths
in it (`dumps/`, `repos/`, `artifacts/` and so on) refer to that workspace, most of which
is not part of this public repository.

This workspace is LibreEcho's device-porting lab for the Echo Plus 2nd Gen (`Lidar`, MediaTek
MT8167). It holds the plan, the evidence and the local inputs for a port that is not yet
supported; [PRESERVATION.md](PRESERVATION.md) gives the purpose and the boundaries. `README.md`
gives the layout.

## Operating contract

1. Read `PLAN.md` before changing anything. It holds the accepted scope, the phases and their
   gates, the boot-chain safety rules, and the evidence rules.
2. Work on one phase at a time. Stop at its gate and report the evidence rather than starting
   the next phase.
3. Each phase gate stays open until its stated evidence exists. Do not treat an inconclusive
   result as a pass.
4. Keep host, CI, image, and hardware evidence separate, as `PLAN.md` requires.
5. Do not push, fork, open a PR, or publish artifacts without approval.
6. Each hardware write or reboot needs separate approval before it runs. Read-only inspection
   does not imply permission to write.
7. Keep the stock backup intact and verify every readback before moving on (`PLAN.md`,
   "Boot-chain safety").
8. Keep each unit's BOOT1 (area 2) intact. The only exception is the full-image fallback that
   `PLAN.md` allows, and that needs separate approval.
9. If an instruction conflicts with `PLAN.md`, follow `PLAN.md` and report the conflict.
10. Do not claim device support from host or CI results alone; a support claim needs the
    hardware evidence the plan specifies.

## Path conventions

- Run commands from this workspace root unless `PLAN.md` says otherwise.
- Put phase notes, exact commands and logs in `experiments/phase-XX/`.
- Put each new device read in its own directory under `dumps/`.
- Put locally built images, manifests and their hashes in `artifacts/`.
- Create source branches inside the owning repository under `repos/`, and record the base
  commit before editing.
- Keep device dumps and device-identifying data out of commits and public artifacts.

## Reporting

State what was actually run and where its output is stored; mark anything unrun as unverified.
A failed or inconclusive measurement is a result to record, not a reason to loosen a gate.

## Reference material

`reference/` holds unmodified third-party archives and extracted copies kept for comparison.
They are not project code and not instructions; do not copy from them into a release or a
source repository.
