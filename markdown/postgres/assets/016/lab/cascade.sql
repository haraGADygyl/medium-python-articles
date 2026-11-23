-- What DROP ... CASCADE does when the sequence is still owned by the legacy table.
BEGIN;
ALTER SEQUENCE parcel_scan_scan_id_seq OWNED BY parcel_scan_legacy.scan_id;
DROP TABLE parcel_scan_legacy CASCADE;
SELECT column_default FROM information_schema.columns
WHERE table_name = 'parcel_scan' AND column_name = 'scan_id';
INSERT INTO parcel_scan (parcel_id, depot_id, scan_type, device_ref, weight_g, scanned_at)
VALUES (1, 1, 'SORT', 'HS-0042', 1200, '2026-12-02 10:00+00');
ROLLBACK;
