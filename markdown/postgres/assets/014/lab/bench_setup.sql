\i /schema.sql
-- 20,000 vans, each insured by two back-to-back yearly policies
INSERT INTO campervan (van_id, nickname, berths)
SELECT v, 'van-' || v, 2 + v % 5 FROM generate_series(1, 20000) AS v;
INSERT INTO van_insurance (van_id, covered_during, policy_ref)
SELECT v, daterange(date '2025-01-01' + y * 365, date '2025-01-01' + (y + 1) * 365),
       format('HX-%s-%s', v, y)
FROM generate_series(1, 20000) AS v, generate_series(0, 1) AS y;
-- 1M rentals staged in an unindexed table: 50 per van, one per 14-day slot
DROP TABLE IF EXISTS rental_stage;
CREATE TABLE rental_stage AS
SELECT v AS van_id,
       'renter-' || v || '-' || k AS renter,
       daterange(date '2025-01-01' + k * 14 + (hashint4(v * 97 + k) & 3),
                 date '2025-01-01' + k * 14 + (hashint4(v * 97 + k) & 3) + 3 + (hashint4(v + k * 31) & 7))
         AS rented_during
FROM generate_series(1, 20000) AS v, generate_series(0, 49) AS k;
VACUUM ANALYZE campervan, van_insurance, rental_stage;
SELECT count(*), min(lower(rented_during)), max(upper(rented_during)) FROM rental_stage;
