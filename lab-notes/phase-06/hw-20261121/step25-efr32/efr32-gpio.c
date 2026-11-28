// SPDX-License-Identifier: GPL-2.0-only
/*
 * efr32-gpio: drive a named GPIO line through the GPIO character device
 * (v1 ABI), for the EFR32 radio's SWCLK and RESET_N lines.  The image has
 * no libgpiod, and /sys/class/gpio is not built in.
 *
 * Usage:
 *   efr32-gpio list                      print every named line
 *   efr32-gpio set <name> <0|1> [secs]   drive the line; keep holding it
 *                                        for secs (default: release now)
 *   efr32-gpio pulse <name> <ms>         drive low for ms, then release
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#define MAX_CHIPS 16

static int open_chip(int n, struct gpiochip_info *info)
{
	char path[32];
	int fd;

	snprintf(path, sizeof(path), "/dev/gpiochip%d", n);
	fd = open(path, O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		/* The image's static /dev has no GPIO nodes; mount devtmpfs
		 * elsewhere and fall back to it. */
		snprintf(path, sizeof(path), "/run/devtmpfs/gpiochip%d", n);
		fd = open(path, O_RDWR | O_CLOEXEC);
	}
	if (fd < 0)
		return -1;
	if (ioctl(fd, GPIO_GET_CHIPINFO_IOCTL, info) < 0) {
		close(fd);
		return -1;
	}
	return fd;
}

/* Finds the chip and offset of a line whose name matches. */
static int find_line(const char *name, int *chip, unsigned int *offset)
{
	struct gpiochip_info info;
	int n, fd;

	for (n = 0; n < MAX_CHIPS; n++) {
		struct gpioline_info line;
		unsigned int i;

		fd = open_chip(n, &info);
		if (fd < 0)
			continue;
		for (i = 0; i < info.lines; i++) {
			memset(&line, 0, sizeof(line));
			line.line_offset = i;
			if (ioctl(fd, GPIO_GET_LINEINFO_IOCTL, &line) < 0)
				continue;
			if (!strcmp(line.name, name)) {
				*chip = n;
				*offset = i;
				close(fd);
				return 0;
			}
		}
		close(fd);
	}
	return -1;
}

static int request_line(int chip, unsigned int offset, int value)
{
	struct gpiochip_info info;
	struct gpiohandle_request req;
	int fd;

	fd = open_chip(chip, &info);
	if (fd < 0)
		return -1;
	memset(&req, 0, sizeof(req));
	req.lineoffsets[0] = offset;
	req.lines = 1;
	req.flags = GPIOHANDLE_REQUEST_OUTPUT;
	req.default_values[0] = value;
	snprintf(req.consumer_label, sizeof(req.consumer_label), "efr32-gpio");
	if (ioctl(fd, GPIO_GET_LINEHANDLE_IOCTL, &req) < 0) {
		close(fd);
		return -1;
	}
	close(fd);
	return req.fd;
}

static int set_value(int fd, int value)
{
	struct gpiohandle_data data;

	memset(&data, 0, sizeof(data));
	data.values[0] = value;
	return ioctl(fd, GPIOHANDLE_SET_LINE_VALUES_IOCTL, &data);
}

static void list_lines(void)
{
	struct gpiochip_info info;
	int n, fd;

	for (n = 0; n < MAX_CHIPS; n++) {
		unsigned int i;

		fd = open_chip(n, &info);
		if (fd < 0)
			continue;
		for (i = 0; i < info.lines; i++) {
			struct gpioline_info line;

			memset(&line, 0, sizeof(line));
			line.line_offset = i;
			if (ioctl(fd, GPIO_GET_LINEINFO_IOCTL, &line) < 0)
				continue;
			if (line.name[0])
				printf("%s %s %u\n", info.name, line.name, i);
		}
		close(fd);
	}
}

int main(int argc, char **argv)
{
	int chip, fd, value, hold = 0;
	unsigned int offset;

	if (argc < 2) {
		fprintf(stderr, "usage: %s list | set <name> <0|1> [secs] | pulse <name> <ms>\n",
			argv[0]);
		return 2;
	}
	if (!strcmp(argv[1], "list")) {
		list_lines();
		return 0;
	}
	if (!strcmp(argv[1], "set") && (argc == 4 || argc == 5)) {
		value = atoi(argv[3]) ? 1 : 0;
		if (argc == 5)
			hold = atoi(argv[4]);
	} else if (!strcmp(argv[1], "pulse") && argc == 4) {
		value = 0;
		hold = -atoi(argv[3]);
	} else {
		fprintf(stderr, "bad arguments\n");
		return 2;
	}

	if (find_line(argv[2], &chip, &offset) < 0) {
		fprintf(stderr, "%s: no such line\n", argv[2]);
		return 1;
	}
	fd = request_line(chip, offset, value);
	if (fd < 0) {
		perror("request");
		return 1;
	}
	if (set_value(fd, value) < 0) {
		perror("set");
		return 1;
	}
	if (hold > 0)
		sleep(hold);
	else if (hold < 0)
		usleep(-hold * 1000);
	close(fd);
	return 0;
}
