\timing on
-- bulk load first, constraints after
DROP TABLE IF EXISTS bench_rental;
CREATE TABLE bench_rental (rental_id bigint GENERATED ALWAYS AS IDENTITY, van_id int NOT NULL, renter text NOT NULL, rented_during daterange NOT NULL);
INSERT INTO bench_rental (van_id, renter, rented_during) SELECT van_id, renter, rented_during FROM rental_stage;
ALTER TABLE bench_rental ADD PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS);
ALTER TABLE bench_rental ADD FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during);
\timing off
SELECT indexrelid::regclass, pg_size_pretty(pg_relation_size(indexrelid)) FROM pg_index WHERE indrelid = 'bench_rental'::regclass;
CREATE INDEX bench_btree_tmp ON bench_rental USING btree (van_id, rented_during);
SELECT pg_size_pretty(pg_relation_size('bench_btree_tmp'));
DROP INDEX bench_btree_tmp;
VACUUM ANALYZE bench_rental;
-- lookup: who has van 4242 on 15 March 2026
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT renter, rented_during FROM bench_rental WHERE van_id = 4242 AND rented_during @> date '2026-03-15';
-- conflict check for a requested window
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT renter, rented_during FROM bench_rental WHERE van_id = 4242 AND rented_during && daterange('2026-03-10','2026-03-20');
-- free vans for a window
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*) FROM campervan c
WHERE NOT EXISTS (SELECT 1 FROM bench_rental r WHERE r.van_id = c.van_id AND r.rented_during && daterange('2026-03-10','2026-03-14'));
