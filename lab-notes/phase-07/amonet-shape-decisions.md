# Ticket #2 threads and decisions

## Threads

1. The channel sits below the protocol. The simulator echoes the BROM handshake and every
   0xf00dd00d frame, so the tests drive the real framing, ordering and echo checks.
   Evidence: `modules/common.py:271-338` frames every read and write; a command-level fake
   would skip that code.
2. Every hardware fact carries its basis. The descriptor records value, basis and evidence for
   each address, and the payload build checks the link end and size against the same record.
   Evidence: proven values from `lab-notes/phase-01/brom-printgpt.log:44-96`; the SRAM window end
   is labelled inferred because no capture establishes it.

## Decisions

### A. Where the simulated BROM sits
- A: byte transport. The simulator speaks the BROM and payload command loops. Gain: tests catch
  framing and ordering drift. Cost: about 250 lines of simulator.
- B: session-level fake. The simulator exposes read and write methods. Gain: a smaller simulator.
  Cost: handshake, payload load and framing go untested.

### B. Where identity comes from
- A: BROM GET_HW_CODE plus a payload EXT_CSD read. Gain: hwcode and both sizes come from the unit,
  as mtkclient read them. Cost: one new payload opcode and a payload build change.
- B: GPT-derived geometry. Gain: no payload change. Cost: the GPT has no boot area size, so the
  identity JSON cannot report Boot1 size honestly.

### C. How the payload gets an MT8167 target
- A: in-place SoC target in `brom-payload/` (`SOC=mt8167`). Gain: one GPL2 program; upstream
  diffs stay readable. Cost: MT8167 constants share the tree with MT8163 and need guards.
- B: a separate `brom-payload-mt8167/` tree. Gain: no shared-file risk. Cost: a second copy of the
  driver tree to maintain.

### D. Where the reviewed backup lives for tests
- A: build the eMMC image at test time from the private reviewed backup, path in
  `LIDAR_BACKUP_DIR`. Gain: no device bytes enter the fork. Cost: the digest test needs the private
  fixture, so a bare clone cannot run that one test.
- B: commit the reviewed GPT and tee1 bytes under `tests/`. Gain: hermetic anywhere. Cost: commits
  device-read firmware, which the workspace contract forbids.
