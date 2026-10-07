# Postgres 18 Can Enforce "No Two Bookings Overlap" For You

#### Twenty-four workers double-booked a campervan fleet through a check-then-insert. A WITHOUT OVERLAPS key let zero through, and its temporal foreign key is the part that is actually new

**By Tihomir Manushev**

*Oct 7, 2026 · 8 min read*

---

Every booking system has the same three lines somewhere: look for a reservation that overlaps the requested dates, and if there is none, insert one. It passes every code review because it is obviously correct for one user. I ran it with 24 concurrent workers against a 20-van fleet, 6,000 booking attempts in all. The first run left 15 pairs of overlapping rentals: the same van promised to two families for the same days, fifteen times.

PostgreSQL 18 lets the primary key say it instead: `PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)`. Under the same load, zero overlaps. That half is not entirely new, because an exclusion constraint could do it since 9.0. The genuinely new half is the **temporal foreign key**, which can refuse a rental on days the van was not insured. Nothing in Postgres could declare that before.

Everything below ran on PostgreSQL 18.0 in Docker on a Ryzen 5 3600, `shared_buffers = 1GB`, `jit = off`.

---

### The race your code review cannot see

Here is the check-then-insert, written the way most applications write it, in its own transaction at the default `READ COMMITTED` isolation:

```python
from datetime import date

import psycopg


def book_van(conn: psycopg.Connection, van_id: int, renter: str,
             first_day: date, day_after_last: date) -> bool:
    """Book a van if no existing rental overlaps the requested dates."""
    with conn.transaction():
        taken = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM van_rental WHERE van_id = %s"
            " AND rented_during && daterange(%s, %s))",
            (van_id, first_day, day_after_last),
        ).fetchone()[0]
        if taken:
            return False
        conn.execute(
            "INSERT INTO van_rental (van_id, renter, rented_during)"
            " VALUES (%s, %s, daterange(%s, %s))",
            (van_id, renter, first_day, day_after_last),
        )
    return True
```

Two transactions can both run the `SELECT`, both see an empty calendar, and both insert. Neither one is wrong about what it saw. Each worker made 250 attempts with a random van, a random start in a 180-day season and a stay of 3 to 10 days. Three runs per variant:

```
variant                         booked   overlapping pairs   rejected by the database
check-then-insert, READ COMM.   528-533        10-16          0
check-then-insert, SERIALIZABLE 466-475            0          1,111-1,170 serialization failures
WITHOUT OVERLAPS key            517-524            0          12-16 exclusion violations
```

`SERIALIZABLE` fixes it, at a price. It tracks reads at page granularity, so about 19% of all attempts aborted with a serialization failure, while the real collisions numbered a dozen or so per run. Without a retry loop it booked about 50 fewer rentals. The constraint rejected 12 to 16 attempts per run, only the real collisions, and every other booking went through.

---

### A primary key with a period in it

The schema needs one extension. The key mixes an integer, compared with `=`, and a range, compared with `&&`, so the index behind it must be GiST, and plain integers have no GiST operator class until `btree_gist` provides one. Without it, `CREATE TABLE` fails with `data type integer has no default operator class for access method "gist"`.

```sql
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
```

The key reads as "unique per van, where two periods count as equal if they overlap". `WITHOUT OVERLAPS` must be on the last column, and that column must be a range or multirange. Now some rentals:

```sql
INSERT INTO campervan VALUES (7, 'Marigold', 4), (8, 'Big Kestrel', 6);

INSERT INTO van_rental (van_id, renter, rented_during) VALUES
    (7, 'Okafor',    '[2026-07-03,2026-07-10)'),
    (7, 'Lindqvist', '[2026-07-10,2026-07-14)');

INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', '[2026-07-08,2026-07-12)');
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Moreau', 'empty');
```

The first two rows share 10 July and still go in. The `[)` bounds mean Okafor returns the van on the morning Lindqvist collects it, so back-to-back rentals touch without overlapping. The third fails:

```
ERROR:  conflicting key value violates exclusion constraint "van_rental_pkey"
DETAIL:  Key (van_id, rented_during)=(7, [2026-07-08,2026-07-12)) conflicts with
         existing key (van_id, rented_during)=(7, [2026-07-03,2026-07-10)).
```

Read the message twice: a *primary key* violates an *exclusion constraint*. Under the hood, `WITHOUT OVERLAPS` is an exclusion constraint on `(van_id WITH =, rented_during WITH &&)`, and the insert path is the same one. What the key adds shows up when you try the old version with the fourth insert's input:

```sql
CREATE TABLE ex_rental (
    van_id         integer,
    rented_during  daterange,
    EXCLUDE USING gist (van_id WITH =, rented_during WITH &&)
);
INSERT INTO ex_rental VALUES
    (7, '[2026-07-03,2026-07-10)'), (7, 'empty'), (7, 'empty'),
    (7, NULL), (NULL, '[2026-07-03,2026-07-10)');
SELECT count(*) FROM ex_rental;   -- 5
```

All five rows go in. An empty range overlaps nothing, so a rental with no dates passes any number of times, and `NULL` never compares equal to anything. The primary key refuses both: key columns are `NOT NULL`, and the fourth insert above failed with `empty WITHOUT OVERLAPS value found in column "rented_during"`. The key also tells every tool that reads the catalog, from ORMs to schema diff tools, that `(van_id, rented_during)` is this table's identity.

---

### The new part: a foreign key over time

A van may only be rented on days it is insured. Policies renew, sometimes with a gap when someone forgets the paperwork:

```sql
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
```

`PERIOD` changes the meaning of the reference from "a matching row exists" to "matching rows *cover* this period". With `auto_explain` logging nested statements, the check behind every rental insert looks like this (tidied):

```sql
SELECT 1
FROM (SELECT covered_during AS r
      FROM ONLY van_insurance x
      WHERE van_id = $1 AND covered_during && $2
      FOR KEY SHARE OF x) x1
HAVING $2 <@ range_agg(x1.r);
```

It locks every policy that overlaps the rental, merges them with `range_agg`, and passes only if the rental fits inside the union. Coverage can come from several rows:

```sql
INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (7, 'Adeyemi', '[2026-08-27,2026-09-04)');    -- spans the renewal

INSERT INTO van_rental (van_id, renter, rented_during)
VALUES (8, 'Kowalczyk', '[2026-08-12,2026-08-19)');  -- spans the lapse

DELETE FROM van_insurance WHERE policy_ref = 'HX-2026-0244';
```

Adeyemi's rental crosses from one policy into the next and is accepted, because the two policies meet with no gap. Kowalczyk's rental falls into Big Kestrel's week-long lapse and is refused with `Key (van_id, rented_during)=(8, [2026-08-12,2026-08-19)) is not present in table "van_insurance"`. The `DELETE` is refused too, because cancelling the second policy would leave Adeyemi driving uninsured from 1 September. Shrinking a policy's period is checked the same way.

That strictness has one awkward consequence. Splitting a policy in two is a delete followed by an insert, and the delete fails on its own before the insert can repair the coverage. Making the constraint deferred moves the check to `COMMIT`:

```sql
ALTER TABLE van_rental
    ALTER CONSTRAINT van_rental_insured_fk DEFERRABLE INITIALLY DEFERRED;

BEGIN;
DELETE FROM van_insurance WHERE policy_ref = 'HX-2026-0071';
INSERT INTO van_insurance VALUES
    (7, '[2026-03-01,2026-06-01)', 'HX-2026-0071'),
    (7, '[2026-06-01,2026-09-01)', 'HX-2026-0071-B');
COMMIT;
```

The split commits, because coverage is whole again by the time anyone checks. When I repeated it with the second half ending on 28 August, the `COMMIT` failed: three uninsured days under Adeyemi's rental.

---

### What it costs

I loaded the same million rentals, 50 per van for 20,000 vans, into an empty `bench_rental` table with `van_rental`'s columns, under five schemas. Each van had two back-to-back yearly policies. The first schema has no overlap protection and is there as the baseline. Median of three runs:

```
schema                                        load ms   µs/row   index size
B-tree PK on rental_id + B-tree (van, range)     3,977      4.0        69 MB
EXCLUDE USING gist                              24,091     24.1        45 MB
PRIMARY KEY ... WITHOUT OVERLAPS                25,575     25.6        45 MB
  + plain FK on van_id                          28,952     29.0        45 MB
  + temporal FK to van_insurance                45,515     45.5        45 MB
```

The GiST index is the expensive part: more than six times the B-tree's insert cost. `EXCLUDE` and `WITHOUT OVERLAPS` land within run-to-run noise of each other, which confirms they are one mechanism. The temporal foreign key costs about 20 µs per row, six times a plain one, because each check locks and aggregates the overlapping policies instead of probing a single key. For a booking system that writes a few rows a second, 45 µs is nothing. For an ingest pipeline at 50,000 rows a second, it is most of a core.

Reads cost nothing extra, because the key's index serves the questions a booking system asks most:

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT renter, rented_during
FROM bench_rental
WHERE van_id = 4242 AND rented_during @> date '2026-03-15';
```

```
 Index Scan using bench_rental_pkey on bench_rental (actual time=0.028..0.029 rows=1.00 loops=1)
   Index Cond: ((van_id = 4242) AND (rented_during @> '2026-03-15'::date))
   Index Searches: 1
   Buffers: shared hit=4
 Execution Time: 0.038 ms
```

Four buffers and 0.038 ms to find who has van 4242 on 15 March, among a million rentals.

---

### Adding it to a table that already exists

`ALTER TABLE ... ADD PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)` on the million-row table took 21.6 seconds under an `ACCESS EXCLUSIVE` lock, so no reads either. There is no concurrent path: `ADD PRIMARY KEY USING INDEX` refuses a GiST index because it "is not a unique index", and it will not adopt the index of an existing `EXCLUDE` constraint either. Run a self-join for overlapping rows first, because one surviving overlap aborts the whole 21 seconds.

The foreign key hides a bigger surprise. Added in one statement, it took 20.6 seconds, and `pg_stat_user_indexes` showed exactly 1,000,000 new scans on the insurance key: one probe per rental. Added in two steps, it took a third of a second:

```sql
ALTER TABLE bench_rental
    ADD CONSTRAINT bench_rental_cover_fk
    FOREIGN KEY (van_id, PERIOD rented_during)
    REFERENCES van_insurance (van_id, PERIOD covered_during) NOT VALID;

ALTER TABLE bench_rental VALIDATE CONSTRAINT bench_rental_cover_fk;
```

`NOT VALID` only enforces the constraint for new writes. `VALIDATE` then checked every existing row in 0.33 seconds with no new index scans. I planted an uninsured rental to make sure it was really checking, and it failed with the same error. It also holds a lighter lock than `ADD`. On 18.0, there is no reason to add a temporal foreign key any other way.

---

### Gotchas

**The error code is not a unique violation.** A conflict raises SQLSTATE `23P01`, `exclusion_violation`, not `23505`. Code that catches `UniqueViolation` to show "those dates are taken" lets this one escape as a 500.

**`ON CONFLICT` only half works.** `ON CONFLICT DO NOTHING` without a target skips the conflicting row. `ON CONFLICT (van_id, rented_during)` fails with "no unique or exclusion constraint matching", and `DO UPDATE` is not supported at all.

**No `FOR PORTION OF` yet.** Shortening one rental by two days in the middle of a policy, or splitting a row at a date, is still hand-written SQL. PostgreSQL 18 shipped the constraints without the temporal `UPDATE` and `DELETE` syntax.

**Foreign keys support only `NO ACTION`.** `ON DELETE CASCADE`, `RESTRICT` and `SET NULL` are rejected with "unsupported ON DELETE action for foreign key constraint using PERIOD".

**Inclusive bounds collide.** `daterange` normalises `[2026-07-14,2026-07-16]` to `[2026-07-14,2026-07-17)`, so dates are safe. A `tstzrange` ending in `]` at 10:00 conflicts with the next rental starting at 10:00. Use `[)` everywhere.

---

### Conclusion

A check-then-insert at `READ COMMITTED` double-booked 10 to 16 times per 6,000 attempts here. `SERIALIZABLE` stopped it by aborting a fifth of all bookings. A `WITHOUT OVERLAPS` primary key stopped it by rejecting only the real collisions. It is an exclusion constraint with a better name, plus the two holes `EXCLUDE` leaves open closed: `NULL` and empty ranges.

The temporal foreign key is the part you could not declare before: a rental must fall inside insured days, across renewals, and nobody can cancel the cover beneath it. Budget for a GiST index on the write path, make the key deferrable if periods get split, catch `23P01`, and always add the foreign key as `NOT VALID` followed by `VALIDATE`.
