// SPDX-License-Identifier: GPL-2.0-only
/* ioctl-shim: let OpenThread's POSIX UART driver open a pty.
 * ot-cli clears DTR/RTS with TIOCMBIC, which a pty refuses; swallow the modem
 * control ioctls and pass everything else through.  Lab tool, never shipped.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <sys/ioctl.h>

int ioctl(int fd, unsigned long request, ...)
{
	static int (*real)(int, unsigned long, ...);
	va_list ap;
	void *arg;

	switch (request) {
	case TIOCMBIC:
	case TIOCMBIS:
	case TIOCMSET:
		return 0;
	}
	va_start(ap, request);
	arg = va_arg(ap, void *);
	va_end(ap);
	if (!real)
		real = dlsym(RTLD_NEXT, "ioctl");
	return real(fd, request, arg);
}
