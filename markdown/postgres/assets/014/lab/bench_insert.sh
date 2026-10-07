#!/usr/bin/env bash
# Load the same 1M rentals into tables with different overlap protection; 3 runs each.
set -euo pipefail
psql_() { docker exec -i pg18-temporal psql -U postgres -X -q -At "$@"; }

declare -A DDL=(
  [a_btree]="rental_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, van_id int NOT NULL, renter text NOT NULL, rented_during daterange NOT NULL"
  [b_exclude]="rental_id bigint GENERATED ALWAYS AS IDENTITY, van_id int NOT NULL, renter text NOT NULL, rented_during daterange NOT NULL, EXCLUDE USING gist (van_id WITH =, rented_during WITH &&)"
  [c_temporal_pk]="rental_id bigint GENERATED ALWAYS AS IDENTITY, van_id int NOT NULL, renter text NOT NULL, rented_during daterange NOT NULL, PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)"
  [d_pk_plain_fk]="rental_id bigint GENERATED ALWAYS AS IDENTITY, van_id int NOT NULL REFERENCES campervan, renter text NOT NULL, rented_during daterange NOT NULL, PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)"
  [e_pk_temporal_fk]="rental_id bigint GENERATED ALWAYS AS IDENTITY, van_id int NOT NULL, renter text NOT NULL, rented_during daterange NOT NULL, PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS), FOREIGN KEY (van_id, PERIOD rented_during) REFERENCES van_insurance (van_id, PERIOD covered_during)"
)
EXTRA_a_btree="CREATE INDEX ON bench_rental USING btree (van_id, rented_during);"

for variant in a_btree b_exclude c_temporal_pk d_pk_plain_fk e_pk_temporal_fk; do
  for run in 1 2 3; do
    extra=""; [[ $variant == a_btree ]] && extra="$EXTRA_a_btree"
    out=$(psql_ <<SQL
DROP TABLE IF EXISTS bench_rental;
CREATE TABLE bench_rental (${DDL[$variant]});
$extra
CHECKPOINT;
SELECT pg_current_wal_lsn() \gset
SELECT clock_timestamp() AS t0 \gset
INSERT INTO bench_rental (van_id, renter, rented_during) SELECT van_id, renter, rented_during FROM rental_stage;
SELECT round(extract(epoch FROM clock_timestamp() - :'t0') * 1000),
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), :'pg_current_wal_lsn')),
       pg_size_pretty(pg_indexes_size('bench_rental')),
       pg_size_pretty(pg_relation_size('bench_rental'));
SQL
)
    echo "$variant run$run ms|wal|indexes|heap: $out"
  done
done
