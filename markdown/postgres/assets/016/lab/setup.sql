-- 20M parcel scans, 2025-06-01 .. 2026-11-23, in time order (append-only, like the real thing).
DROP DATABASE IF EXISTS seed;
CREATE DATABASE seed;
\c seed
CREATE TABLE parcel_scan (
    scan_id     bigserial   PRIMARY KEY,
    parcel_id   bigint      NOT NULL,
    depot_id    integer     NOT NULL,
    scan_type   text        NOT NULL,
    device_ref  text        NOT NULL,
    weight_g    integer,
    scanned_at  timestamptz NOT NULL
);
INSERT INTO parcel_scan (parcel_id, depot_id, scan_type, device_ref, weight_g, scanned_at)
SELECT (g * 2654435761) % 3000000 + 1,
       (g * 7919) % 400 + 1,
       (ARRAY['INDUCT','SORT','LOAD','OUT_FOR_DELIVERY','DELIVERED'])[g % 5 + 1],
       'HS-' || lpad(((g * 31) % 9000)::text, 4, '0'),
       200 + (g * 13) % 24000,
       timestamptz '2025-06-01 00:00+00'
         + (g - 1)::integer * ((timestamptz '2026-11-23 06:00+00' - timestamptz '2025-06-01 00:00+00') / 20000000)
FROM generate_series(1::bigint, 20000000) AS g;
CREATE INDEX parcel_scan_parcel_idx ON parcel_scan (parcel_id);
CREATE INDEX parcel_scan_depot_time_idx ON parcel_scan (depot_id, scanned_at);
VACUUM (ANALYZE) parcel_scan;
SELECT pg_size_pretty(pg_table_size('parcel_scan')) AS heap,
       pg_size_pretty(pg_indexes_size('parcel_scan')) AS indexes,
       min(scanned_at), max(scanned_at), count(*)
FROM parcel_scan;
