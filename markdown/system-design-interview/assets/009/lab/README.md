# Lab — 009, which of your users are online right now?

PostgreSQL 17.6 (`postgres:17`) and Redis 8.4.0 (`redis:8`) in Docker, Python 3.12.3,
`psycopg[binary]==3.2.3`, `redis==5.2.1`. Ryzen 5 3600, 32 GB, NVMe.

```bash
docker run -d --name presence-pg -e POSTGRES_PASSWORD=lab -p 55439:5432 --shm-size=1g \
  postgres:17 -c shared_buffers=1GB -c max_wal_size=8GB -c max_connections=100
docker run -d --name presence-redis -p 56379:6379 redis:8
pip install "psycopg[binary]==3.2.3" "redis==5.2.1"
```

## Experiments

| Experiment | Command | Output |
| --- | --- | --- |
| Heartbeats as `UPDATE ... last_seen`, 10,000/s for 180 s, with and without an index on `last_seen`, 2 interleaved rounds | `./sustained_pg.sh` | `output-pg-sustained.txt` |
| Unthrottled ceiling, 30 s, 3 interleaved rounds, wait events sampled | `./ceiling_pg.sh` | `output-pg-ceiling.txt` |
| 60 s at 10,000/s, then the "online now" count and its plan while heartbeats run | `./run_pg.sh` | `output-pg.txt` |
| Heartbeats into a Redis sorted set: window width vs flaps and ghost time | `for m in 1.2 2 3 4; do python3 window.py $m 1; done` | `output-window.txt` |
| Write rate of the window design, 8,100 users, real time | `python3 hb_fleet.py 8100 60` | `output-hb-fleet.txt` |
| Gateway-owned presence: idle writes, churn, reads, logout, vanished phones, frozen gateway | `python3 gw_storm.py` | `output-gateway.txt` |
| The three tables the article quotes, from the files above | `python3 summary.py` | `output-summary.txt` |

`schema.sql` builds 1M accounts, ids 1–300,000 "connected". `heartbeat.sql` is the
pgbench script (one `UPDATE` per heartbeat, random connected user).

### Reading the Postgres numbers

HOT ratio, WAL bytes per heartbeat, index growth and the `Heap Fetches` of the
index-only scan repeat in every run. **Throughput does not**: unthrottled 30 s runs
reached ~18,000 updates/s in both configurations, but every sustained run fell to
~4,000/s after about two minutes, with or without the index, waiting on
`LWLock:WALWrite`. `pg_test_fsync` measured `fdatasync` at 1,756 µs/op on this
drive afterwards. The collapse belongs to this disk's fsync behaviour under
sustained load, not to Postgres, and the article says so. An earlier set of runs
made while other heavy work was running on the machine was discarded.

The table in the article combines the four sustained runs: HOT %, WAL bytes per
update, index sizes (28 MB at start with the index, measured by `run_pg.sh` on the
same schema) and autovacuum counts.

### The window experiment (`window.py`)

2,000 asyncio clients, time compressed 10x (a 30 s heartbeat is 3 lab seconds), 180
lab seconds = 30 real minutes per window. 3% of heartbeats are lost; 5% arrive
2–20 real seconds late; the rest 50–300 ms. 200 clients vanish without a goodbye
at random moments. A watcher polls the sorted set every real second. "Flaps" are
offline events for clients that are still alive; "ghost" is the time from
vanishing to the offline event. All times reported in real seconds.

### The gateway experiment (`gw_storm.py`)

Four `gateway.py` processes (asyncio TCP, ports 7101–7104), `janitor.py`, and
`clients.py` processes holding 8,100 connections: 8 x 1,000 idle users, 50 who log
out (SIGTERM, sockets closed cleanly) and 50 phones in a tunnel (10 processes x 5,
each SIGSTOPped at a different moment, sockets left open). Gateways ping every 5 s
and drop a connection after 2 unanswered pings; each renews a 3 s lease every 1 s.
A gateway is then frozen with SIGSTOP (power loss or partition: no FIN, no RST);
clients that hear nothing for 15 s reconnect elsewhere. A reader polls 200 of its
users every 50 ms. "Writes" counts `HSET`, `HDEL`, `SADD`, `SREM`, `SET` and
`EVALSHA` from `INFO commandstats` (commands inside the Lua script count too).

An earlier gateway run with the pingers in phase and a time-based miss check
detected vanished clients at 7.1 s, because the threshold sat exactly on a ping
boundary; `gateway.py` now counts missed pings and starts each pinger at a random
offset. Only the corrected run is kept.

Teardown: `docker rm -f presence-pg presence-redis`.
