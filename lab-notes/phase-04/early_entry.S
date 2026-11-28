/*
 * Minimal ARM64 LK-entry probe for the Lidar (MT8167) boot image.
 *
 * Purpose: distinguish "LK entered this payload" from "LK fell back to the
 * stock boot path".  If this payload runs, it masks interrupts, disables the
 * SoC watchdog, and spins forever.  The device therefore stays stopped with
 * no further output.  If the device boots stock Android instead, this payload
 * was never entered.
 *
 * The file is a plain uncompressed arm64 Linux Image, not a Linux kernel:
 *   - LK loads it at kernel_addr 0x40080000 (Android v0 boot header).
 *   - The first instruction at the load address is the standard non-EFI NOP,
 *     followed by a branch to the entry code below.  No header parsing or
 *     relocation is required.
 *   - MMU, caches and stacks are not touched.  All state is in registers.
 *   - The loop is a busy branch, not WFI, so it cannot trap or depend on an
 *     interrupt controller or event stream.
 *
 * Watchdog semantics (source-verified):
 *   - The stock PVT DTB (appended DTB index 4, sha256 b5302d9e...) contains
 *     toprgu@10007000 with compatible "mediatek,mt8167-wdt",
 *     "mediatek,mt6589-wdt" and reg <0 0x10007000 0 0x1000>.
 *   - arch/arm64/boot/dts/mediatek/mt8167.dtsi:14 includes mt8516.dtsi,
 *     whose toprgu@10007000 node (mt8516.dtsi:205-210) has the same fallback
 *     compatible "mediatek,mt6589-wdt" and the same register range.
 *   - drivers/watchdog/mtk_wdt.c matches "mediatek,mt6589-wdt" (line 496) and
 *     defines WDT_MODE 0x00, WDT_MODE_EN (1 << 0), WDT_MODE_KEY 0x22000000
 *     (lines 45-53).
 *   - mtk_wdt_stop() (lines 308-320) reads WDT_MODE, clears WDT_MODE_EN, ORs
 *     WDT_MODE_KEY and writes the result back.  This payload performs exactly
 *     that sequence.
 *   Referenced tree: repos/LibreEcho-Linux (Linux 6.1 based).
 *
 * Build: experiments/phase-04/build_early_entry_probe.py
 */

	.section .text.early_entry, "ax"
	.global _start
_start:
	/* arm64 Image header, all fields little-endian. */
	nop				/* offset 0x00: non-EFI signature NOP */
	b	entry			/* offset 0x04: branch to entry code */
	.quad	0			/* 0x08: text_offset */
	.quad	_end - _start		/* 0x10: effective image size */
	.quad	0xa			/* 0x18: LE, 4K pages, phys base anywhere */
	.quad	0			/* 0x20: reserved */
	.quad	0			/* 0x28: reserved */
	.quad	0			/* 0x30: reserved */
	.ascii	"ARM\x64"		/* 0x38: ARM64 Image magic */
	.long	0			/* 0x3c: reserved (no PE header) */

entry:					/* 0x40 */
	msr	daifset, #0xf		/* mask D, A, I and F */
	movz	w1, #0x7000
	movk	w1, #0x1000, lsl #16	/* w1 = 0x10007000, TOPRGU base */
	ldr	w2, [x1]		/* w2 = WDT_MODE */
	bic	w2, w2, #1		/* clear WDT_MODE_EN */
	movz	w3, #0x2200, lsl #16	/* w3 = WDT_MODE_KEY */
	orr	w2, w2, w3		/* supply the write key */
	str	w2, [x1]		/* WDT_MODE = key | mode & ~EN */
1:
	b	1b			/* entered: stay here forever */
_end:
