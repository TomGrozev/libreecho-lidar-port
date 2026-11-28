/* ARM64 entry control: write a known marker to reserved RAM, then stop. */
	.section .text.early_entry, "ax"
	.global _start
_start:
	nop
	b	entry
	.quad	0
	.quad	_end - _start
	.quad	0xa
	.quad	0
	.quad	0
	.quad	0
	.ascii	"ARM\x64"
	.long	0

entry:
	msr	daifset, #0xf
	movz	w1, #0x7000
	movk	w1, #0x1000, lsl #16
	ldr	w2, [x1]
	bic	w2, w2, #1
	movz	w3, #0x2200, lsl #16
	orr	w2, w2, w3
	str	w2, [x1]

	movz	x4, #0x0000
	movk	x4, #0x4440, lsl #16
	adr	x5, marker
	ldp	x6, x7, [x5]
	stp	x6, x7, [x4]
	dmb	sy
1:
	b	1b

	.align	3
marker:
	.ascii	"LIBREECHORAMMRK!"
_end:
