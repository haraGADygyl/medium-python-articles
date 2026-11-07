"""Run the article's functions (design.py) against the state a lab script
left in Redis, and check they give the same answers.

  python3 exact.py 1  && python3 verify_design.py exact
  python3 sketch.py 1 && python3 verify_design.py sketch
  python3 panel.py 1 50000 && python3 verify_design.py panel 1
"""
import sys
import time

import numpy as np

import design
from common import connect, load

design.r = connect()
r = design.r
mode = sys.argv[1]

if mode == "exact":
    t0 = time.perf_counter()
    top = design.trending_now(59 * 60 + 1)
    print(f"trending_now: {(time.perf_counter() - t0) * 1000:.0f} ms, top 3 {top[:3]}")
    design.record("tagprobe", 600_000.0)
    design.record("tagprobe", 600_010.0)
    print(f"record: trend:min:10000 tagprobe = {r.zscore('trend:min:10000', 'tagprobe')}, "
          f"ttl {r.ttl('trend:min:10000')} s")

elif mode == "sketch":
    print("top_tags:", design.top_tags(59)[:3])
    design.record_batch(10_000, {"tagprobe": 3, "tagother": 1})
    design.record_batch(10_000, {"tagprobe": 2})
    print("record_batch: estimate after 3 + 2 =",
          r.execute_command("CMS.QUERY", "trend:cms:10000", "tagprobe"),
          "candidates", r.zrange("trend:cand:10000", 0, -1, withscores=True))

elif mode == "panel":
    data = load(int(sys.argv[2]))
    rows = design.trending_panel(11, 24)
    ids = np.array([int(n[3:]) for n, _ in rows], np.int64)
    print(f"trending_panel: {len(rows)} tags, {np.isin(ids, data['bursts']).sum()} new, "
          f"top 3 {[(n, round(x, 1)) for n, x in rows[:3]]}")
    print("is_trending(5000, 72):", design.is_trending(5000, 72),
          " is_trending(9138, 102240):", design.is_trending(9138, 102240))
