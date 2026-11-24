# Lab for 017 — random UUID primary keys vs `uuidv7()`

PostgreSQL 18.6 in Docker on a Ryzen 5 3600 (NVMe), `shared_buffers=256MB`, `jit=off`,
`track_io_timing=on`; everything else default (`max_wal_size=1GB`, `checkpoint_timeout=5min`,
`full_page_writes=on`, `wal_compression=off`), port 55421.

    docker run -d --name pg18-uuid -e POSTGRES_PASSWORD=lab -p 55421:5432 --shm-size=1g postgres:18 \
      -c shared_buffers=256MB -c jit=off -c track_io_timing=on
    docker cp setup.sql pg18-uuid:/setup.sql
    docker exec pg18-uuid psql -U postgres -X -f /setup.sql
    python3 load.py 20 > load.txt                  # ~7 min, needs psycopg 3

The experiments run in this order on the same database, because each one builds on the tables the
previous one left.

| File | What it does |
| --- | --- |
| `setup.sql` | Three webhook delivery tables, identical except the key: `bigint` identity, `uuid DEFAULT gen_random_uuid()`, `uuid DEFAULT uuidv7()` |
| `load.py` → `load.txt` | 20 x 1M-row `INSERT ... SELECT` per table, each under `EXPLAIN (ANALYZE, BUFFERS, WAL)`, after a `CHECKPOINT`; final sizes and `pgstatindex` density |
| `bench.sh`, `insert_*.sql` → `bench.txt` | pgbench, 8 clients, single-row prepared inserts, 60 s after a `CHECKPOINT`; WAL/FPI from `pg_stat_wal` deltas. Ends with `ALTER ... SET DEFAULT uuidv7()` on `delivery_v4` and a 60 s rerun |
| `bench.sh` → `bench-300s.txt` | Same, 300 s (one `checkpoint_timeout`), v4 (default reset to `gen_random_uuid()`) vs v7 |
| `features.sql` → `features.txt` | `uuid_extract_timestamp`, in-session monotonicity over 1M ids, the shift argument, the timestamp leak, "latest 50" with and without a time-ordered key |
| `reindex.sql` → `reindex.txt` | `REINDEX INDEX CONCURRENTLY` on the v4-era key after the switch |

## Measured

- Bulk load, 20M rows: serial 47.8 s, v4 280.3 s, v7 90.5 s. WAL 2,977 / 13,687 / 3,248 MB. FPI 23 / 1,842,717 / 29.
  Checkpoints 8 / 28 / 9. Primary key 428 / 772 / 602 MB, leaf density 90.04 / 70.19 / 89.99%. Heap 1,149 / 1,302 /
  1,302 MB.
- v4 per-million time: 4.7 s (1st), 8.0 s (10th), 46.0 s (20th); shared reads per chunk go 2,775 (6th) → 62,427 (7th)
  → 662,507 (20th) as the key outgrows `shared_buffers`. v7 stays 3.6–6.0 s with ~0 reads.
- pgbench 300 s: v4 2,165 tps, v7 1,874 tps (commit-bound; v4's first 30 s ran at 4–9k tps, cause not identified,
  then both sat at ~1.6–1.9k). WAL per row 3,056 vs 218 bytes; FPI per row 0.48 vs 0.0016; WAL 1,893 vs 117 MB;
  checkpoints 3 vs 1; key blocks read from outside shared buffers 446,403 (82.9% hit) vs 3 (100.0%); 160 vs 261
  rows per new leaf.
- pgbench 60 s: serial 191, v4 3,968, v7 205 bytes WAL per row; FPI per row 0.63 for v4, ~0 for the others.
  The "pkey blocks read" lines in `bench.txt` are **not used**: that version of `bench.sh` ran `pgstatindex` inside the
  counter window, so its own full-index read is counted. `bench-300s.txt` uses the fixed script.
- After `SET DEFAULT uuidv7()` on the v4 table (60 s): 227 bytes WAL per row, 12 FPI, 145 rows per new leaf
  (50:50 splits mid-index; `_bt_afternewitemoff` skips single-column indexes, PG 18 `nbtsplitloc.c`).
- `REINDEX CONCURRENTLY` on the v4 key: 13.4 s, 815 MB → 627 MB, density 69.35 → 89.99%.
- 1M `uuidv7()` in one statement: strictly increasing, spanning 1,410 distinct milliseconds.
- "Latest 50": v4 by `attempted_at` (no index) 1,564 ms parallel seq scan, 172,332 blocks read; v7 by
  `delivery_id DESC` 0.034 ms backward index scan, 51 buffers.
