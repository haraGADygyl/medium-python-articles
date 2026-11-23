-- A long report transaction: it touches parcel_scan, then keeps its ACCESS SHARE lock for 20 s
-- (pg_sleep stands in for 20 s of real aggregation).
BEGIN;
SELECT count(*) FROM parcel_scan WHERE depot_id = 7;
SELECT pg_sleep(20);
COMMIT;
