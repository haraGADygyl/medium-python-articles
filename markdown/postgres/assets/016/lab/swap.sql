-- Step 4: the only moment the table is locked.
\timing on
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE parcel_scan RENAME TO parcel_scan_legacy;
ALTER TABLE parcel_scan_legacy
  DROP CONSTRAINT parcel_scan_pkey,
  ADD CONSTRAINT parcel_scan_legacy_pkey PRIMARY KEY USING INDEX parcel_scan_id_time_key;
ALTER TABLE parcel_scan_new RENAME TO parcel_scan;
ALTER TABLE parcel_scan
  ATTACH PARTITION parcel_scan_legacy
  FOR VALUES FROM (MINVALUE) TO ('2026-12-01 00:00+00');
ALTER SEQUENCE parcel_scan_scan_id_seq OWNED BY parcel_scan.scan_id;
COMMIT;
