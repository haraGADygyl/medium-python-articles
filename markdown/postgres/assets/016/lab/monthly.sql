-- The offline way: copy everything into a monthly-partitioned table. With writes frozen,
-- this whole file is the outage. The result is also the testbed for pruning and retention.
DROP DATABASE IF EXISTS monthly;
CREATE DATABASE monthly TEMPLATE seed;
\c monthly
\timing on
CREATE TABLE parcel_scan_monthly (LIKE parcel_scan INCLUDING DEFAULTS)
  PARTITION BY RANGE (scanned_at);
DO $$
DECLARE month_start date;
BEGIN
  FOR month_start IN SELECT generate_series(date '2025-06-01', date '2026-12-01', interval '1 month') LOOP
    EXECUTE format(
      'CREATE TABLE parcel_scan_monthly_%s PARTITION OF parcel_scan_monthly FOR VALUES FROM (%L) TO (%L)',
      to_char(month_start, 'YYYY_MM'), month_start, month_start + interval '1 month');
  END LOOP;
END $$;
\echo PHASE copy
INSERT INTO parcel_scan_monthly SELECT * FROM parcel_scan;
\echo PHASE indexes
ALTER TABLE parcel_scan_monthly ADD PRIMARY KEY (scan_id, scanned_at);
CREATE INDEX ON parcel_scan_monthly (parcel_id);
CREATE INDEX ON parcel_scan_monthly (depot_id, scanned_at);
\echo PHASE analyze
VACUUM ANALYZE parcel_scan_monthly;
