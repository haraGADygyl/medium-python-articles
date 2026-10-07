\set VERBOSITY default
DROP TABLE IF EXISTS van_rental, van_insurance, campervan, ex_rental CASCADE;
-- block 1
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE campervan (
    van_id    integer  PRIMARY KEY,
    nickname  text     NOT NULL,
    berths    smallint NOT NULL
);

CREATE TABLE van_rental (
    rental_id      bigint    GENERATED ALWAYS AS IDENTITY,
    van_id         integer   NOT NULL REFERENCES campervan,
    renter         text      NOT NULL,
    rented_during  daterange NOT NULL,
    PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)
);
-- block 2
INSERT INTO campervan VALUES (7, 'Marigold', 4), (8, 'Big Kestrel', 6);

INSERT INTO van_rental (van_id, renter, rented_during) VALUES
    (7, 'Okafor',    '[2026-07-03,2026-07-10)'),
    (7, 'Lindqvist', '[2026-07-10,2026-07-14)');

INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', '[2026-07-08,2026-07-12)');
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', 'empty');
-- block 3
CREATE TABLE ex_rental (
    van_id         integer,
    rented_during  daterange,
    EXCLUDE USING gist (van_id WITH =, rented_during WITH &&)
);
INSERT INTO ex_rental VALUES
    (7, '[2026-07-03,2026-07-10)'), (7, 'empty'), (7, 'empty'), (7, NULL), (NULL, '[2026-07-03,2026-07-10)');
SELECT count(*) FROM ex_rental;
-- block 4
CREATE TABLE van_insurance (
    van_id          integer   NOT NULL REFERENCES campervan,
    covered_during  daterange NOT NULL,
    policy_ref      text      NOT NULL,
    PRIMARY KEY (van_id, covered_during WITHOUT OVERLAPS)
);

INSERT INTO van_insurance VALUES
    (7, '[2026-03-01,2026-09-01)', 'HX-2026-0071'),
    (7, '[2026-09-01,2027-03-01)', 'HX-2026-0244'),
    (8, '[2026-04-01,2026-08-15)', 'HX-2026-0102'),
    (8, '[2026-08-22,2027-04-01)', 'HX-2026-0310');

ALTER TABLE van_rental
    ADD CONSTRAINT van_rental_insured_fk
    FOREIGN KEY (van_id, PERIOD rented_during)
    REFERENCES van_insurance (van_id, PERIOD covered_during);
-- block 5
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Adeyemi', '[2026-08-27,2026-09-04)');    -- spans the renewal

INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (8, 'Kowalczyk', '[2026-08-12,2026-08-19)');  -- spans the lapse

DELETE FROM van_insurance WHERE policy_ref = 'HX-2026-0244';
-- block 6
ALTER TABLE van_rental ALTER CONSTRAINT van_rental_insured_fk DEFERRABLE INITIALLY DEFERRED;

BEGIN;
DELETE FROM van_insurance WHERE policy_ref = 'HX-2026-0071';
INSERT INTO van_insurance VALUES
    (7, '[2026-03-01,2026-06-01)', 'HX-2026-0071'),
    (7, '[2026-06-01,2026-09-01)', 'HX-2026-0071-B');
COMMIT;
SELECT * FROM van_insurance WHERE van_id = 7 ORDER BY covered_during;
-- gotchas
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', '[2026-07-08,2026-07-12)') ON CONFLICT DO NOTHING;
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', '[2026-07-08,2026-07-12)') ON CONFLICT (van_id, rented_during) DO NOTHING;
SELECT * FROM van_rental ORDER BY rental_id;
