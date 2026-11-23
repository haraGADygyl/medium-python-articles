-- Dropping June 2025 (1,110,597 rows): DELETE on the plain table vs DETACH + DROP on the monthly one.
\c monthly
CHECKPOINT;
SELECT pg_current_wal_lsn() AS lsn0 \gset
\timing on
DELETE FROM parcel_scan WHERE scanned_at < '2025-07-01 00:00+00';
\timing off
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), :'lsn0')) AS delete_wal,
       pg_size_pretty(pg_table_size('parcel_scan')) AS heap_after_delete;
CHECKPOINT;
SELECT pg_current_wal_lsn() AS lsn1 \gset
\timing on
ALTER TABLE parcel_scan_monthly DETACH PARTITION parcel_scan_monthly_2025_06 CONCURRENTLY;
DROP TABLE parcel_scan_monthly_2025_06;
\timing off
SELECT pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), :'lsn1')) AS detach_drop_wal;
