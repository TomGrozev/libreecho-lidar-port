// SPDX-License-Identifier: GPL-2.0-only
/* tcp-uart: bridge one TCP client to a serial port, both directions.
 * Local lab tool: lets a host-side Zigbee/Thread stack reach the EFR32 over
 * the LAN while the Echo UART stays on the device.  One client at a time.
 *
 * Usage: tcp-uart <tty> <port>
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

static void setraw(int fd, speed_t speed)
{
	struct termios t;

	if (tcgetattr(fd, &t) < 0)
		return;
	cfmakeraw(&t);
	cfsetispeed(&t, speed);
	cfsetospeed(&t, speed);
	t.c_cflag &= ~CRTSCTS;
	tcsetattr(fd, TCSANOW, &t);
}

int main(int argc, char **argv)
{
	struct sockaddr_in addr;
	int srv, cli, tty, one = 1;
	char buf[4096];

	if (argc != 3) {
		fprintf(stderr, "usage: %s <tty> <port>\n", argv[0]);
		return 2;
	}
	tty = open(argv[1], O_RDWR | O_NOCTTY);
	if (tty < 0) {
		perror("tty");
		return 1;
	}
	setraw(tty, B115200);

	srv = socket(AF_INET, SOCK_STREAM, 0);
	setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_addr.s_addr = htonl(INADDR_ANY);
	addr.sin_port = htons(atoi(argv[2]));
	if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(srv, 1) < 0) {
		perror("listen");
		return 1;
	}
	for (;;) {
		cli = accept(srv, NULL, NULL);
		if (cli < 0)
			continue;
		for (;;) {
			struct pollfd p[2] = { { tty, POLLIN, 0 }, { cli, POLLIN, 0 } };
			int i, n;

			if (poll(p, 2, -1) < 0) {
				if (errno == EINTR)
					continue;
				break;
			}
			for (i = 0; i < 2; i++) {
				if (!(p[i].revents & (POLLIN | POLLHUP | POLLERR)))
					continue;
				n = read(p[i].fd, buf, sizeof(buf));
				if (n <= 0)
					goto next_client;
				if (write(p[i].fd == tty ? cli : tty, buf, n) != n)
					goto next_client;
			}
		}
next_client:
		close(cli);
	}
}
