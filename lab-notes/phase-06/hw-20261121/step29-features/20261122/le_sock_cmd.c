/* Throwaway test helper for the Lidar feature sweep: send one LibreEcho
 * adapter-envelope request to an AF_UNIX stream socket and print the reply.
 * usage: le_sock_cmd <socket> <cmd> [args-json] */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

int main(int argc, char **argv)
{
    struct sockaddr_un addr;
    char request[2048], reply[4096];
    ssize_t n;
    int fd;

    if (argc < 3) {
        fprintf(stderr, "usage: %s <socket> <cmd> [args-json]\n", argv[0]);
        return 2;
    }
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) { perror("socket"); return 1; }
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", argv[1]);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("connect");
        return 1;
    }
    snprintf(request, sizeof(request),
             "{\"v\":1,\"id\":1,\"cmd\":\"%s\",\"args\":%s}\n",
             argv[2], argc > 3 ? argv[3] : "{}");
    if (send(fd, request, strlen(request), 0) < 0) { perror("send"); return 1; }
    n = recv(fd, reply, sizeof(reply) - 1, 0);
    if (n <= 0) { perror("recv"); return 1; }
    reply[n] = 0;
    fputs(reply, stdout);
    close(fd);
    return 0;
}
