/* ARM64 control: mark RAM, wait five seconds, then reset into Kaeru fastboot. */
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

	mrs	x8, cntfrq_el0
	movz	x9, #5
	mul	x8, x8, x9
	mrs	x10, cntpct_el0
	add	x8, x8, x10
1:
	mrs	x10, cntpct_el0
	cmp	x10, x8
	b.lo	1b

	/* Match the bootchain's hardware-proven fastboot restart sequence. */
	movz	w2, #0x1971
	str	w2, [x1, #0x08]
	ldr	w2, [x1, #0x24]
	orr	w2, w2, #4
	str	w2, [x1, #0x24]
	movz	w3, #0x0014
	movk	w3, #0x2200, lsl #16
	str	w3, [x1]
	dsb	sy
	movz	w2, #0x1209
	str	w2, [x1, #0x14]
2:
	b	2b

	.align	3
marker:
	.ascii	"LIBREECHORAMMRK!"
_end:
