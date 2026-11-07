# Lab — 010, what is trending right now, and how sure are you?

Redis 8.4.0 (`redis:8`, count-min sketch built in) in Docker, Python 3.12.3,
`redis==5.2.1`, `numpy==1.26.4`. Ryzen 5 3600, 32 GB, NVMe.

```bash
docker run -d --name trending-redis -p 56380:6379 redis:8
pip install "redis==5.2.1" "numpy==1.26.4"
for s in 1 2 3; do python3 stream.py $s; done      # stream-1.npz .. stream-3.npz (~36 MB each, not committed)
```

## The traffic (`stream.py`)

10M tags with Zipf(1.0) popularity, 5,000 tag uses a second (300,000 per minute,
18M in the hour). Each tag's rate this hour drifts from its usual rate by
lognormal(0, 0.15). 30 brand-new tags drawn from the tail (ranks 5M-10M) take off
during the hour, 1,000-10,000 uses each, ramping up from a random start minute.
The baseline is the previous 24 hours at the usual rates (432M uses, 9.8M distinct
tags), Poisson per tag, no bursts. Three seeds = three different hours.

Seed 1: 2,883,233 distinct tags this hour, 1,872,836 of them used once; new tags'
baseline is 3 uses in 24 hours (median).

## Experiments

| Experiment | Command | Output |
| --- | --- | --- |
| Exact per-minute sorted sets, 60-way `ZUNIONSTORE`, `PING` probe every 1 ms; then the article's `record` / `trending_now` | `python3 exact.py 1 && python3 verify_design.py exact` | `output-exact.txt` |
| Count-min sketch per minute (`CMS.INITBYPROB 0.001 0.01` = 2,000 x 7), 200 candidates per minute, error by rank; then `record_batch` / `top_tags` | `python3 sketch.py 1 && python3 verify_design.py sketch` | `output-sketch.txt` |
| Trending rule (>= 500 uses, lift >= 5 against the 24 h baseline) from sketches of width 2,000-100,000, every tag seen in the hour scored | `python3 trending.py <seed> 2000,10000,20000,50000,100000` | `output-trending-<seed>.txt` |
| Do new tags reach per-minute candidate lists? | `python3 candidates.py 1 2000,20000,100000 200,1000` | `output-candidates-1.txt` |
| Real memory of a CMS key (`used_memory` delta over 36 keys) | `python3 memcheck.py` | `output-memcheck.txt` |
| Final design: 12 five-minute sketches + 24 hourly baseline sketches at 50,000 x 7, 1,000 candidates per bucket; then `trending_panel` | `python3 panel.py <seed> 50000 && python3 verify_design.py panel <seed>` | `output-panel-<seed>.txt` |
| The sweep table in the article | `python3 summary.py` | `output-summary.txt` |

`design.py` holds every code block the article shows, unchanged; `verify_design.py`
runs those functions against the state each experiment leaves in Redis and checks
they give the same answers.

## Notes

- **Loading.** The sorted sets and sketches are filled from per-minute aggregated
  counts (`ZADD` with the count, `CMS.INCRBY` with the count). The final state is
  identical to one increment per use; per-use ingest was measured separately on
  one minute (300,000 pipelined `ZINCRBY`).
- **Merge equivalence.** `trending.py` builds one sketch of the hour directly and
  first checks, at width 2,000, that 60 merged minute sketches answer identically
  on ~9,600 tags (`True` for all three seeds).
- **Memory.** `MEMORY USAGE` reports 8 bytes per CMS counter; Redis allocates 4
  (`output-memcheck.txt`). The article uses `used_memory` deltas. The `KB/sketch`
  column of `output-trending-*.txt` is `MEMORY USAGE`; `summary.py` replaces it.
- **Best case.** `trending.py` scores every tag seen in the hour, which no
  candidate list can beat. `candidates.py` shows the per-minute lists do catch
  all 30 new tags at every width, so the failure is in the numbers, not in
  candidate discovery.
- **Not measured.** Coordinated campaigns pushing a tag, more than one Redis node,
  real tag distributions (the noise floor depends on how much traffic sits in the
  tail), and keeping the exact hour set up to date incrementally.

Teardown: `docker rm -f trending-redis`.
