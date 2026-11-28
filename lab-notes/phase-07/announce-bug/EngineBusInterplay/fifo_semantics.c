/* Host reproduction of the engine's system.pcm fd lifecycle.
 *
 * Mirrors audio_engine.c setup_sources(): the engine holds every bus FIFO
 * open O_RDWR|O_NONBLOCK for its whole lifetime.  Checks what a producer
 * (esphomed: O_WRONLY|O_NONBLOCK) can observe: open failure, first-write
 * failure, short writes, EAGAIN when full, and EPIPE only after the engine
 * fd closes.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int failures;

static void check(int cond, const char *what)
{
    printf("%s %s\n", cond ? "PASS" : "FAIL", what);
    if (!cond) failures++;
}

int main(void)
{
    const char *path = "/tmp/le-fifo-semantics.pcm";
    unsigned char buf[4096];
    int engine, writer;
    ssize_t n;
    long total = 0;
    int saw_eagain = 0, saw_short = 0, saw_epipe = 0;

    signal(SIGPIPE, SIG_IGN);
    unlink(path);
    if (mkfifo(path, 0600) < 0) { perror("mkfifo"); return 1; }
    memset(buf, 0x5a, sizeof buf);

    /* No reader: producer's non-blocking open must fail ENXIO. */
    errno = 0;
    writer = open(path, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
    check(writer < 0 && errno == ENXIO, "no engine fd -> O_WRONLY|O_NONBLOCK open ENXIO");

    /* Engine lifetime fd: one O_RDWR open, exactly as setup_sources() does. */
    engine = open(path, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    check(engine >= 0, "engine O_RDWR|O_NONBLOCK open");

    /* Producer open succeeds while the engine holds its RDWR fd, even though
     * the engine never reads in this test. */
    writer = open(path, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
    check(writer >= 0, "producer O_WRONLY|O_NONBLOCK open succeeds with engine fd held");

    /* First write: the FIFO is empty, so one esphomed chunk fits whole. */
    errno = 0;
    n = write(writer, buf, 1024 * 4);
    check(n == 4096, "first 4096-byte write is complete");
    if (n > 0) total += n;

    /* Fill until the ring is full. Never EPIPE while the engine fd is open. */
    for (int i = 0; i < 1000; ++i) {
        errno = 0;
        n = write(writer, buf, sizeof buf);
        if (n > 0) {
            total += n;
            if (n < (ssize_t)sizeof buf) saw_short = 1;
            continue;
        }
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) { saw_eagain = 1; break; }
        if (n < 0 && errno == EPIPE) saw_epipe = 1;
        printf("unexpected write result n=%zd errno=%d (%s)\n", n, errno, strerror(errno));
        break;
    }
    printf("fifo capacity ~= %ld bytes\n", total);
    check(saw_eagain && !saw_epipe, "full FIFO -> EAGAIN, never EPIPE while engine fd open");
    printf("short write observed: %s\n", saw_short ? "yes" : "no (4096-byte chunks fit)");

    /* The engine never reads in this test; a full ring is exactly the
     * backpressure case. Drain one period the way read_sources() would. */
    n = read(engine, buf, sizeof buf);
    check(n == 4096, "engine fd can still read after producer fill");
    errno = 0;
    n = write(writer, buf, sizeof buf);
    check(n == 4096, "space freed by engine read -> write accepted again");

    /* Engine exit/restart closes its RDWR fd; then, and only then, the
     * producer's next write has no reader and reports EPIPE. */
    close(engine);
    for (;;) {
        errno = 0;
        n = write(writer, buf, sizeof buf);
        if (n < 0 && errno == EPIPE) { saw_epipe = 1; break; }
        if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            /* still full; drain via a temporary reader? no: closing engine
             * already left only the writer, but the ring still holds data,
             * so EAGAIN can persist. Retry after a read is impossible. */
            break;
        }
        if (n <= 0) break;
    }
    check(saw_epipe, "after engine fd closes, write EPIPE (engine exit only)");

    close(writer);
    unlink(path);
    printf("%s\n", failures ? "HARNESS FAILED" : "ALL CHECKS PASSED");
    return failures != 0;
}
