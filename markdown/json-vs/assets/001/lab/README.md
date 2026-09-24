# Lab — 001, JSON vs. JSONB

PostgreSQL 18.0 (`postgres:18.0` Docker image, default configuration), Python 3.12.3,
`psycopg[binary]==3.3.6`, Ryzen 5 3600. The payload is the series' shared dataset,
generated in memory by `../../payload/make_payload.py` and copied into a staging
table, so the load timings measure only the `::json` / `::jsonb` conversion.

```bash
pip install "psycopg[binary]==3.3.6"
./run.sh        # starts a throwaway container on 127.0.0.1:55001, runs both, removes it
```

| Experiment | Command | Output |
| --- | --- | --- |
| Load time, storage, five queries, GIN and expression indexes | `python3 measure.py` | `output-jsonb.txt` |
| Whitespace, key order, duplicates, numbers, `\u0000`, equality | `psql -X -f semantics.sql` | `output-semantics.txt` |

`measure.py` connects to `LAB_DSN` (default
`postgresql://postgres:lab@127.0.0.1:55001/postgres`) and drops its own tables at
the end.

**Conditions.** `max_parallel_workers_per_gather = 0` for the session, so every
timing is one backend's work. Each query runs once as a warm-up and then five times;
the fastest is reported, measured at the client. The documents average 419 bytes as
`json`, under the ~2 KB TOAST threshold, so neither table is compressed — documents
large enough to be TOASTed may compare differently, and this lab does not test that.

Timings move by roughly ±10% between runs; sizes and row counts do not.
