# Lab for 015 — extended statistics in PostgreSQL 18

PostgreSQL 18.6 in Docker on a Ryzen 5 3600, `shared_buffers=1GB`, `jit=off`, `work_mem=16MB`, port 55419.
Plans and timings use `max_parallel_workers_per_gather=0`.

    docker run -d --name pg18-extstats -e POSTGRES_PASSWORD=lab -p 55419:5432 postgres:18 \
      -c shared_buffers=1GB -c jit=off -c work_mem=16MB
    docker cp setup.sql pg18-extstats:/setup.sql
    docker exec pg18-extstats psql -U postgres -f /setup.sql      # ~90 s

| File | What it does |
| --- | --- |
| `setup.sql` | 10M deterministic sessions (922 MB heap) with planted correlations: city → state (except Portland, OR/ME), model → make, Leaf → CHAdeMO 97%, Tesla → NACS 92%; 8,184 stations; 816-row `tariff_rate` with no index |
| `revenue.sql` | The dashboard query from the article |
| `bench.sh` | Plan shape and `pgbench` latency (20 runs) with no extended statistics, dependencies only, and all three kinds |
| `plans.sh` → `plans.txt` | Full `EXPLAIN (ANALYZE, BUFFERS)` before and after |
| `estimates.sql` | Every other estimate in the article: impossible combinations, GROUP BY, the five-column object at target 100 and 2000, ANALYZE time per kind, cross-table, expression statistics, `IN` |

Measured: 1 estimated vs 12,938 actual; 848 ms → 42 ms (dependencies) → 41 ms (plus MCV, estimate 12,848).
A second full rebuild from `setup.sql` gave 749 ms → 39 ms → 39 ms.
Five-column object: estimate stays 1 at target 100 (ANALYZE 2.3 s); 14,050 at target 2000 (ANALYZE 87 s).
