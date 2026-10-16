"""Heartbeats into a Redis sorted set; how wide should the online window be?

N clients beat every INTERVAL (scaled: 1 lab second = SCALE real seconds).
A share of beats is lost, a share is delayed by a mobile-network stall.
A watcher turns "score within WINDOW of now" into online/offline events.
Some clients vanish without saying goodbye. Reported in real-world seconds.

    python3 window.py <window multiple of the interval> [seed]
"""
import asyncio
import random
import statistics
import sys
import time

import redis.asyncio as aioredis

SCALE = 10                    # 1 lab second = 10 real seconds
INTERVAL = 30 / SCALE         # 30 s heartbeat
N_CLIENTS = 2000
LOSS = 0.03                   # 3% of beats never arrive
STALL_P = 0.05                # 5% arrive late...
STALL_REAL = (2.0, 20.0)      # ...by 2-20 real seconds
BASE_REAL = (0.05, 0.30)      # everyone else: 50-300 ms
RUN = int(__import__("os").environ.get("RUN", 180))
VANISH = 200                  # clients that leave without a goodbye
TICK = 0.1                    # watcher period (1 real second)
KEY = "presence:online"


async def client(r, uid, rng, dead_at, stop):
    """Beat every INTERVAL until stopped or vanished."""
    await asyncio.sleep(rng.uniform(0, INTERVAL))       # spread start
    while not stop.is_set():
        if uid in dead_at and time.monotonic() >= dead_at[uid]:
            return                                       # gone, no goodbye
        if rng.random() >= LOSS:
            if rng.random() < STALL_P:
                delay = rng.uniform(*STALL_REAL) / SCALE
            else:
                delay = rng.uniform(*BASE_REAL) / SCALE
            asyncio.get_running_loop().call_later(
                delay, lambda u=uid: asyncio.ensure_future(arrive(r, u)))
        await asyncio.sleep(INTERVAL * rng.uniform(0.98, 1.02))


async def arrive(r, uid):
    await r.zadd(KEY, {str(uid): time.monotonic()})


async def main(multiple: float, seed: int) -> None:
    rng = random.Random(seed)
    window = multiple * INTERVAL
    r = aioredis.Redis(port=56379, decode_responses=True)
    await r.delete(KEY)
    await r.config_resetstat()
    start = time.monotonic()
    # vanish times uniformly in the middle of the run, after warm-up
    victims = rng.sample(range(N_CLIENTS), VANISH)
    dead_at = {u: start + rng.uniform(30, RUN - 30) for u in victims}
    stop = asyncio.Event()
    tasks = [asyncio.create_task(client(r, u, random.Random(seed * 7919 + u),
                                        dead_at, stop))
             for u in range(N_CLIENTS)]
    online: set[str] = set()
    flaps = 0                 # offline events for clients still alive
    ghosts: list[float] = []  # real seconds from vanishing to offline event
    warm = start + 2 * INTERVAL + window
    while time.monotonic() - start < RUN:
        await asyncio.sleep(TICK)
        now = time.monotonic()
        current = set(await r.zrangebyscore(KEY, now - window, "+inf"))
        if now >= warm:
            for uid in online - current:
                u = int(uid)
                if u in dead_at and dead_at[u] <= now:
                    ghosts.append((now - dead_at[u]) * SCALE)
                    del dead_at[u]
                else:
                    flaps += 1
        online = current
    stop.set()
    zadds = int((await r.info("commandstats"))["cmdstat_zadd"]["calls"])
    await asyncio.gather(*tasks, return_exceptions=True)
    alive_hours = (N_CLIENTS - VANISH / 2) * (RUN - (warm - start)) * SCALE / 3600
    q = statistics.quantiles(ghosts, n=20) if len(ghosts) > 1 else [0] * 19
    print(f"window {multiple:.1f}x = {window * SCALE:4.0f} s   "
          f"flaps/user-hour {flaps / alive_hours:5.2f}   "
          f"ghost p50 {statistics.median(ghosts):5.1f} s  p95 {q[18]:5.1f} s  "
          f"max {max(ghosts):5.1f} s  (n={len(ghosts)})   "
          f"zadd/s real {zadds / (RUN * SCALE):6.1f}  per user {zadds / (RUN * SCALE) / N_CLIENTS:.4f}")
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 1))
