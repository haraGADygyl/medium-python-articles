"""Trap 1: exact per-minute sorted sets and a 60-way ZUNIONSTORE."""
import statistics
import sys
import threading
import time

from common import MINUTES, connect, load, tag

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
r = connect()
r.flushall()
data = load(seed)

# per-event ingest rate for one minute of traffic (300,000 ZINCRBY)
ids, counts = data["minutes"][0]
events = [tag(i) for i, c in zip(ids.tolist(), counts.tolist()) for _ in range(c)]
t0 = time.perf_counter()

for start in range(0, len(events), 10_000):
    pipe = r.pipeline(transaction=False)

    for member in events[start:start + 10_000]:
        pipe.zincrby("probe:minute", 1, member)

    pipe.execute()

secs = time.perf_counter() - t0
print(f"ingest: {len(events)} ZINCRBY in {secs:.2f} s = {len(events) / secs:,.0f}/s, one client, pipelined")
r.delete("probe:minute")

before = r.info("memory")["used_memory"]

for m, (ids, counts) in enumerate(data["minutes"]):
    key = f"trend:min:{m}"
    pairs = dict(zip(map(tag, ids.tolist()), counts.tolist()))
    items = list(pairs.items())

    for start in range(0, len(items), 5_000):
        r.zadd(key, dict(items[start:start + 5_000]))

after = r.info("memory")["used_memory"]
sizes = [r.zcard(f"trend:min:{m}") for m in range(MINUTES)]
one = r.memory_usage("trend:min:0", samples=0)
print(f"60 minute buckets: {sum(sizes):,} members, {statistics.mean(sizes):,.0f} per minute, "
      f"bucket 0 = {one / 1e6:.1f} MB, used_memory +{(after - before) / 1e6:.0f} MB")

# read path: union the hour while another client pings every millisecond
keys = [f"trend:min:{m}" for m in range(MINUTES)]

for run in range(3):
    stop = threading.Event()
    worst = []

    def prober() -> None:
        p = connect()

        while not stop.is_set():
            t = time.perf_counter()
            p.ping()
            worst.append(time.perf_counter() - t)
            time.sleep(0.001)

    th = threading.Thread(target=prober)
    th.start()
    time.sleep(0.2)
    t0 = time.perf_counter()
    n = r.zunionstore("trend:hour", keys)
    union = time.perf_counter() - t0
    time.sleep(0.2)
    stop.set()
    th.join()
    slow = sum(1 for w in worst if w > 0.1)
    print(f"run {run + 1}: ZUNIONSTORE 60 keys -> {n:,} members in {union * 1000:.0f} ms; "
          f"PING worst {max(worst) * 1000:.0f} ms, {slow} pings over 100 ms")

hour_mem = r.memory_usage("trend:hour", samples=0)
print(f"hour set: {hour_mem / 1e6:.0f} MB; total used_memory {r.info('memory')['used_memory'] / 1e6:.0f} MB")
top = r.zrevrange("trend:hour", 0, 9, withscores=True)
once = sum(1 for c in data["hour"] if c == 1) if False else int((data["hour"] == 1).sum())
print(f"tags used once this hour: {once:,} of {n:,} ({once / n:.0%})")

for rank, (member, score) in enumerate(top, 1):
    print(f"  {rank:2d} {member} {int(score):>9,}")
