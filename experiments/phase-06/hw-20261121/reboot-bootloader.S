/* Minimal static ARM32 helper: reboot(LINUX_REBOOT_CMD_RESTART2, "bootloader").
 * The 6.18 Lidar kernel exposes the Kaeru fastboot bit through syscon-reboot-mode,
 * so this names the mode and the notifier writes 0x10007024 bit 2 before restart.
 * No libc: only the reboot syscall, then exit(1) if it returns. */
	.syntax unified
	.arm
	.global _start
_start:
	ldr	r0, =0xfee1dead
	ldr	r1, =672274793
	ldr	r2, =0xa1b2c3d4
	adr	r3, mode
	mov	r7, #88		@ __NR_reboot
	svc	#0
	mov	r0, #1
	mov	r7, #1		@ __NR_exit
	svc	#0
mode:
	.asciz	"bootloader"
	.align	2
