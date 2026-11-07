"""The final design, end to end.

12 five-minute sketches for the current hour, 24 hourly sketches for the
baseline, a candidate list of the top 1,000 estimates per five-minute bucket.
Read path: merge the 12, merge the 24, score the candidates, apply the rule.
"""
import sys
import threading
import time

import numpy as np

from common import connect, load, tag

WIDTH, DEPTH, KEEP = int(sys.argv[2]), 7, 1_000
MIN_SUPPORT, MIN_LIFT, SMOOTH = 500, 5.0, 10
seed = int(sys.argv[1])
r = connect()
r.flushall()
data = load(seed)
hour, base, bursts = data["hour"], data["base"], data["bursts"]
rng = np.random.default_rng(seed)


def incr(key: str, ids: np.ndarray, counts: np.ndarray) -> list[int]:
    estimates = []

    for start in range(0, len(ids), 5_000):
        flat = []

        for i, c in zip(ids[start:start + 5_000].tolist(), counts[start:start + 5_000].tolist()):
            flat += [tag(i), c]

        estimates += r.execute_command("CMS.INCRBY", key, *flat)

    return estimates


# the baseline: 24 hourly sketches, the 24-hour counts split across them
remaining = base.copy()

for h in range(24):
    part = remaining if h == 23 else rng.binomial(remaining, 1 / (24 - h))
    remaining = remaining - part
    ids = np.flatnonzero(part)
    r.execute_command("CMS.INITBYDIM", f"trend:base:{h}", WIDTH, DEPTH)
    incr(f"trend:base:{h}", ids, part[ids])

# the current hour: twelve five-minute buckets, each with its candidate list
for b in range(12):
    key, cand = f"trend:cms:{b}", f"trend:cand:{b}"
    r.execute_command("CMS.INITBYDIM", key, WIDTH, DEPTH)
    counts = np.zeros(10_000_000, np.int64)

    for ids, c in data["minutes"][b * 5:(b + 1) * 5]:
        counts[ids] += c

    ids = np.flatnonzero(counts)
    est = incr(key, ids, counts[ids])
    top = np.argsort(est)[-KEEP:]
    r.zadd(cand, {tag(int(ids[i])): est[i] for i in top})


def panel() -> tuple[list[tuple[str, int, float]], int]:
    hour_keys = [f"trend:cms:{b}" for b in range(12)]
    base_keys = [f"trend:base:{h}" for h in range(24)]
    r.delete("trend:hour", "trend:day")
    r.execute_command("CMS.INITBYDIM", "trend:hour", WIDTH, DEPTH)
    r.execute_command("CMS.INITBYDIM", "trend:day", WIDTH, DEPTH)
    r.execute_command("CMS.MERGE", "trend:hour", 12, *hour_keys)
    r.execute_command("CMS.MERGE", "trend:day", 24, *base_keys)
    names = list({n for b in range(12) for n in r.zrange(f"trend:cand:{b}", 0, -1)})
    now = r.execute_command("CMS.QUERY", "trend:hour", *names)
    day = r.execute_command("CMS.QUERY", "trend:day", *names)
    rows = []

    for name, n, d in zip(names, now, day):
        lift = (n + SMOOTH) / (d / 24 + SMOOTH)

        if n >= MIN_SUPPORT and lift >= MIN_LIFT:
            rows.append((name, n, lift))

    return sorted(rows, key=lambda x: -x[2]), len(names)


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
    time.sleep(0.1)
    t0 = time.perf_counter()
    rows, ncand = panel()
    secs = time.perf_counter() - t0
    stop.set()
    th.join()
    print(f"run {run + 1}: merge 12 + 24 sketches, score {ncand:,} candidates: "
          f"{secs * 1000:.0f} ms, PING worst {max(worst) * 1000:.1f} ms")

one = r.memory_usage("trend:cms:0", samples=0)
cand = sum(r.memory_usage(f"trend:cand:{b}", samples=0) for b in range(12))
print(f"memory: 36 sketches, MEMORY USAGE says {one / 1e6:.2f} MB each, "
      f"candidate lists {cand / 1e6:.2f} MB, used_memory {r.info('memory')['used_memory'] / 1e6:.0f} MB")
ids = np.array([int(n[3:]) for n, _, _ in rows], np.int64)
new = np.isin(ids, bursts)
exact_pass = np.flatnonzero((hour >= MIN_SUPPORT) &
                            ((hour + SMOOTH) / (base / 24 + SMOOTH) >= MIN_LIFT))
print(f"panel: {len(rows)} tags pass, {new.sum()} of them new, {len(rows) - new.sum()} not; "
      f"exact rule passes {len(exact_pass)} ({np.isin(exact_pass, bursts).sum()} new)")
missed = sorted(hour[np.setdiff1d(exact_pass, ids)].tolist())
print(f"missed by the panel: {len(missed)} {missed}")

for name, n, lift in rows[:5]:
    i = int(name[3:])
    true = (hour[i] + SMOOTH) / (base[i] / 24 + SMOOTH)
    print(f"  {name}: sketch {n:,} uses, lift {lift:.1f}  |  true {hour[i]:,} uses, "
          f"baseline {base[i]}, lift {true:.0f}")
