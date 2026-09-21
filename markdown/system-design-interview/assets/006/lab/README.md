# Lab — 006, rank among 50 million players

PostgreSQL 17.6 (`postgres:17`) and Redis 8 (`redis:8`) in Docker, Python 3.12,
`psycopg[binary]==3.2.3`, `redis==5.2.1`, Ryzen 5 3600.

Postgres: 50,000,000 rows, 5448 MB with both indexes. Redis: the same 50M members
in one sorted set, 4.50 GiB, 97 bytes per member, saving disabled so the timings
are clean.

```bash
docker run -d --name lb-pg -e POSTGRES_PASSWORD=demo -p 5462:5432 postgres:17
docker run -d --name lb-redis -p 6389:6379 redis:8 \
  redis-server --save '' --appendonly no
pip install "psycopg[binary]==3.2.3" redis==5.2.1

docker exec -i lb-pg psql -U postgres -v ON_ERROR_STOP=1 -q < seed.sql   # ~2 min
python3 zload.py 50000000                                                # ~5.5 min
```

| Experiment | Command | Output |
| --- | --- | --- |
| Rank latency, three methods + EXPLAIN | `SAMPLES=40 WINDOW_SAMPLES=5 python3 rank_latency.py` | `output-rank-latency.txt` |
| Tie groups, SQL rank forms vs ZREVRANK | `python3 ties.py` | `output-ties.txt` |
| Ordinal vs competition rank in Redis | `python3 competition_rank.py` | `output-competition.txt` |
| Pagination drift, offset vs cursor | `python3 pagination.py` | `output-pagination.txt` |
| Players near me, and snapshot cost | `python3 neighbours.py` | `output-neighbours.txt` |

`rank_latency.py` takes `SAMPLES` and `WINDOW_SAMPLES` from the environment; the
`rank()` window form takes about 19 seconds per call, so five is enough.

`pagination.py` churns 2000 writes/s while paging: half climb into the top band,
half drop out of it. Climbers cause duplicates, leavers cause skips — with only
one direction of movement you measure only one of the two failures, which is how
the first version of this script understated the problem.

Teardown: `docker rm -f lb-pg lb-redis`.
