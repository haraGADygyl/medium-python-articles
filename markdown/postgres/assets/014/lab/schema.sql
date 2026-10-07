DROP TABLE IF EXISTS van_rental, van_insurance, campervan CASCADE;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE campervan (
    van_id    integer PRIMARY KEY,
    nickname  text NOT NULL,
    berths    smallint NOT NULL
);

CREATE TABLE van_insurance (
    van_id          integer   NOT NULL REFERENCES campervan,
    covered_during  daterange NOT NULL,
    policy_ref      text      NOT NULL,
    PRIMARY KEY (van_id, covered_during WITHOUT OVERLAPS)
);

CREATE TABLE van_rental (
    rental_id      bigint GENERATED ALWAYS AS IDENTITY,
    van_id         integer   NOT NULL,
    renter         text      NOT NULL,
    rented_during  daterange NOT NULL,
    PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS),
    FOREIGN KEY (van_id, PERIOD rented_during)
        REFERENCES van_insurance (van_id, PERIOD covered_during)
);
