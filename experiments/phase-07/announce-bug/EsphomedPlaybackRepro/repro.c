/* Throwaway reproduction harness for the Lidar announcement playback_error.
 * Drives the real esp_playback tick loop (instrumented copy, identical line
 * layout) over a socketpair with a regular-file bus sink, and reports which
 * fail site fired, how long after the first bus write, and the stream shape.
 *
 * usage: repro <body.wav|body.mp3> <framing> <splits...>
 *   framing: chunked:N  (chunks of N payload bytes; 0 = one chunk)
 *            content-length
 *   splits:  byte offsets of TCP write boundaries into the wire stream
 *            (default: send everything at once)
 */
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/ioctl.h>
#include <unistd.h>

int esphome_fail_line;
#include "playback_instrumented.c"

#define MAXWIRE (4u*1024u*1024u)
static unsigned char body[MAXWIRE];
static unsigned char wire[MAXWIRE];
static size_t body_n, wire_n;

static void put32(unsigned char *b, uint32_t v)
{
    for (unsigned i = 0; i < 4; i++) b[i] = (unsigned char)(v >> (8 * i));
}

static size_t add_chunk(size_t off, const unsigned char *p, size_t n)
{
    int z = snprintf((char *)wire + off, 32, "%zx\r\n", n);
    if (z <= 0) return 0;
    off += (size_t)z;
    memcpy(wire + off, p, n); off += n;
    wire[off++] = '\r'; wire[off++] = '\n';
    return off;
}

static size_t build_wire(const char *framing)
{
    size_t off;
    int cl = !strcmp(framing, "content-length");
    int chunk = 0;
    unsigned sizes[512], nsizes = 0;

    if (!cl && !strncmp(framing, "chunks:", 7)) {
        const char *q = framing + 7;
        while (*q && nsizes < 512) {
            sizes[nsizes++] = (unsigned)strtoul(q, (char **)&q, 10);
            if (*q == ',') q++;
        }
        chunk = -1;
        off = (size_t)snprintf((char *)wire, 256,
            "HTTP/1.1 200 OK\r\n"
            "Server: Home Assistant\r\n"
            "Content-Type: audio/wav\r\n"
            "Transfer-Encoding: chunked\r\n"
            "Connection: close\r\n\r\n");
        {
            size_t at = 0;
            for (unsigned i = 0; at < body_n; i++) {
                size_t n = sizes[i % nsizes];
                if (!n || n > body_n - at) n = body_n - at;
                off = add_chunk(off, body + at, n);
                at += n;
            }
        }
        memcpy(wire + off, "0\r\n\r\n", 5); off += 5;
    } else if (!cl) {
        if (sscanf(framing, "chunked:%d", &chunk) != 1 || chunk < 0) {
            fprintf(stderr, "bad framing %s\n", framing); exit(2);
        }
        off = (size_t)snprintf((char *)wire, 256,
            "HTTP/1.1 200 OK\r\n"
            "Server: Home Assistant\r\n"
            "Content-Type: audio/wav\r\n"
            "Transfer-Encoding: chunked\r\n"
            "Connection: close\r\n\r\n");
        if (chunk == 0) {
            off = add_chunk(off, body, body_n);
        } else if (chunk < 0) {
            size_t at = 0;
            for (unsigned i = 0; at < body_n; i++) {
                size_t n = sizes[i % nsizes];
                if (!n || n > body_n - at) n = body_n - at;
                off = add_chunk(off, body + at, n);
                at += n;
            }
        } else {
            for (size_t at = 0; at < body_n; at += (size_t)chunk) {
                size_t n = body_n - at < (size_t)chunk ? body_n - at : (size_t)chunk;
                off = add_chunk(off, body + at, n);
            }
        }
        memcpy(wire + off, "0\r\n\r\n", 5); off += 5;
    } else {
        off = (size_t)snprintf((char *)wire, 256,
            "HTTP/1.1 200 OK\r\n"
            "Server: Home Assistant\r\n"
            "Content-Type: audio/wav\r\n"
            "Content-Length: %zu\r\n"
            "Connection: close\r\n\r\n", body_n);
        memcpy(wire + off, body, body_n); off += body_n;
    }
    return off;
}

int main(int argc, char **argv)
{
    static struct esp_playback p;
    static char bus[512], dir[] = "/tmp/lidar-repro-XXXXXX";
    size_t splits[4096];
    unsigned nsplits = 0;
    int f[2], sink, rc = 0;
    uint64_t now = 0, first_write_at = 0, fail_at = 0;
    size_t sent = 0, last_size = 0, writes = 0, wrote_at_first = 0;

    if (argc < 3) { fprintf(stderr, "usage: %s body framing [split...]\n", argv[0]); return 2; }
    {
        FILE *fp = fopen(argv[1], "rb");
        if (!fp) { perror(argv[1]); return 2; }
        body_n = fread(body, 1, sizeof body, fp);
        if (ferror(fp) || !feof(fp)) { fprintf(stderr, "body too large\n"); return 2; }
        fclose(fp);
    }
    wire_n = build_wire(argv[2]);
    for (int i = 3; i < argc && nsplits < sizeof splits / sizeof *splits; i++)
        splits[nsplits++] = (size_t)strtoull(argv[i], NULL, 10);

    if (!mkdtemp(dir)) { perror("mkdtemp"); return 2; }
    snprintf(bus, sizeof bus, "%s/bus.pcm", dir);
    sink = open(bus, O_CREAT | O_RDWR | O_TRUNC, 0600);
    if (sink < 0) { perror(bus); return 2; }
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, f) != 0) { perror("socketpair"); return 2; }

    esp_playback_init(&p);
    p.fd = f[0]; p.state = 5; p.fetching = 1;
    p.expected = SIZE_MAX; p.deadline = 1000000;
    snprintf(p.bus, sizeof p.bus, "%s", bus);

    for (unsigned i = 0; i <= nsplits; i++) {
        size_t end = i < nsplits ? (splits[i] < wire_n ? splits[i] : wire_n) : wire_n;
        if (end > sent) {
            if (send(f[1], wire + sent, end - sent, MSG_NOSIGNAL) != (ssize_t)(end - sent)) {
                perror("send"); return 2;
            }
            sent = end;
        }
        /* One daemon iteration per TCP arrival, 10 ms poll like esphomed. */
        rc = esp_playback_tick(&p, now += 10);
        {
            off_t sz = lseek(sink, 0, SEEK_END);
            if ((size_t)sz > last_size) {
                if (!writes) first_write_at = now;
                writes++; last_size = (size_t)sz;
                wrote_at_first = p.frames;
            }
        }
        if (rc) { fail_at = now; break; }
    }
    if (!rc) {
        shutdown(f[1], SHUT_WR);
        for (unsigned i = 0; i < 8000 && !rc; i++) {
            rc = esp_playback_tick(&p, now += 10);
            {
                off_t sz = lseek(sink, 0, SEEK_END);
                if ((size_t)sz > last_size) {
                    if (!writes) first_write_at = now;
                    writes++; last_size = (size_t)sz;
                }
            }
            if (rc) fail_at = now;
        }
    }
    lseek(sink, 0, SEEK_END);
    printf("framing=%s wire=%zu sent=%zu rc=%d fail_line=%d state=%d result=%d frames=%llu "
           "bus_bytes=%zu writes=%zu first_write_at=%llu fail_at=%llu "
           "eof=%d fetching=%d chunk_left=%zu position=%zu body_len=%zu received=%zu "
           "wrote_before_first_frame=%zu\n",
           argv[2], wire_n, sent, rc, esphome_fail_line, p.state, p.result,
           (unsigned long long)p.frames, (size_t)lseek(sink, 0, SEEK_END), writes,
           (unsigned long long)first_write_at, (unsigned long long)fail_at,
           p.eof, p.fetching, p.chunk_left, p.position, p.body_len, p.received,
           wrote_at_first);
    esp_playback_close(&p);
    close(f[0]); close(f[1]); close(sink);
    unlink(bus); rmdir(dir);
    return rc > 0 ? 0 : 1;
}
