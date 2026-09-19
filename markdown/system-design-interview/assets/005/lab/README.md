# Lab — 005, DDL lock queueing

PostgreSQL 17.6 (Docker `postgres:17`), Python 3.12, `psycopg[binary]==3.2.3`,
Ryzen 5 3600. Table: 20,000,000 rows, 1302 MB heap / 2333 MB total.

```bash
docker run -d --name ddl-lab -e POSTGRES_PASSWORD=demo -p 5461:5432 postgres:17
pip install "psycopg[binary]==3.2.3"
docker exec -i ddl-lab psql -U postgres -v ON_ERROR_STOP=1 -q < seed.sql
```

| Experiment | Command | Output |
| --- | --- | --- |
| Bare ALTER behind a 12 s reader | `python3 exp_queue.py naive` | `output-queue-naive.json` |
| Same, with `lock_timeout` + retry | `python3 exp_queue.py retry` | `output-queue-retry.json` |
| Which statements rewrite the table | `python3 exp_rewrite.py` | `output-rewrite.json` |
| `SET NOT NULL`, direct vs staged | `python3 exp_notnull.py` | `output-notnull.json` |
| `pg_locks` during the stall | `python3 exp_snapshot.py` | `output-locks-snapshot.txt` |

`lab.py` holds the shared traffic generator, the long-reader helper, the
`pg_locks` poller and the retry wrapper. Each experiment drops and re-adds its
own column, so they can be run in any order. Teardown: `docker rm -f ddl-lab`.
