\set parcel random(1, 3000000)
\set depot random(1, 400)
INSERT INTO parcel_scan (parcel_id, depot_id, scan_type, device_ref, weight_g, scanned_at)
VALUES (:parcel, :depot, 'SORT', 'HS-0042', 1200, now());
