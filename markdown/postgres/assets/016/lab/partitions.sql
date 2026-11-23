-- Keep months of partitions ahead of the writers. CREATE TABLE ... PARTITION OF would need
-- ACCESS EXCLUSIVE on parcel_scan; a standalone table + ATTACH needs only SHARE UPDATE EXCLUSIVE.
CREATE OR REPLACE FUNCTION create_scan_partition(month_start date)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  part text        := 'parcel_scan_' || to_char(month_start, 'YYYY_MM');
  lo   timestamptz := month_start;
  hi   timestamptz := month_start + interval '1 month';
BEGIN
  IF to_regclass(part) IS NOT NULL THEN
    RETURN;
  END IF;
  EXECUTE format('CREATE TABLE %I (LIKE parcel_scan INCLUDING DEFAULTS)', part);
  EXECUTE format('ALTER TABLE parcel_scan ATTACH PARTITION %I FOR VALUES FROM (%L) TO (%L)',
                 part, lo, hi);
END $$;

\timing on
SET lock_timeout = '1s';
SELECT create_scan_partition(m::date)
FROM generate_series(date_trunc('month', now()) + interval '1 month',
                     date_trunc('month', now()) + interval '6 months',
                     interval '1 month') AS m;
\timing off
SELECT inhrelid::regclass AS partition FROM pg_inherits
WHERE inhparent = 'parcel_scan'::regclass ORDER BY 1;

-- The sequence now belongs to the parent, so the legacy partition can be dropped one day.
BEGIN;
DROP TABLE parcel_scan_legacy;
SELECT nextval('parcel_scan_scan_id_seq') > 20000000 AS sequence_survived;
ROLLBACK;
