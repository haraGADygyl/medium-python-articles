# Lab — 011, the user saved their order and the page says it doesn't exist

PostgreSQL 17.6 (`postgres:17`) in Docker: one primary and one streaming replica on the
same machine. Python 3.12.3, `psycopg[binary]==3.2.3`. Ryzen 5 3600, 32 GB, NVMe.

```bash
docker network create rywlab
docker run -d --name rywlab-primary --network rywlab -e POSTGRES_PASSWORD=lab -p 55441:5432 \
  --shm-size=1g postgres:17 -c shared_buffers=1GB -c max_wal_size=4GB -c wal_level=replica \
  -c max_connections=200
docker exec rywlab-primary bash -c \
  'echo "host replication all all scram-sha-256" >> /var/lib/postgresql/data/pg_hba.conf'
docker exec rywlab-primary psql -U postgres -c 'select pg_reload_conf()'

docker volume create rywlab-replica
docker run --rm --network rywlab -e PGPASSWORD=lab -v rywlab-replica:/var/lib/postgresql/data \
  postgres:17 bash -c 'rm -rf /var/lib/postgresql/data/* && pg_basebackup -h rywlab-primary \
  -U postgres -D /var/lib/postgresql/data -R -X stream -C -S replica1 \
  && chown -R postgres:postgres /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data'
docker run -d --name rywlab-replica --network rywlab -e POSTGRES_PASSWORD=lab -p 55442:5432 \
  --shm-size=1g -v rywlab-replica:/var/lib/postgresql/data postgres:17 \
  -c shared_buffers=1GB -c max_connections=200

docker exec -i rywlab-primary psql -U postgres < schema.sql
pip install "psycopg[binary]==3.2.3"
```

The replica runs with the defaults that matter here: `hot_standby = on`,
`max_standby_streaming_delay = 30s`, `hot_standby_feedback = off`. `window.py` changes
`hot_standby_feedback` (replica) and `synchronous_standby_names` (primary) itself with
`ALTER SYSTEM` before each run, and resets them for the modes that don't use them.

## Experiments

| Experiment | Command | Output |
| --- | --- | --- |
| Place an order on the primary, read it straight back from the replica, 16 customers, 20 s, quiet and during a bulk import | `python3 stale.py idle 20`, `python3 stale.py busy 20` | `output-stale-first.txt`, `output-stale-quiet.txt` |
| The 60 s scene, primary for 2 s after your own write | `python3 window.py sticky` | `output-sticky.txt`, `-run2`, `-run3` |
| Same, 5 s window | `python3 window.py sticky 5` | `output-sticky-5s.txt` |
| Same, LSN token taken after COMMIT | `python3 window.py token` | `output-token.txt`, `-run2`, `-run3` |
| Same, token taken inside the INSERT (`pg_current_wal_insert_lsn()`) | `python3 window.py token-early` | `output-token-early.txt` |
| Same, `synchronous_commit = remote_apply`, all reads on the replica | `python3 window.py remote_apply` | `output-remote_apply.txt` |
| Same, 2 s window with `hot_standby_feedback = on` | `python3 window.py sticky-feedback` | `output-sticky-feedback.txt` |
| Which LSN goes in the token: immediate read-back, trust the replica's check | `python3 tokencheck.py early busy 20`, `... after busy 20` | `output-tokencheck-first.txt`, `output-tokencheck-quiet.txt` |

### The scene (`window.py`)

24 customers each place an order and read it every 250 ms for 8 s, then place the next;
24 more read random old orders from the replica the whole time. At t=10 s a report on the
replica opens a `REPEATABLE READ` transaction, sums orders by month and then holds the
snapshot with `pg_sleep(90)` (the "slow report" is faked). At t=12 s the primary deletes
100,000 abandoned carts and runs `VACUUM`. The cleanup record conflicts with the report's
snapshot, so replay waits `max_standby_streaming_delay` (30 s) and then cancels the report.

"Replica behind" comes from a heartbeat row the sampler updates on the primary every 100 ms
and reads back on the replica (same machine, same clock). "Shown then gone" counts orders
that a customer saw at least once and then got "not found" for on a later read.

Across nine scene runs (all modes except `sticky-feedback`) the replica fell 30.25–31.06 s
behind; `sticky` lost 87 / 85 / 80 orders after showing them; `token` had 0 stale reads in
all three runs.

### Reading the trap-1 numbers

The drive's write speed is not steady. The first idle run on a fresh drive placed ~40,000
orders in 20 s with the order appearing p50 1.46 ms after commit; idle runs straight after a
bulk import (which writes 1–2 GB of WAL) placed 15,000–17,000 with p50 ~5.5 ms. Every run
is kept. Bulk-import worst case: 218 ms in the very first run, 1,780–2,042 ms in the three
quiet runs.

`tokencheck.py` with the early token found 6 bad reads in 36,748 in the first run (fresh
drive, high throughput) and none in three later runs, which got only 331–507 reads through
each on the slowed drive.

One set of repeats (three `stale.py` pairs, two `tokencheck.py` pairs) partly overlapped
diagram rendering on the same machine and was discarded. For the record: idle 96.4–99.8%
stale, busy worst 0.90–2.53 s; early token 2 bad in 1,800 and 0 in 528, after-commit token
0 in 358 and 0 in 556.

Teardown: `docker rm -f rywlab-primary rywlab-replica && docker volume rm rywlab-replica &&
docker network rm rywlab`.
