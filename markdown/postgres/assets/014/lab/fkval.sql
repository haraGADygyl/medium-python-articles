\timing on
ALTER TABLE bench_rental DROP CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental ADD CONSTRAINT bench_rental_cover_fk FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during);
ALTER TABLE bench_rental DROP CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental ADD CONSTRAINT bench_rental_cover_fk FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during) NOT VALID;
ALTER TABLE bench_rental VALIDATE CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental DROP CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental ADD CONSTRAINT bench_rental_cover_fk FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during);
ALTER TABLE bench_rental DROP CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental ADD CONSTRAINT bench_rental_cover_fk FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during) NOT VALID;
ALTER TABLE bench_rental VALIDATE CONSTRAINT bench_rental_cover_fk;
ALTER TABLE bench_rental ADD CONSTRAINT bench_rental_van_fk FOREIGN KEY (van_id) REFERENCES campervan;
