# Lab for 016 — partitioning a live table without taking it down

PostgreSQL 18.6 in Docker on a Ryzen 5 3600, `shared_buffers=1GB`, `jit=off`, `work_mem=16MB`,
`max_wal_size=8GB`, port 55420.

    docker run -d --name pg18-partition -e POSTGRES_PASSWORD=lab -p 55420:5432 --shm-size=1g postgres:18 \
      -c shared_buffers=1GB -c jit=off -c work_mem=16MB -c max_wal_size=8GB -c log_lock_waits=on
    docker cp setup.sql pg18-partition:/setup.sql
    docker exec pg18-partition psql -U postgres -X -f /setup.sql      # ~85 s, database "seed"

Every experiment starts from `CREATE DATABASE ... TEMPLATE seed`, so runs never contaminate each other.

| File | What it does |
| --- | --- |
| `setup.sql` | 20M `parcel_scan` rows, 2025-06-01 .. 2026-11-23, in time order: 1,563 MB heap, 1,240 MB indexes |
| `insert.sql`, `lookup.sql` | The live load: pgbench, 8 clients, 400 tx/s, 4 inserts : 1 parcel lookup |
| `prepare.sql` | Online steps: `CHECK ... NOT VALID`, `VALIDATE`, `CREATE UNIQUE INDEX CONCURRENTLY (scan_id, scanned_at)` |
| `parent.sql` | The empty partitioned table and three future monthly partitions |
| `swap.sql` | One transaction: rename, promote the new index to PK, rename, `ATTACH ... FROM (MINVALUE)`, move sequence ownership |
| `migrate.sh [nocheck]` → `run-check/`, `run-nocheck/` | The migration under load; per-second worst latency by phase (`phases.py`) |
| `report.sql`, `lockqueue.sh` → `run-lockqueue/` | A 20 s report holds ACCESS SHARE; swap with `lock_timeout = '2s'`, then without |
| `monthly.sql` → `naive-copy.txt` | The offline way: copy into 19 monthly partitions; also the pruning/retention testbed (database `monthly`) |
| `pruning.sql` → `pruning.txt` | Plan-time, run-time, generic-plan pruning; the `::date` cast that disables it; lookup without the key |
| `lookup_by_id.sh` → `lookup_by_id.txt` | pgbench point lookups by `scan_id`, plain vs partitioned, simple vs prepared |
| `retention.sql` → `retention.txt` | Dropping June 2025: `DELETE` vs `DETACH PARTITION CONCURRENTLY` + `DROP` |
| `identity.sql` | A `GENERATED ALWAYS AS IDENTITY` table cannot be attached; moving the identity to the parent in the swap |
| `create_vs_attach.sql` → `create_vs_attach.txt` | With a report open: `CREATE TABLE ... PARTITION OF` times out, create + `ATTACH` passes |
| `partitions.sql` → `partitions.txt` | `create_scan_partition()` via ATTACH, run under an open report; legacy drop keeps the sequence |
| `cascade.sql` → `cascade.txt` | Sequence still owned by legacy: `DROP ... CASCADE` strips the parent's default, the next insert fails `NOT NULL` |

## Measured

- Offline copy (writes frozen): copy 20.2 s + three indexes 23.2 s + `VACUUM ANALYZE` 5.7 s = 49.1 s.
- Online: `NOT VALID` 1.2 ms; `VALIDATE` 1,314 ms (worst request in those seconds 3.7 ms);
  `CREATE UNIQUE INDEX CONCURRENTLY` 7,061 ms (worst request 73.5 ms; 217 ms in the nocheck run).
- Swap: all statements ~14 ms including an 11.7 ms `COMMIT`; DEBUG1 says "partition constraint ... is implied by
  existing constraints"; worst request that second 5.0 ms; 30,049 transactions, 0 failed.
- Swap without the CHECK: `ATTACH` scans for 1,444 ms; worst request 1,448.5 ms.
- Lock queue: `lock_timeout = '2s'` cancels at 2,000 ms (worst request 2,003 ms); no timeout waits 8,941 ms with
  0 transactions completed for 8 consecutive seconds (worst request 8,947 ms).
- Pruning (19 partitions): constant range plans 1 partition; `now() - 7 days` and a generic prepared plan show
  `Subplans Removed: 17`; `scanned_at::date = ...` scans all 19 (2,709 ms) vs 38 ms as a range; the unpartitioned
  table with the same cast: 2,486 ms.
- Lookup by `scan_id` only: 0.125 ms plain vs 0.372 ms partitioned (simple protocol); prepared 0.117 vs 0.140 ms.
- Retention, 1,110,597 rows: `DELETE` 953 ms, 146 MB WAL, heap still 1,563 MB; `DETACH CONCURRENTLY` 5.5 ms +
  `DROP` 13.5 ms, 269 kB WAL.
- PostgreSQL 19.0 (`postgres:19`) rejects `ALTER TABLE ... SPLIT PARTITION` with a syntax error.
