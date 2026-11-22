"""What set-if-newer costs: latency per call against a plain SET / DEL,
and the memory a tombstone holds.

    python3 cost.py
"""
import time

import redis

from race import RHOST, RPORT, SET_IF_NEWER, pct

N = 20_000
TTL = 3600


def timed(label: str, call) -> None:
    """Run call(i) N times, one at a time, and print p50/p99 in microseconds."""
    samples = []

    for i in range(N):
        start = time.perf_counter_ns()
        call(i)
        samples.append((time.perf_counter_ns() - start) / 1000)

    print(f"  {label:<36} p50 {pct(samples, 50):6.1f} us   "
          f"p99 {pct(samples, 99):6.1f} us")


def main() -> None:
    r = redis.Redis(host=RHOST, port=RPORT)
    r.flushall()
    script = r.register_script(SET_IF_NEWER)
    script(keys=["warm"], args=[1, 1, TTL])

    print(f"one client, {N:,} calls each, keys fare:0..{N - 1}")

    for _ in range(2):   # second round is the one that counts
        timed("SET fare EX 3600 (plain fill)",
              lambda i: r.set(f"fare:{i}", f"{i}|8900", ex=TTL))
        timed("DEL fare (plain invalidate)",
              lambda i: r.delete(f"fare:{i}"))
        timed("set-if-newer, key absent (fill)",
              lambda i: script(keys=[f"fare:{i}"], args=[5, 8900, TTL]))
        timed("set-if-newer, newer version (fill)",
              lambda i: script(keys=[f"fare:{i}"], args=[6, 9100, TTL]))
        timed("set-if-newer, older version (refused)",
              lambda i: script(keys=[f"fare:{i}"], args=[4, 8700, TTL]))
        timed("tombstone (invalidate)",
              lambda i: script(keys=[f"fare:{i}"], args=[7, "-", TTL]))
        r.flushall()
        script = r.register_script(SET_IF_NEWER)
        print()

    r.flushall()
    before = r.info("memory")["used_memory"]
    pipe = r.pipeline(transaction=False)

    for i in range(100_000):
        pipe.set(f"fare:{i}", "1234567|-", ex=TTL)

    pipe.execute()
    after = r.info("memory")["used_memory"]
    print(f"100,000 tombstones: {(after - before) / 1e6:.1f} MB "
          f"({(after - before) / 100_000:.0f} bytes each), "
          f"MEMORY USAGE of one: {r.memory_usage('fare:1')} bytes")
    r.flushall()


if __name__ == "__main__":
    main()
