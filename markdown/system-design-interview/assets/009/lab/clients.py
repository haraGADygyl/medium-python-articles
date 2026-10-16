"""N simulated users holding one TCP connection each to a gateway.

    python3 clients.py <first user id> <count> <port> [<port> ...]

Answers every PING with PONG. SIGTERM closes every connection cleanly (the
user logs out). SIGSTOP from the harness freezes the process with its sockets
still open (the phone went into a tunnel). If a gateway drops the connection,
or sends nothing for three ping intervals, the user reconnects to the next gateway after 0-2 s of jitter.
"""
import asyncio
import os
import random
import signal
import sys
import time


SILENCE_S = 3 * float(os.environ.get("PING_S", "5"))   # no ping: gateway is gone


async def user(uid: int, ports: list[int], stop: asyncio.Event) -> None:
    attempt = uid
    while not stop.is_set():
        port = ports[attempt % len(ports)]
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            attempt += 1
            await asyncio.sleep(random.uniform(0, 2))
            continue
        writer.write(f"HELLO u{uid}\n".encode())
        closing = asyncio.create_task(stop.wait())
        try:
            while True:
                line_task = asyncio.create_task(reader.readline())
                done, _ = await asyncio.wait({line_task, closing},
                                             timeout=SILENCE_S,
                                             return_when=asyncio.FIRST_COMPLETED)
                if not done:
                    line_task.cancel()
                    break                       # silent gateway: go elsewhere
                if closing in done:
                    line_task.cancel()
                    writer.close()
                    return
                line = line_task.result()
                if not line:
                    break                       # gateway went away
                if line == b"PING\n":
                    writer.write(b"PONG\n")
        except ConnectionError:
            pass
        closing.cancel()
        writer.close()
        attempt += 1
        await asyncio.sleep(random.uniform(0, 2))


async def main(first: int, count: int, ports: list[int]) -> None:
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    tasks = []
    for uid in range(first, first + count):
        tasks.append(asyncio.create_task(user(uid, ports, stop)))
        if len(tasks) % 200 == 0:
            await asyncio.sleep(0.05)           # don't SYN-flood the gateways
    await asyncio.gather(*tasks)
    await asyncio.sleep(0.2)                    # let the FINs go out
    print(f"{time.time():.3f} logged out {count}", flush=True)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2]),
                     [int(p) for p in sys.argv[3:]]))
