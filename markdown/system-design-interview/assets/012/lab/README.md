# Lab — 012, you delete the cache key on every write. Why is the cache still stale?

Redis 8.4.0 (`redis:8`) and PostgreSQL 17.6 (`postgres:17`) in Docker on one machine.
Python 3.12.3, `psycopg[binary]==3.2.3`, `redis==5.2.1`. Ryzen 5 3600, 32 GB, NVMe.

```bash
docker run -d --name stalelab-pg -e POSTGRES_PASSWORD=lab -p 55451:5432 postgres:17 \
  -c max_connections=200
docker run -d --name stalelab-redis -p 56451:6379 redis:8
pip install "psycopg[binary]==3.2.3" "redis==5.2.1"
```

`race.py` creates and resets its own `fares` table (1,000 sailings) and flushes Redis
before every run.

## Experiments

| Experiment | Command | Output |
| --- | --- | --- |
| Delete after COMMIT, 2% of fills stall | `python3 race.py plain` (x3) | `output-plain-1..3.txt` |
| Same, no injected stalls | `python3 race.py plain --stall-p 0` | `output-plain-nostall.txt` |
| Delete, then UPDATE | `python3 race.py delete-first` | `output-delete-first.txt` |
| Delayed double delete, 100 / 500 / 1000 / 2000 ms | `python3 race.py double --delay 0.5` | `output-double-*.txt` |
| Fills use set-if-newer, writer still deletes | `python3 race.py versioned` (x3) | `output-versioned-1..3.txt` |
| Fills use set-if-newer, writer leaves a versioned tombstone | `python3 race.py tombstone` (x3) | `output-tombstone-1..3.txt` |
| One reader, one writer, one sailing, with timestamps | `python3 scene.py plain`, `double 500 700`, `versioned`, `tombstone` | `output-scene-*.txt` |
| Latency of SET / DEL vs the Lua script, tombstone memory | `python3 cost.py` | `output-cost.txt` |

`runall.sh` runs the first batch in order (the double-delete runs in it were later redone,
see below).

### The workload (`race.py`)

32 reader threads read random sailings through cache-aside (GET; on a miss SELECT fare and
version, then SET with a 3,600 s TTL). 8 writer threads reprice random sailings at 400
UPDATEs a second in total for 60 s, after a 2 s warm-up. 2% of fills sleep between the
SELECT and the SET for a lognormal time (median 200 ms, sigma 1.0, capped at 4 s): the
stalls are injected, not observed.

A cached fare is **stale** when it holds a version older than one that committed more than
the grace period ago (1 s; for double delete, 1 s plus the delay, so a fare the second
delete would still clean up isn't counted). A checker compares every key with the writers'
record every 100 ms; each stale episode is one **reprice undone by a late fill**. After the
writers stop, readers keep going for stall cap + grace + 1 s so every stalled fill lands,
then every key is compared with Postgres: **still stale** keys keep the old fare until
their TTL runs out.

### Results

| Mode | Undone reprices (of ~24,000) | Still stale for the TTL | Misses to Postgres |
| --- | --- | --- | --- |
| plain | 44 / 59 / 49 | 3 / 3 / 2 | 383–389/s |
| plain, no injected stalls | 14 | 3 | 385/s |
| delete-first | 262 | 15 | 388/s |
| double 100 ms | 41 | 2 | 630/s |
| double 500 ms | 17 / 21 / 21 | 0 / 2 / 0 | 713–716/s |
| double 1000 ms | 6 | 2 | 712/s |
| double 2000 ms | 1 | 0 | 702/s |
| versioned, writer deletes | 16 / 18 / 19 | 0 / 0 / 2 | 388–389/s |
| versioned, tombstone | 0 / 0 / 0 | 0 / 0 / 0 | 387–388/s |

### Discarded

`discarded/` holds the first four double-delete runs. They used the plain 1 s grace,
which is shorter than a 1–2 s delay, so they counted fares the second delete was still
going to remove (2,000 ms showed 83 "undone"). They were rerun with the grace measured
from the second delete; those are the `output-double-*.txt` files.

Teardown: `docker rm -f stalelab-pg stalelab-redis`.
