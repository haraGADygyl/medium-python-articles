"""Closed-loop fleet of callers with four retry policies."""
import argparse
import asyncio
import json
import random
import time

import aiohttp

WORKERS = 2000
THINK_MIN, THINK_MAX = 1.55, 1.75
ATTEMPT_TIMEOUT = 0.300
MAX_ATTEMPTS = 5
BACKOFF_BASE = 0.100
BACKOFF_CAP = 2.000


class Budget:
    """Finagle-style retry budget: retries are paid for by successes."""

    def __init__(self, ratio: float = 0.2, initial: float = 10.0,
                 ceiling: float = 100.0):
        self.tokens = initial
        self.ratio = ratio
        self.ceiling = ceiling

    def deposit(self) -> None:
        self.tokens = min(self.ceiling, self.tokens + self.ratio)

    def withdraw(self) -> bool:
        if self.tokens < 1.0:
            return False
        self.tokens -= 1.0
        return True


class Breaker:
    """Rolling-window breaker with a single-flight half-open probe."""

    def __init__(self, window: int = 40, threshold: float = 0.5,
                 open_for: float = 1.0, single_flight: bool = True,
                 steps: int = 4):
        self.window: list[int] = []
        self.size = window
        self.threshold = threshold
        self.open_for = open_for
        self.state = "closed"
        self.opened_at = 0.0
        self.consecutive_opens = 0
        self.probe_in_flight = False
        self.single_flight = single_flight
        self.steps = steps
        self.probes = 0
        self.trips = 0
        self.short_circuited = 0

    def _cool_off(self) -> float:
        back = self.open_for * (2 ** min(self.consecutive_opens, self.steps))
        return back * (0.5 + random.random())

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self.opened_at < self._cool_off():
                self.short_circuited += 1
                return False
            self.state = "half-open"
            self.probe_in_flight = False
        if self.single_flight and self.probe_in_flight:
            self.short_circuited += 1
            return False
        self.probe_in_flight = True
        self.probes += 1
        return True

    def record(self, ok: bool) -> None:
        if self.state == "half-open":
            self.probe_in_flight = False
            if ok:
                self.state = "closed"
                self.window.clear()
                self.consecutive_opens = 0
            else:
                self.opened_at = time.monotonic()
                self.state = "open"
                self.consecutive_opens += 1
            return
        self.window.append(1 if ok else 0)
        if len(self.window) > self.size:
            del self.window[:-self.size]
        if len(self.window) >= self.size:
            if (self.size - sum(self.window)) / self.size > self.threshold:
                self.state = "open"
                self.opened_at = time.monotonic()
                self.consecutive_opens += 1
                self.trips += 1
                self.window.clear()


class Fleet:
    def __init__(self, policy: str, url: str, duration: float,
                 single_flight: bool = True, steps: int = 4):
        self.policy = policy
        self.url = url
        self.duration = duration
        self.t0 = time.monotonic()
        self.jobs = 0
        self.attempts = 0
        self.retries = 0
        self.succeeded = 0
        self.failed = 0
        self.failed_after_recovery = 0
        self.refused_by_budget = 0
        self.recovery_failures: list[float] = []
        self.budget = Budget()
        self.breaker = Breaker(single_flight=single_flight, steps=steps)
        self.latencies: list[float] = []
        self.timeline: dict[int, dict[str, int]] = {}

    def tick(self, field: str) -> None:
        sec = int(self.now())
        row = self.timeline.setdefault(
            sec, {"attempts": 0, "ok": 0, "fail": 0, "skipped": 0})
        row[field] += 1

    def now(self) -> float:
        return time.monotonic() - self.t0

    def delay(self, attempt: int) -> float:
        window = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
        if self.policy == "naive":
            return window
        return random.uniform(0, window)      # full jitter

    async def one_call(self, session: aiohttp.ClientSession) -> bool:
        self.attempts += 1
        self.tick("attempts")
        started = time.monotonic()
        try:
            async with session.get(self.url) as resp:
                await resp.read()
                ok = resp.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            ok = False
        if ok:
            self.latencies.append(time.monotonic() - started)
        return ok

    async def one_job(self, session: aiohttp.ClientSession) -> None:
        self.jobs += 1
        first = self.now()
        use_budget = self.policy in ("budget", "breaker")
        use_breaker = self.policy == "breaker"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                if use_budget and not self.budget.withdraw():
                    self.refused_by_budget += 1
                    self.tick("skipped")
                    break
                self.retries += 1
            if use_breaker and not self.breaker.allow():
                self.tick("skipped")
                break
            ok = await self.one_call(session)
            if use_breaker:
                self.breaker.record(ok)
            if ok:
                if use_budget:
                    self.budget.deposit()
                self.succeeded += 1
                self.tick("ok")
                return
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(self.delay(attempt))
        self.failed += 1
        self.tick("fail")
        if first >= RECOVERY_AT:
            self.failed_after_recovery += 1
            self.recovery_failures.append(first)

    async def worker(self, session: aiohttp.ClientSession) -> None:
        await asyncio.sleep(random.uniform(0, THINK_MAX))
        while self.now() < self.duration:
            await self.one_job(session)
            await asyncio.sleep(random.uniform(THINK_MIN, THINK_MAX))

    async def run(self) -> dict:
        timeout = aiohttp.ClientTimeout(total=ATTEMPT_TIMEOUT)
        conn = aiohttp.TCPConnector(limit=0, force_close=False,
                                    limit_per_host=0)
        async with aiohttp.ClientSession(timeout=timeout,
                                          connector=conn) as session:
            await asyncio.gather(*(self.worker(session)
                                   for _ in range(WORKERS)))
        lat = sorted(self.latencies)
        return {
            "policy": self.policy,
            "jobs": self.jobs,
            "attempts": self.attempts,
            "retries": self.retries,
            "amplification": round(self.attempts / max(1, self.jobs), 2),
            "succeeded": self.succeeded,
            "failed": self.failed,
            "failed_after_recovery": self.failed_after_recovery,
            "refused_by_budget": self.refused_by_budget,
            "breaker_trips": self.breaker.trips,
            "breaker_probes": self.breaker.probes,
            "short_circuited": self.breaker.short_circuited,
            "last_failure_at": round(max(self.recovery_failures), 2)
                               if self.recovery_failures else None,
            "p50_ms": round(lat[len(lat) // 2] * 1000, 2) if lat else None,
            "p99_ms": round(lat[int(len(lat) * 0.99)] * 1000, 2) if lat else None,
            "timeline": [dict(sec=k, **v)
                         for k, v in sorted(self.timeline.items())],
        }


RECOVERY_AT = 16.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("policy", choices=["naive", "jitter", "budget", "breaker"])
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--recovery-at", type=float, default=16.0)
    ap.add_argument("--probe", choices=["single", "all"], default="single")
    ap.add_argument("--cool-steps", type=int, default=4)
    args = ap.parse_args()
    global RECOVERY_AT
    RECOVERY_AT = args.recovery_at
    random.seed(20260910)
    fleet = Fleet(args.policy, f"http://127.0.0.1:{args.port}/quote",
                  args.duration, args.probe == "single", args.cool_steps)
    print(json.dumps(asyncio.run(fleet.run())), flush=True)


if __name__ == "__main__":
    main()
