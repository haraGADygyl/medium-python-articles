-- The empty partitioned table, built beside the live one.
CREATE TABLE parcel_scan_new (LIKE parcel_scan INCLUDING DEFAULTS)
  PARTITION BY RANGE (scanned_at);
ALTER TABLE parcel_scan_new
  ADD CONSTRAINT parcel_scan_new_pkey PRIMARY KEY (scan_id, scanned_at);
CREATE INDEX parcel_scan_new_parcel_idx ON parcel_scan_new (parcel_id);
CREATE INDEX parcel_scan_new_depot_time_idx ON parcel_scan_new (depot_id, scanned_at);
CREATE TABLE parcel_scan_2026_12 PARTITION OF parcel_scan_new
  FOR VALUES FROM ('2026-12-01 00:00+00') TO ('2027-01-01 00:00+00');
CREATE TABLE parcel_scan_2027_01 PARTITION OF parcel_scan_new
  FOR VALUES FROM ('2027-01-01 00:00+00') TO ('2027-02-01 00:00+00');
CREATE TABLE parcel_scan_2027_02 PARTITION OF parcel_scan_new
  FOR VALUES FROM ('2027-02-01 00:00+00') TO ('2027-03-01 00:00+00');
