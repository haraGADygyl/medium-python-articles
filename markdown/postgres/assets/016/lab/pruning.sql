-- What partition pruning decides, on the 19-partition monthly table. Parallel query off.
\c monthly
SET max_parallel_workers_per_gather = 0;
\echo === P1 constant range: plan-time pruning
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM parcel_scan_monthly
WHERE scanned_at >= '2026-10-01 00:00+00' AND scanned_at < '2026-10-08 00:00+00';
\echo === P2 now(): run-time pruning at executor start
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM parcel_scan_monthly
WHERE scanned_at >= now() - interval '7 days';
\echo === P3 cast on the key: no pruning
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM parcel_scan_monthly
WHERE scanned_at::date = date '2026-10-15';
\echo === P3b same day, written as a range
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM parcel_scan_monthly
WHERE scanned_at >= '2026-10-15 00:00+00' AND scanned_at < '2026-10-16 00:00+00';
\echo === P3c unpartitioned, cast
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM parcel_scan
WHERE scanned_at::date = date '2026-10-15';
\echo === P4 lookup without the key
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT * FROM parcel_scan_monthly WHERE scan_id = 12345678;
\echo === P4b same lookup, unpartitioned
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT * FROM parcel_scan WHERE scan_id = 12345678;
\echo === P5 generic plan for a prepared statement
PREPARE recent_scans(timestamptz) AS
  SELECT count(*) FROM parcel_scan_monthly WHERE scanned_at >= $1;
SET plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, COSTS OFF) EXECUTE recent_scans('2026-11-16 00:00+00');
