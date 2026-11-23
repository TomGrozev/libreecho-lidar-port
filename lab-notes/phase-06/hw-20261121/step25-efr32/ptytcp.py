#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""ptytcp: make a pty whose other end is a TCP connection.

Usage: ptytcp.py <host> <port>   -> prints the pty slave path on stdout, then
bridges until the TCP side closes.
"""
import asyncio
import os
import pty
import sys


async def main() -> None:
    host, port = sys.argv[1], int(sys.argv[2])
    master, slave = pty.openpty()
    print(os.ttyname(slave), flush=True)
    reader, writer = await asyncio.open_connection(host, port)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_pty():
        try:
            data = os.read(master, 4096)
        except OSError:
            data = b""
        queue.put_nowait(data)

    loop.add_reader(master, on_pty)

    async def tcp_to_pty():
        while True:
            data = await reader.read(4096)
            if not data:
                queue.put_nowait(b"")
                return
            os.write(master, data)

    async def pty_to_tcp():
        while True:
            data = await queue.get()
            if not data:
                return
            writer.write(data)
            await writer.drain()

    await asyncio.gather(tcp_to_pty(), pty_to_tcp())
    writer.close()


if __name__ == "__main__":
    asyncio.run(main())
