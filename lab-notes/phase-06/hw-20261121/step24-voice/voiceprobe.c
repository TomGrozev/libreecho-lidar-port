/* Step 24 silent voice probe: talk to libreecho unix-socket adapters without
 * a shell.  Two modes:
 *   send <socket> <request-line> <pcm-file> <out-file>
 *        send the JSON request line, read the reply line, stream the raw
 *        pcm file, then collect events until the peer closes.
 *   recv <socket> <request-line> <seconds> <out-file>
 *        send the request, then capture the peer's stream for N seconds.
 * Static armhf build for the Lidar image (libreecho-local has no CLI).
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static int connect_unix(const char *path)
{
    struct sockaddr_un addr;
    int fd;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof(addr.sun_path)) return -1;
    strcpy(addr.sun_path, path);
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static int write_all(int fd, const char *buf, size_t len)
{
    size_t off = 0;
    while (off < len) {
        ssize_t n = write(fd, buf + off, len - off);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        off += (size_t)n;
    }
    return 0;
}

/* Copy everything the peer writes until EOF or the deadline. */
static int drain(int fd, FILE *out, int timeout_ms)
{
    char buf[8192];
    struct pollfd p = {.fd = fd, .events = POLLIN};
    for (;;) {
        int r = poll(&p, 1, timeout_ms);
        if (r < 0 && errno == EINTR) continue;
        if (r <= 0) return 0;
        ssize_t n = read(fd, buf, sizeof(buf));
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        fwrite(buf, 1, (size_t)n, out);
        fflush(out);
    }
}

int main(int argc, char **argv)
{
    if (argc < 5) {
        fprintf(stderr, "usage: %s send|recv socket request pcm|seconds out\n",
                argv[0]);
        return 2;
    }
    int fd = connect_unix(argv[2]);
    if (fd < 0) { perror("connect"); return 1; }
    char line[512];
    int n = snprintf(line, sizeof(line), "%s\n", argv[3]);
    if (n <= 0 || write_all(fd, line, (size_t)n) < 0) { perror("write"); return 1; }

    FILE *out = fopen(argv[5], "wb");
    if (!out) { perror("open out"); return 1; }

    if (!strcmp(argv[1], "recv")) {
        /* Nothing else to send: read the stream for the requested seconds. */
        long seconds = strtol(argv[4], NULL, 10);
        drain(fd, out, (int)(seconds > 0 ? seconds * 1000 : 5000));
        fclose(out);
        return 0;
    }

    /* send: emit the reply line, then the PCM payload, then half-close. */
    char reply[1024];
    size_t used = 0;
    while (used + 1 < sizeof(reply)) {
        if (read(fd, reply + used, 1) != 1) break;
        if (reply[used++] == '\n') break;
    }
    reply[used] = '\0';
    printf("reply: %s", reply);

    FILE *pcm = fopen(argv[4], "rb");
    if (!pcm) { perror("open pcm"); return 1; }
    char buf[8192];
    size_t got;
    while ((got = fread(buf, 1, sizeof(buf), pcm)) > 0) {
        if (write_all(fd, buf, got) < 0) { perror("pcm write"); return 1; }
    }
    fclose(pcm);
    shutdown(fd, SHUT_WR);
    drain(fd, out, 30000);
    fclose(out);
    return 0;
}
