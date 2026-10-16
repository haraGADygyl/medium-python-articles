"""A connection gateway that owns presence for the users connected to it.

    python3 gateway.py <gateway id> <port>

Redis is written only when something changes: a user connects, a user leaves,
or a user stops answering pings. The gateway also renews its own lease once a
second; readers treat a gateway without a lease as dead, and its users offline.
Every offline event is logged to stdout with a wall-clock timestamp.
"""
import asyncio
import os
import random
import sys
import time

import redis.asyncio as aioredis

PING_S = float(os.environ.get("PING_S", "5"))   # gateway -> client ping
MISSES = 2                                       # unanswered pings = gone
LEASE_MS = 3000
RENEW_S = 1.0
WHERE = "presence:where"                         # hash: user -> gateway

RELEASE = """
if redis.call('HGET', KEYS[1], ARGV[1]) == ARGV[2] then
    redis.call('HDEL', KEYS[1], ARGV[1])
end
redis.call('SREM', KEYS[2], ARGV[1])
"""


class Gateway:
    def __init__(self, gw_id: str, r: aioredis.Redis) -> None:
        self.gw_id = gw_id
        self.r = r
        self.members = f"gw:{gw_id}:users"
        self.conns: dict[str, tuple[asyncio.StreamWriter, list[int]]] = {}
        self.release = r.register_script(RELEASE)

    async def claim(self, uid: str) -> None:
        async with self.r.pipeline(transaction=True) as pipe:
            pipe.hset(WHERE, uid, self.gw_id).sadd(self.members, uid)
            await pipe.execute()

    async def offline(self, uid: str, reason: str) -> None:
        self.conns.pop(uid, None)
        await self.release(keys=[WHERE, self.members], args=[uid, self.gw_id])
        print(f"{time.time():.3f} offline {uid} {reason}", flush=True)

    async def handle(self, reader: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        hello = await reader.readline()
        uid = hello.decode().split()[1]
        missed = [0]                         # pings since the last pong
        self.conns[uid] = (writer, missed)
        await self.claim(uid)
        try:
            while line := await reader.readline():
                if line == b"PONG\n":
                    missed[0] = 0
        except ConnectionError:
            pass
        if self.conns.get(uid, (None,))[0] is writer:   # not already reaped
            await self.offline(uid, "closed")
        writer.close()

    async def pinger(self) -> None:
        await asyncio.sleep(random.uniform(0, PING_S))  # gateways out of phase
        while True:
            for uid, (writer, missed) in list(self.conns.items()):
                if missed[0] >= MISSES:
                    await self.offline(uid, "no-pong")
                    writer.close()
                else:
                    missed[0] += 1
                    writer.write(b"PING\n")
            await asyncio.sleep(PING_S)

    async def lease(self) -> None:
        while True:
            await self.r.set(f"gw:{self.gw_id}:alive", 1, px=LEASE_MS)
            await asyncio.sleep(RENEW_S)


async def main(gw_id: str, port: int) -> None:
    r = aioredis.Redis(port=56379, decode_responses=True)
    gw = Gateway(gw_id, r)
    await r.sadd("gateways", gw_id)
    server = await asyncio.start_server(gw.handle, "127.0.0.1", port,
                                        backlog=4096)
    print(f"{time.time():.3f} ready {gw_id} {port}", flush=True)
    async with server:
        await asyncio.gather(server.serve_forever(), gw.pinger(), gw.lease())


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], int(sys.argv[2])))
