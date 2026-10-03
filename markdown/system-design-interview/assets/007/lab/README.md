# Lab — 007, where an account balance lives

PostgreSQL 17.6 (`postgres:17`) in Docker, Python 3.12, `psycopg[binary]==3.2.3`,
Ryzen 5 3600, NVMe. Server flags: `shared_buffers=1GB`, `max_connections=200`,
`max_wal_size=16GB`, `checkpoint_timeout=30min` (so no checkpoint lands inside a
benchmark run).

Accounts: `0` is the platform fee account, `1..1,000,000` wallets with 10,000.00
each, `1,000,001..1,010,000` merchants. `entry` carries `xid xid8 DEFAULT
pg_current_xact_id()` and two covering indexes, `(account_id, xid) INCLUDE
(amount)` and `(account_id, id) INCLUDE (amount)`.

```bash
pip install "psycopg[binary]==3.2.3"
./run_all.sh          # rebuilds the container and runs everything, ~17 min
```

| Experiment | Script | Output |
| --- | --- | --- |
| Payment throughput: no fee leg, hot fee column, fee as entry | `bench/run.sh` (pgbench, scripts in `bench/`) | `output-pgbench.txt` |
| `SUM(amount)` for 10^4..10^7 entries + plan | `sum_latency.py` (after `seed_history.sql`) | `output-sum-latency.txt` |
| Checkpoint race, `max(id)` boundary | `DURATION=30 python3 race.py naive` | `output-race-naive.txt` |
| Checkpoint race, `xid8` watermark | `DURATION=30 python3 race.py watermark` | `output-race-watermark.txt` |
| Idle transaction pins the watermark | `python3 stall.py` | `output-stall.txt` |
| 8 concurrent debits vs 100 cents, two designs | `python3 overdraft.py` (x3) | `output-overdraft.txt` |

`bench/run.sh` runs three rounds with every configuration interleaved inside a
round, `VACUUM account` + `CHECKPOINT` before each 30 s run, and prints the median
plus all three runs. On this desktop the drive slowed down partway through round
one (single-client commits went from ~0.6 ms to ~3 ms and stayed there), which is
the outlier in each row's `runs:` list. Medians are the steady state. An earlier
non-interleaved version ran each configuration back to back and drifted with the
drive; do not use it.

`race.py` and `stall.py` credit account `7` from 32 writer threads, each
transaction an `INSERT` into `entry` plus an `UPDATE` of a random wallet, with a
single checkpointer every 50 ms in `REPEATABLE READ`.

Teardown: `docker rm -f bal-pg`.
