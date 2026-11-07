"""Generate one hour of hashtag events plus a 24-hour baseline.

10M tags, Zipf(1.0) popularity, 5,000 tag-events/s (300,000 per minute).
Each tag's rate this hour drifts from its baseline by lognormal(0, 0.15).
30 brand-new tags from the tail burst during the hour, 1,000-10,000 uses each,
ramping up from a random start minute. Writes stream-<seed>.npz.
"""
import sys

import numpy as np

V = 10_000_000
PER_MIN = 300_000
MINUTES = 60
N_BURSTS = 30

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
rng = np.random.default_rng(seed)

p = 1.0 / np.arange(1, V + 1)
p /= p.sum()
drifted = p * rng.lognormal(0.0, 0.15, V)
cdf = np.cumsum(drifted)
cdf /= cdf[-1]

bursts = rng.choice(np.arange(V // 2, V), N_BURSTS, replace=False)
burst_total = rng.integers(1_000, 10_001, N_BURSTS)
burst_start = rng.integers(0, 45, N_BURSTS)

minute_ids, minute_counts = [], []

for m in range(MINUTES):
    # burst events this minute: linear ramp from start to end of hour
    extra = []

    for tag, total, start in zip(bursts, burst_total, burst_start):
        if m < start:
            continue

        span = MINUTES - start
        weight = (m - start + 1) / (span * (span + 1) / 2)
        extra.append(np.full(rng.poisson(total * weight), tag))

    burst_events = np.concatenate(extra) if extra else np.empty(0, np.int64)
    base_events = np.searchsorted(cdf, rng.random(PER_MIN - len(burst_events)))
    ids, counts = np.unique(np.concatenate([base_events, burst_events]),
                            return_counts=True)
    minute_ids.append(ids.astype(np.int64))
    minute_counts.append(counts.astype(np.int64))

# baseline: the previous 24 hours at the undrifted rates, no bursts
base = rng.poisson(24 * PER_MIN * MINUTES * p)
base_ids = np.flatnonzero(base)

np.savez_compressed(
    f"stream-{seed}.npz",
    bursts=bursts,
    base_ids=base_ids, base_counts=base[base_ids],
    **{f"m{m}_ids": minute_ids[m] for m in range(MINUTES)},
    **{f"m{m}_counts": minute_counts[m] for m in range(MINUTES)},
)
hour = np.zeros(V, np.int64)

for ids, counts in zip(minute_ids, minute_counts):
    hour[ids] += counts

print(f"seed {seed}: events {hour.sum()}, distinct/hour {np.count_nonzero(hour)}, "
      f"distinct/min avg {np.mean([len(i) for i in minute_ids]):.0f}, "
      f"used once {np.sum(hour == 1)}, baseline distinct {len(base_ids)}, "
      f"burst hour counts {sorted(hour[bursts].tolist())}")
