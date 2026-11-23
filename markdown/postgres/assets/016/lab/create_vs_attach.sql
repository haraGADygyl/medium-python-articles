-- While a report holds ACCESS SHARE on parcel_scan, which way of adding a partition gets through?
-- Run with the report from report.sql open in another session.
\timing on
SET lock_timeout = '1s';
\echo === CREATE TABLE ... PARTITION OF
CREATE TABLE parcel_scan_2027_03 PARTITION OF parcel_scan
  FOR VALUES FROM ('2027-03-01 00:00+00') TO ('2027-04-01 00:00+00');
\echo === CREATE standalone, then ATTACH
CREATE TABLE parcel_scan_2027_03 (LIKE parcel_scan INCLUDING DEFAULTS);
ALTER TABLE parcel_scan_2027_03 ADD CONSTRAINT parcel_scan_2027_03_bound
  CHECK (scanned_at >= '2027-03-01 00:00+00' AND scanned_at < '2027-04-01 00:00+00');
ALTER TABLE parcel_scan ATTACH PARTITION parcel_scan_2027_03
  FOR VALUES FROM ('2027-03-01 00:00+00') TO ('2027-04-01 00:00+00');
SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent = 'parcel_scan'::regclass ORDER BY 1;
