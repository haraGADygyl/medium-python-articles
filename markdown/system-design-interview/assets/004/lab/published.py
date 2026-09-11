import asyncio


HEALTHY_SLOTS = 40
DEGRADED_SLOTS = 8
WORK_SECONDS = 0.025


class SlotPool:
    """Concurrency limit for the rate service. Nothing sheds load."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.in_use = 0
        self.waiting = 0
        self.gate = asyncio.Condition()

    async def acquire(self) -> None:
        async with self.gate:
            self.waiting += 1
            try:
                while self.in_use >= self.capacity:
                    await self.gate.wait()
            finally:
                self.waiting -= 1
            self.in_use += 1

    async def release(self) -> None:
        async with self.gate:
            self.in_use -= 1
            self.gate.notify(1)

    async def resize(self, capacity: int) -> None:
        """The incident: 40 slots become 8 for 800 ms, then 40 again."""
        async with self.gate:
            self.capacity = capacity
            self.gate.notify(capacity)


async def quote(pool: SlotPool) -> str:
    """One rate lookup: queue for a slot, then do the work."""
    await pool.acquire()
    try:
        await asyncio.sleep(WORK_SECONDS)
        return "ok"
    finally:
        await pool.release()
# ---- block 2
import aiohttp

QUOTE_URL = "http://127.0.0.1:8091/quote"
ATTEMPT_TIMEOUT = 0.300
MAX_ATTEMPTS = 5
BACKOFF_BASE = 0.100
BACKOFF_CAP = 2.000


def backoff(attempt: int) -> float:
    """Textbook exponential backoff: 100, 200, 400, 800 ms."""
    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))


async def call_once(session: aiohttp.ClientSession) -> bool:
    """One attempt. A timeout and a 503 are the same thing to the caller."""
    try:
        async with session.get(QUOTE_URL) as resp:
            await resp.read()
            return resp.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return False


async def fetch_rate(session: aiohttp.ClientSession) -> bool:
    """The answer everyone gives: retry with exponential backoff."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if await call_once(session):
            return True
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(backoff(attempt))
    return False
# ---- block 3
import random


def backoff_jittered(attempt: int) -> float:
    """Full jitter: sleep somewhere inside the window, not on its edge."""
    window = min(BACKOFF_CAP, BACKOFF_BASE * (2 ** (attempt - 1)))
    return random.uniform(0, window)
# ---- block 4
class RetryBudget:
    """Retries are paid for by successes, so a total outage stops them."""

    def __init__(self, ratio: float = 0.2, opening: float = 10.0,
                 ceiling: float = 100.0):
        self.tokens = opening
        self.ratio = ratio
        self.ceiling = ceiling

    def deposit(self) -> None:
        """A success buys a fifth of a future retry."""
        self.tokens = min(self.ceiling, self.tokens + self.ratio)

    def withdraw(self) -> bool:
        """A retry costs a whole token, or it does not happen."""
        if self.tokens < 1.0:
            return False
        self.tokens -= 1.0
        return True


async def fetch_rate_budgeted(session: aiohttp.ClientSession,
                              budget: RetryBudget) -> bool:
    """The first attempt is free. Every retry has to be affordable."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1 and not budget.withdraw():
            return False
        if await call_once(session):
            budget.deposit()
            return True
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(backoff_jittered(attempt))
    return False
# ---- block 5
import time


class Breaker:
    """One breaker per dependency, shared by every caller in the process."""

    def __init__(self, size: int = 40, threshold: float = 0.5,
                 cool_off: float = 1.0, doublings: int = 4):
        self.outcomes: list[int] = []
        self.size = size
        self.threshold = threshold
        self.cool_off = cool_off
        self.doublings = doublings
        self.state = "closed"
        self.opened_at = 0.0
        self.strikes = 0
        self.probing = False

    def wait_time(self) -> float:
        """Cool-off doubles on every consecutive trip, up to a ceiling."""
        base = self.cool_off * (2 ** min(self.strikes, self.doublings))
        return base * (0.5 + random.random())

    def allow(self) -> bool:
        """False means: fail this call now, without touching the network."""
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.monotonic() - self.opened_at < self.wait_time():
                return False
            self.state = "half-open"
            self.probing = False
        if self.probing:
            return False
        self.probing = True
        return True

    def record(self, ok: bool) -> None:
        """In half-open, one probe decides — not the rolling window."""
        if self.state == "half-open":
            self.probing = False
            if ok:
                self.state, self.strikes = "closed", 0
                self.outcomes.clear()
            else:
                self.state, self.opened_at = "open", time.monotonic()
                self.strikes += 1
            return
        self.outcomes.append(1 if ok else 0)
        del self.outcomes[:-self.size]
        if len(self.outcomes) == self.size:
            if (self.size - sum(self.outcomes)) / self.size > self.threshold:
                self.state, self.opened_at = "open", time.monotonic()
                self.strikes += 1
                self.outcomes.clear()
# ---- block 6
async def fetch_rate_protected(session: aiohttp.ClientSession,
                               budget: RetryBudget,
                               breaker: Breaker) -> bool:
    """The budget caps the volume; the breaker stops the traffic outright."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1 and not budget.withdraw():
            return False
        if not breaker.allow():
            return False
        ok = await call_once(session)
        breaker.record(ok)
        if ok:
            budget.deposit()
            return True
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(backoff_jittered(attempt))
    return False


# ---- driver: prove the published code runs end to end
async def main() -> None:
    pool = SlotPool(HEALTHY_SLOTS)
    print("quote via SlotPool:", await quote(pool))

    async def incident() -> None:
        await asyncio.sleep(2.0)
        await pool.resize(DEGRADED_SLOTS)
        await asyncio.sleep(0.8)
        await pool.resize(HEALTHY_SLOTS)

    asyncio.create_task(incident())
    budget, breaker = RetryBudget(), Breaker()
    timeout = aiohttp.ClientTimeout(total=ATTEMPT_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        print("backoff:", [round(backoff(n), 3) for n in range(1, 5)])
        print("jittered <= window:",
              all(backoff_jittered(n) <= backoff(n) for n in range(1, 5)))
        print("naive fetch_rate:", await fetch_rate(session))
        print("budgeted:", await fetch_rate_budgeted(session, budget))
        print("protected:", await fetch_rate_protected(session, budget,
                                                       breaker))
        print("breaker state:", breaker.state, "tokens:",
              round(budget.tokens, 1))


if __name__ == "__main__":
    asyncio.run(main())
