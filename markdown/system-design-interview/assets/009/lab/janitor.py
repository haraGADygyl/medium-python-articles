"""Clears the users of gateways whose lease has expired, once a second."""
import asyncio
import time

import redis.asyncio as aioredis

from gateway import RELEASE, WHERE


async def main() -> None:
    r = aioredis.Redis(port=56379, decode_responses=True)
    release = r.register_script(RELEASE)
    while True:
        for gw in await r.smembers("gateways"):
            if await r.exists(f"gw:{gw}:alive"):
                continue
            members = f"gw:{gw}:users"
            users = await r.smembers(members)
            for uid in users:
                await release(keys=[WHERE, members], args=[uid, gw])
            await r.srem("gateways", gw)
            print(f"{time.time():.3f} janitor cleared {gw}: {len(users)} users",
                  flush=True)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
