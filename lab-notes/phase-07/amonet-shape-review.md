# Amonet on MT8167: shape review

Ticket #2, gate before build. Reason: new structure, a new fork and the first MT8167 device
module, which the later tickets copy.

Ticket #2 makes a source-built BROM route reach a Lidar, print its identity as JSON and read
the boot chain. The route uses no download agent, and the host suite uses no USB.

## Acceptance examples
- Given a simulated BROM built from the reviewed backup, when the host asks for identity, then
  it prints hwcode 0x8167, USER size 7650410496, Boot1 size 2097152 and sector size 512 as JSON.
- Given the same simulator, when the host reads the `gpt` area and the `tee1` partition, then
  each digest equals the reviewed backup digest.
- Given a simulator that reports hwcode 0x8163, when the host asks for identity, then it
  refuses before it loads the payload.

## Placement map
- NEW `modules/device_descriptor.py`: the MT8167 descriptor, with each address labelled proven
  or inferred. Why new: upstream device data is a dict entry and a generated `device.prop`,
  with no geometry or address record.
- NEW `modules/channel.py`: the one byte channel seam. The real channel is USB 0e8d:0003.
- NEW `modules/brom.py`: the session, identity, area read and absolute read. Why new: upstream
  `modules/main.py` is a one-shot install chain, not a command surface.
- NEW `modules/lidar_brom.py`: the CLI with `identity` and `read`.
- NEW `modules/sim/`: the simulated BROM and the partitioned eMMC image built from the reviewed
  backup. Why new: upstream has no tests and no simulated device.
- NEW `tests/`: the hermetic suite over the simulated channel.
- CHANGED `modules/common.py`: `Device` accepts an injected channel.
- CHANGED `brom-payload/`: an MT8167 SoC target, an EXT_CSD read command, and link-map and size
  assertions. The payload stays the upstream GPL2 program, invoked from disk.
- REUSED `modules/gpt.py`: the reviewed GPT parser, unchanged.
- REMOVED nothing at this ticket.

## Surface for the later tickets
`BromSession` gains the write methods at ticket #3, and the Platform adapter at ticket #4 calls
the CLI, so the command grammar and the identity JSON are the contract to review now.
