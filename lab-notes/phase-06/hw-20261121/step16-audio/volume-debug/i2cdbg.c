/* Silent TLV320AIC3204 register probe via /dev/i2c-2.
 * Usage: i2cdbg <page> <reg> [<page> <reg> ...]
 * Reads the listed registers and always restores page 0 on exit.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <errno.h>

static int fd;

static int wr(unsigned char a, unsigned char v)
{
	struct i2c_msg m;
	unsigned char b[2] = { a, v };

	m.addr = 0x18; m.flags = 0; m.len = 2; m.buf = b;
	return ioctl(fd, I2C_RDWR, &(struct i2c_rdwr_ioctl_data){ .msgs = &m, .nmsgs = 1 }) == 1 ? 0 : -1;
}

static int set_page(int p)
{
	return wr(0x00, p);
}

static int rd(int page, int reg)
{
	struct i2c_msg m[2];
	unsigned char a = reg, v;
	int r;

	if (set_page(page)) return -2;
	m[0].addr = 0x18; m[0].flags = 0; m[0].len = 1; m[0].buf = &a;
	m[1].addr = 0x18; m[1].flags = I2C_M_RD; m[1].len = 1; m[1].buf = &v;
	r = ioctl(fd, I2C_RDWR, &(struct i2c_rdwr_ioctl_data){ .msgs = m, .nmsgs = 2 });
	if (r != 2) return -3;
	return v;
}

int main(int argc, char **argv)
{
	int i, rc = 0;

	fd = open("/tmp/i2c-2", O_RDWR);
	if (fd < 0) { perror("open"); return 1; }
	if (ioctl(fd, I2C_SLAVE_FORCE, 0x18) < 0) { perror("I2C_SLAVE_FORCE"); return 1; }

	for (i = 1; i + 1 < argc; i += 2) {
		int page = (int)strtol(argv[i], NULL, 0);
		int reg = (int)strtol(argv[i + 1], NULL, 0);
		int v;

		if (page < 0) {
			/* Read without touching the page register */
			struct i2c_msg m[2];
			unsigned char a = reg, tmp;
			int r;

			m[0].addr = 0x18; m[0].flags = 0; m[0].len = 1; m[0].buf = &a;
			m[1].addr = 0x18; m[1].flags = I2C_M_RD; m[1].len = 1; m[1].buf = &tmp;
			r = ioctl(fd, I2C_RDWR, &(struct i2c_rdwr_ioctl_data){ .msgs = m, .nmsgs = 2 });
			v = r == 2 ? (unsigned char)tmp : (r == -1 ? -errno : -3);
			page = -1;
		} else {
			v = rd(page, reg);
		}
		if (v < 0) {
			printf("p%d[0x%02x]=ERR%d\n", page, reg, v);
			rc = 1;
		} else {
			printf("p%d[0x%02x]=0x%02x\n", page, reg, v);
		}
	}
	/* Leave the codec on page 0, the state every normal access assumes. */
	set_page(0);
	close(fd);
	return rc;
}
