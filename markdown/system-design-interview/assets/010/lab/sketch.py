"""The fix: one count-min sketch per minute, merged for the hour, plus a
short candidate list per minute built from the estimates CMS.INCRBY returns."""
import sys
import threading
import time

import numpy as np

from common import MINUTES, connect, load, tag

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ERROR, PROB, KEEP = 0.001, 0.01, 200
r = connect()
r.flushall()
data = load(seed)
before = r.info("memory")["used_memory"]

for m, (ids, counts) in enumerate(data["minutes"]):
    key, cand = f"trend:cms:{m}", f"trend:cand:{m}"
    r.execute_command("CMS.INITBYPROB", key, ERROR, PROB)
    pairs = list(zip(map(tag, ids.tolist()), counts.tolist()))

    for start in range(0, len(pairs), 2_000):
        chunk = pairs[start:start + 2_000]
        flat = [x for pair in chunk for x in pair]
        estimates = r.execute_command("CMS.INCRBY", key, *flat)
        r.zadd(cand, {name: est for (name, _), est in zip(chunk, estimates)})
        r.zremrangebyrank(cand, 0, -(KEEP + 1))

used = r.info("memory")["used_memory"] - before
info = dict(zip(*[iter(r.execute_command("CMS.INFO", "trend:cms:0"))] * 2))
sk = r.memory_usage("trend:cms:0", samples=0)
cd = r.memory_usage("trend:cand:0", samples=0)
print(f"per minute: CMS width {info['width']} depth {info['depth']} = {sk / 1e3:.0f} KB, "
      f"candidates {KEEP} = {cd / 1e3:.0f} KB (MEMORY USAGE); "
      f"60 minutes: used_memory +{used / 1e6:.1f} MB")


def top10() -> list[tuple[str, int]]:
    keys = [f"trend:cms:{m}" for m in range(MINUTES)]
    r.delete("trend:cms:hour")
    r.execute_command("CMS.INITBYPROB", "trend:cms:hour", ERROR, PROB)
    r.execute_command("CMS.MERGE", "trend:cms:hour", len(keys), *keys)
    r.zunionstore("trend:cand:hour", [f"trend:cand:{m}" for m in range(MINUTES)],
                  aggregate="MAX")
    names = r.zrange("trend:cand:hour", 0, -1)
    counts = r.execute_command("CMS.QUERY", "trend:cms:hour", *names)
    ranked = sorted(zip(names, counts), key=lambda x: -x[1])

    return ranked[:10], len(names)


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
    top, ncand = top10()
    secs = time.perf_counter() - t0
    stop.set()
    th.join()
    print(f"run {run + 1}: merge 60 sketches + score {ncand} candidates in {secs * 1000:.1f} ms; "
          f"PING worst {max(worst) * 1000:.1f} ms")

hour = data["hour"]
exact = np.argsort(-hour)[:11]
bound = ERROR * hour.sum()
print(f"\nN = {hour.sum():,}, error bound = {ERROR} x N = {bound:,.0f} (with probability {1 - PROB})")
print("rank  sketch says           exact top 10          over")

for rank, ((name, est), true_id) in enumerate(zip(top, exact), 1):
    i = int(name[3:])
    print(f"{rank:4d}  {name} {est:>9,}   {tag(true_id)} {hour[true_id]:>9,}   +{est - hour[i]:,}")

print(f"exact #11: {tag(exact[10])} {hour[exact[10]]:,}  (gap #10 -> #11 = {hour[exact[9]] - hour[exact[10]]:,})")
same_set = {int(n[3:]) for n, _ in top} == set(exact[:10].tolist())
same_order = [int(n[3:]) for n, _ in top] == exact[:10].tolist()
print(f"same 10 tags: {same_set}; same order: {same_order}")

# error by depth in the ranking, from the merged hour sketch
order = np.argsort(-hour)
print("\nexact rank band   true count (median)   overestimate (median / max)   relative (median)")

for lo, hi in [(1, 10), (91, 100), (991, 1000), (9991, 10000), (99991, 100000)]:
    ids = order[lo - 1:hi]
    est = np.array(r.execute_command("CMS.QUERY", "trend:cms:hour", *map(tag, ids.tolist())))
    over = est - hour[ids]
    print(f"{lo:>7,}-{hi:<7,}  {int(np.median(hour[ids])):>18,}   "
          f"{int(np.median(over)):>12,} / {int(over.max()):>8,}   {np.median(over / hour[ids]):>15.1%}")

never = [tag(i) for i in np.flatnonzero(hour == 0)[:2000].tolist()]
ghost = np.array(r.execute_command("CMS.QUERY", "trend:cms:hour", *never))
print(f"\n2,000 tags never used this hour: estimate median {int(np.median(ghost)):,}, max {int(ghost.max()):,}")
