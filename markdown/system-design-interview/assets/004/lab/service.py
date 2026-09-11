"""The downstream service: bounded capacity, a capacity collapse, honest stats."""
import argparse
import asyncio
import json
import time

from aiohttp import web

WORK_SECONDS = 0.025      # one dependency round trip per request
BUCKET = 0.1              # stats resolution


class Limiter:
    """A pool of concurrent slots whose size can change mid-flight."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.in_use = 0
        self.waiting = 0
        self.cond = asyncio.Condition()

    async def acquire(self) -> None:
        async with self.cond:
            self.waiting += 1
            try:
                while self.in_use >= self.capacity:
                    await self.cond.wait()
            finally:
                self.waiting -= 1
            self.in_use += 1

    async def release(self) -> None:
        async with self.cond:
            self.in_use -= 1
            self.cond.notify(1)

    async def resize(self, capacity: int) -> None:
        async with self.cond:
            self.capacity = capacity
            self.cond.notify(capacity)


class Service:
    def __init__(self, healthy: int, degraded: int,
                 down_at: float, up_at: float):
        self.t0 = time.monotonic()
        self.healthy = healthy
        self.degraded = degraded
        self.down_at = down_at
        self.up_at = up_at
        self.limiter = Limiter(healthy)
        self.buckets: dict[int, dict[str, float]] = {}
        self.abandoned = 0

    def now(self) -> float:
        return time.monotonic() - self.t0

    def bucket(self, t: float) -> dict[str, float]:
        key = int(t / BUCKET)
        b = self.buckets.get(key)
        if b is None:
            b = {"arrived": 0, "ok": 0, "gone": 0, "max_waiting": 0}
            self.buckets[key] = b
        return b

    async def schedule(self) -> None:
        await asyncio.sleep(max(0.0, self.down_at - self.now()))
        await self.limiter.resize(self.degraded)
        await asyncio.sleep(max(0.0, self.up_at - self.now()))
        await self.limiter.resize(self.healthy)

    async def handle(self, request: web.Request) -> web.Response:
        b = self.bucket(self.now())
        b["arrived"] += 1
        b["max_waiting"] = max(b["max_waiting"], self.limiter.waiting)
        try:
            await self.limiter.acquire()
        except asyncio.CancelledError:
            self.abandoned += 1
            b["gone"] += 1
            raise
        try:
            await asyncio.sleep(WORK_SECONDS)
        finally:
            await self.limiter.release()
        self.bucket(self.now())["ok"] += 1
        return web.Response(status=200, text="ok")

    async def stats(self, request: web.Request) -> web.Response:
        rows = [dict(t=round(k * BUCKET, 1),
                     **{n: int(v) for n, v in b.items()})
                for k, b in sorted(self.buckets.items())]
        return web.json_response({
            "bucket": BUCKET, "healthy_slots": self.healthy,
            "degraded_slots": self.degraded,
            "work_seconds": WORK_SECONDS, "abandoned": self.abandoned,
            "rows": rows})


async def start(args) -> None:
    svc = Service(args.slots, args.degraded_slots, args.down_at, args.up_at)
    app = web.Application()
    app.router.add_get("/quote", svc.handle)
    app.router.add_get("/admin/stats", svc.stats)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", args.port).start()
    asyncio.create_task(svc.schedule())
    print(json.dumps({"ready": True, "port": args.port}), flush=True)
    await asyncio.Event().wait()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--slots", type=int, default=40)
    ap.add_argument("--degraded-slots", type=int, default=8)
    ap.add_argument("--down-at", type=float, default=6.0)
    ap.add_argument("--up-at", type=float, default=16.0)
    asyncio.run(start(ap.parse_args()))


if __name__ == "__main__":
    main()
