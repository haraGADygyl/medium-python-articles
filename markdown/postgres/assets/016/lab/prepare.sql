-- Steps 1-3: online. The table keeps taking writes throughout.
ALTER TABLE parcel_scan
  ADD CONSTRAINT parcel_scan_legacy_bound
  CHECK (scanned_at < '2026-12-01 00:00+00') NOT VALID;
\timing on
ALTER TABLE parcel_scan VALIDATE CONSTRAINT parcel_scan_legacy_bound;
\echo PHASE index
CREATE UNIQUE INDEX CONCURRENTLY parcel_scan_id_time_key
  ON parcel_scan (scan_id, scanned_at);
