"""Merge pgbench per-thread aggregate logs into per-second rows and the max latency per phase."""
import sys
from collections import defaultdict

out = sys.argv[1]
marks = [(l.split()[0], float(l.split()[1])) for l in open(f"{out}/phases.txt")]
per_second = defaultdict(lambda: [0, 0.0])
for line in open(f"{out}/latency.log"):
    p = line.split()
    sec = per_second[int(p[0])]
    sec[0] += int(p[1])
    sec[1] = max(sec[1], float(p[5]) / 1000)
t0 = min(per_second)
print(f"{'second':>6} {'tx':>4} {'max ms':>9}")
for t in sorted(per_second):
    n, hi = per_second[t]
    tag = " ".join(m for m, ts in marks if int(ts) == t)
    print(f"{t - t0:>6} {n:>4} {hi:>9.1f} {tag}")
bounds = [(marks[i][0], marks[i][1], marks[i + 1][1]) for i in range(len(marks) - 1)]
print()
for name, start, end in bounds:
    window = [per_second[t][1] for t in per_second if int(start) <= t <= int(end)]
    print(f"{name:>14}: {end - start:7.2f} s wall, worst request {max(window):8.1f} ms")
