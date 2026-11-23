\set parcel random(1, 3000000)
SELECT scan_type, depot_id, scanned_at FROM parcel_scan WHERE parcel_id = :parcel ORDER BY scanned_at;
