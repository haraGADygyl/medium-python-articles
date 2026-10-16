"""The window design's write rate: N users, one ZADD every 30 s each, real time.

    python3 hb_fleet.py <users> <seconds>
"""
import asyncio
import random
import sys
import time

import redis.asyncio as aioredis


async def beat(r: aioredis.Redis, uid: int, stop: float) -> None:
    await asyncio.sleep(random.uniform(0, 30))
    while time.monotonic() < stop:
        await r.zadd("presence:online", {f"u{uid}": time.time()})
        await asyncio.sleep(30)


async def main(users: int, seconds: int) -> None:
    r = aioredis.Redis(port=56379, max_connections=64)
    await r.delete("presence:online")
    await asyncio.sleep(0)
    stop = time.monotonic() + 30 + seconds
    tasks = [asyncio.create_task(beat(r, u, stop)) for u in range(users)]
    await asyncio.sleep(30)                      # every user has started
    await r.config_resetstat()
    await asyncio.sleep(seconds)
    stats = await r.info("commandstats")
    calls = int(stats["cmdstat_zadd"]["calls"])
    print(f"window design, {users} connected users, {seconds} s: "
          f"{calls} ZADD = {calls / seconds:.1f} writes/s", flush=True)
    for t in tasks:
        t.cancel()
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]), int(sys.argv[2])))
