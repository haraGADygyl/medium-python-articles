"""Presence owned by gateways: write rate, logout, vanished phone, dead gateway.

    python3 gw_storm.py
"""
import asyncio
import os
import random
import re
import signal
import statistics
import subprocess
import sys
import time

import redis.asyncio as aioredis

from reader import online_by_gateway, online_by_window

PY = sys.executable
PORTS = [7101, 7102, 7103, 7104]
IDLE_PROCS, PER_PROC = 8, 1000
LEAVE = (8000, 50)                  # logs out cleanly
VANISH = (8050, 50)                 # phone in a tunnel: SIGSTOP, sockets open
VANISH_PROCS = 10                   # 5 users each, frozen at different moments
TOTAL = IDLE_PROCS * PER_PROC + LEAVE[1] + VANISH[1]
LOGS = "logs"


def spawn(args: list[str], log: str) -> subprocess.Popen:
    return subprocess.Popen([PY, *args], stdout=open(f"{LOGS}/{log}", "w"),
                            stderr=subprocess.STDOUT)


def offline_times(first: int, count: int, reason: str) -> dict[str, float]:
    """First offline event per user, from every gateway log."""
    wanted = {f"u{i}" for i in range(first, first + count)}
    seen: dict[str, float] = {}
    for name in os.listdir(LOGS):
        if not name.startswith("gw"):
            continue
        for line in open(f"{LOGS}/{name}"):
            m = re.match(rf"([\d.]+) offline (\S+) {reason}", line)
            if m and m[2] in wanted and m[2] not in seen:
                seen[m[2]] = float(m[1])
    return seen


async def counts(r: aioredis.Redis) -> dict[str, int]:
    stats = await r.info("commandstats")
    return {k.removeprefix("cmdstat_"): int(v["calls"]) for k, v in stats.items()}


def writes(stats: dict[str, int]) -> int:
    return sum(n for c, n in stats.items()
               if c in {"hset", "hdel", "sadd", "srem", "set", "evalsha"})


async def wait_for(r: aioredis.Redis, n: int, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while await r.hlen("presence:where") != n:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{await r.hlen('presence:where')} of {n} connected")
        await asyncio.sleep(0.2)


async def main() -> None:
    os.makedirs(LOGS, exist_ok=True)
    r = aioredis.Redis(port=56379, decode_responses=True)
    await r.flushall()
    gws = [spawn(["gateway.py", f"gw{i + 1}", str(p)], f"gw{i + 1}.log")
           for i, p in enumerate(PORTS)]
    janitor = spawn(["janitor.py"], "janitor.log")
    await asyncio.sleep(1.5)
    ports = [str(p) for p in PORTS]
    idle = [spawn(["clients.py", str(i * PER_PROC), str(PER_PROC), *ports],
                  f"idle{i}.log") for i in range(IDLE_PROCS)]
    leave = spawn(["clients.py", str(LEAVE[0]), str(LEAVE[1]), *ports], "leave.log")
    per = VANISH[1] // VANISH_PROCS
    vanish = [spawn(["clients.py", str(VANISH[0] + i * per), str(per), *ports],
                    f"vanish{i}.log") for i in range(VANISH_PROCS)]
    await wait_for(r, TOTAL)
    print(f"{TOTAL} users connected across {len(PORTS)} gateways, "
          f"ping every {os.environ.get('PING_S', '5')} s", flush=True)

    # 1. idle steady state: what does presence write when nothing happens?
    await asyncio.sleep(10)
    await r.config_resetstat()
    await asyncio.sleep(60)
    c = await counts(r)
    print(f"idle 60 s: {writes(c)} writes = {writes(c) / 60:.1f}/s  "
          f"({', '.join(f'{k} {v}' for k, v in sorted(c.items()) if k not in {'info', 'config|resetstat'})})",
          flush=True)

    # 2. churn: 1000 users log out and log back in
    await r.config_resetstat()
    idle[0].send_signal(signal.SIGTERM)
    idle[0].wait()
    await wait_for(r, TOTAL - PER_PROC)
    idle[0] = spawn(["clients.py", "0", str(PER_PROC), *ports], "idle0b.log")
    await wait_for(r, TOTAL)
    c = await counts(r)
    lease = c.get("set", 0)
    print(f"1000 logouts + 1000 logins: {writes(c) - lease} writes "
          f"= {(writes(c) - lease) / 1000:.1f} per logout-login pair "
          f"(lease renewals excluded: {lease})", flush=True)

    # 3. reads: 50 users on a search page, both designs
    users = [f"u{i}" for i in random.sample(range(TOTAL), 50)]
    now = time.time()
    await r.zadd("presence:online", {f"u{i}": now for i in range(TOTAL)})
    for name, fn in [("gateway (HMGET + MGET)", lambda: online_by_gateway(r, users)),
                     ("window (ZMSCORE)", lambda: online_by_window(r, users, time.time(), 90))]:
        for _ in range(200):
            await fn()
        samples = []
        for _ in range(3000):
            t0 = time.perf_counter()
            await fn()
            samples.append((time.perf_counter() - t0) * 1e6)
        q = statistics.quantiles(samples, n=100)
        print(f"read 50 users, {name}: p50 {q[49]:.0f} us  p99 {q[98]:.0f} us", flush=True)

    # 4. clean logout
    t0 = time.time()
    leave.send_signal(signal.SIGTERM)
    leave.wait()
    await asyncio.sleep(2)
    seen = offline_times(*LEAVE, "closed")
    lat = sorted((t - t0) * 1000 for t in seen.values())
    print(f"logout of {LEAVE[1]}: {len(seen)} offline, p50 {statistics.median(lat):.1f} ms, "
          f"max {lat[-1]:.1f} ms", flush=True)

    # 5. vanished phones: SIGSTOP, sockets stay open
    frozen_at: dict[str, float] = {}
    for i, proc in enumerate(vanish):
        await asyncio.sleep(random.uniform(0.3, 1.7))
        proc.send_signal(signal.SIGSTOP)
        for u in range(VANISH[0] + i * per, VANISH[0] + (i + 1) * per):
            frozen_at[f"u{u}"] = time.time()
    await asyncio.sleep(22)
    seen = offline_times(*VANISH, "no-pong")
    lat = sorted(t - frozen_at[u] for u, t in seen.items())
    print(f"vanish of {VANISH[1]}: {len(seen)} offline, p50 {statistics.median(lat):.1f} s, "
          f"min {lat[0]:.1f} s, max {lat[-1]:.1f} s", flush=True)
    for proc in vanish:
        proc.kill()

    # 6. a gateway dies silently (SIGSTOP: power loss, partition)
    victim = "gw4"
    members = sorted(await r.smembers(f"gw:{victim}:users"))
    sample = random.sample(members, 200)
    await r.config_resetstat()
    t0 = time.time()
    gws[3].send_signal(signal.SIGSTOP)
    first_off: dict[str, float] = {}
    back_on: dict[str, float] = {}
    while time.time() - t0 < 30:
        state = await online_by_gateway(r, sample)
        now = time.time() - t0
        for u, up in state.items():
            if not up and u not in first_off:
                first_off[u] = now
            if up and u in first_off and u not in back_on:
                back_on[u] = now
        await asyncio.sleep(0.05)
    off = sorted(first_off.values())
    gap = sorted(back_on[u] - first_off[u] for u in back_on)
    c = await counts(r)
    print(f"gateway {victim} frozen with {len(members)} users; sample of 200: "
          f"{len(first_off)} seen offline, first at {off[0]:.2f} s, "
          f"all by {off[-1]:.2f} s; {len(back_on)} back online, "
          f"offline for p50 {statistics.median(gap):.1f} s, max {gap[-1]:.1f} s", flush=True)
    print(f"  writes in the 30 s after the freeze: {writes(c)} "
          f"(lease renewals {c.get('set', 0)})", flush=True)
    print("  " + open(f"{LOGS}/janitor.log").read().strip().splitlines()[-1], flush=True)

    for p in [*idle, *gws, janitor]:
        p.kill()
    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
