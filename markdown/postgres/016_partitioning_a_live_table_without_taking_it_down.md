# Partitioning a Live Table Without Taking It Down

#### Copying 20 million rows into partitions froze writes for 49 seconds. Attaching the live table as one partition held its lock for 14 ms, because a CHECK constraint did the slow part first

**By Tihomir Manushev**

*Nov 23, 2026 · 8 min read*

---

Every partitioning tutorial starts with an empty table. Mine is the scan log of a parcel network, written around the clock, and the nightly job that deletes expired months has become the slowest thing in the database. Monthly partitions would turn that delete into a file drop. The usual migration copies everything into a new partitioned table and swaps the names, and writes stop while the copy runs.

On a 20-million-row copy of that table, the copy took 49 seconds. Another path held a lock for 14 milliseconds while 400 transactions per second kept running, and none failed. It attaches the existing table, as it is, as the first partition, after a `CHECK` constraint has already proved its bounds.

The numbers come from PostgreSQL 18.6 in Docker on a Ryzen 5 3600, `shared_buffers = 1GB`.

---

### The table, and the offline way

```sql
CREATE TABLE parcel_scan (
    scan_id     bigserial   PRIMARY KEY,
    parcel_id   bigint      NOT NULL,
    depot_id    integer     NOT NULL,
    scan_type   text        NOT NULL,   -- INDUCT, SORT, LOAD, OUT_FOR_DELIVERY, DELIVERED
    device_ref  text        NOT NULL,
    weight_g    integer,
    scanned_at  timestamptz NOT NULL
);
CREATE INDEX parcel_scan_parcel_idx     ON parcel_scan (parcel_id);
CREATE INDEX parcel_scan_depot_time_idx ON parcel_scan (depot_id, scanned_at);
```

It holds 20 million scans from June 2025 to today: a 1,563 MB heap and 1,240 MB of indexes. Rows arrive in time order and never change. During every experiment below, `pgbench` ran 8 clients at a fixed 400 transactions per second, four inserts for each parcel lookup.

The offline way copies everything into a table with 19 monthly partitions. The `INSERT ... SELECT` took 20.2 s, the three indexes 23.2 s and `VACUUM ANALYZE` 5.7 s: 49 seconds without writes, for 1.5 GB of heap. Every step touches the whole table, so the outage grows with it.

---

### Step 1: prove the boundary while writes continue

Pick a cutoff no row will reach before the swap, such as the first of next month. Older rows stay in the old table; newer ones go to monthly partitions.

```sql
ALTER TABLE parcel_scan
  ADD CONSTRAINT parcel_scan_legacy_bound
  CHECK (scanned_at < '2026-12-01 00:00+00') NOT VALID;

ALTER TABLE parcel_scan VALIDATE CONSTRAINT parcel_scan_legacy_bound;
```

`NOT VALID` adds the constraint in 1.2 ms without reading any existing row, and from that moment every new insert is checked against it. `VALIDATE` then reads the whole heap to confirm that the old rows comply. It holds only a `SHARE UPDATE EXCLUSIVE` lock, which conflicts with neither reads nor writes: it ran for 1,314 ms, and the slowest request during those seconds took 3.7 ms.

`ATTACH PARTITION` must prove every row fits the partition's bounds, and it skips that scan when a validated constraint already implies them.

---

### Step 2: an index the parent will accept

A unique index on a partitioned table must include the partition key, because each partition enforces uniqueness only among its own rows. `PRIMARY KEY (scan_id)` cannot exist on the new parent, while `PRIMARY KEY (scan_id, scanned_at)` can. The old table needs a matching unique index before it can be attached, and building it concurrently keeps writes flowing:

```sql
CREATE UNIQUE INDEX CONCURRENTLY parcel_scan_id_time_key
  ON parcel_scan (scan_id, scanned_at);
```

It took 7.1 s, and the slowest request during the build took 73.5 ms.

---

### Step 3: build the empty parent beside it

```sql
CREATE TABLE parcel_scan_new (LIKE parcel_scan INCLUDING DEFAULTS)
  PARTITION BY RANGE (scanned_at);
ALTER TABLE parcel_scan_new
  ADD CONSTRAINT parcel_scan_new_pkey PRIMARY KEY (scan_id, scanned_at);
CREATE INDEX parcel_scan_new_parcel_idx ON parcel_scan_new (parcel_id);
CREATE INDEX parcel_scan_new_depot_time_idx ON parcel_scan_new (depot_id, scanned_at);

CREATE TABLE parcel_scan_2026_12 PARTITION OF parcel_scan_new
  FOR VALUES FROM ('2026-12-01 00:00+00') TO ('2027-01-01 00:00+00');
```

`LIKE ... INCLUDING DEFAULTS` copies the columns, the `NOT NULL`s and the `nextval()` default, so ids keep coming from the same sequence. The parent's indexes mirror the old table's on purpose: on attach, Postgres adopts matching indexes and builds missing ones while holding the lock.

---

### Step 4: the swap

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE parcel_scan RENAME TO parcel_scan_legacy;
ALTER TABLE parcel_scan_legacy
  DROP CONSTRAINT parcel_scan_pkey,
  ADD CONSTRAINT parcel_scan_legacy_pkey PRIMARY KEY USING INDEX parcel_scan_id_time_key;
ALTER TABLE parcel_scan_new RENAME TO parcel_scan;
ALTER TABLE parcel_scan
  ATTACH PARTITION parcel_scan_legacy
  FOR VALUES FROM (MINVALUE) TO ('2026-12-01 00:00+00');
ALTER SEQUENCE parcel_scan_scan_id_seq OWNED BY parcel_scan.scan_id;
COMMIT;
```

The first rename takes an `ACCESS EXCLUSIVE` lock on the live table until `COMMIT`. The second statement exists because my first attempt failed with `multiple primary keys for table "parcel_scan_legacy" are not allowed`: the old key collides with the one the parent pushes down. Promoting the step 2 index takes under a millisecond. A foreign key referencing `parcel_scan_pkey` would block the drop, so check for one first.

At `client_min_messages = debug1`, the attach logs `partition constraint for table "parcel_scan_legacy" is implied by existing constraints` and reads no rows. `FROM (MINVALUE)` means everything below the cutoff, which the `CHECK` and the `NOT NULL` column imply exactly.

The transaction took about 14 ms, 11.7 of them in `COMMIT`, and the slowest request in that second took 5.0 ms. The run completed 30,049 transactions with 0 failures; the same `INSERT INTO parcel_scan` simply went through the new parent.

Without the step 1 constraint, the attach reads the whole heap under the lock: 1,444 ms, and the slowest request waited 1,448 ms. That is a cached 1.5 GB heap. On a cold table of several hundred gigabytes, the lock lasts as long as a full read.

---

### The lock queue: how 14 ms becomes 8 seconds

The swap is fast only if it gets its lock straight away. `ACCESS EXCLUSIVE` conflicts even with the `ACCESS SHARE` a plain `SELECT` holds until its transaction ends, and locks are granted in queue order, so a waiting `ALTER TABLE` blocks every query that arrives after it.

I opened a report transaction that held `parcel_scan` for 20 seconds, then ran the swap without `lock_timeout`:

```
second   tx   worst ms
    13  412       1.4
    14  155       4.9   <- swap starts waiting behind the report
    15    0       0.0
   ...
    22    0       0.0
    23 3884    8946.9   <- report ends, swap commits, the backlog drains
```

No transaction completed for eight seconds, lookups included. With `SET LOCAL lock_timeout = '2s'`, the swap gave up with `canceling statement due to lock timeout`, rolled back, and the slowest request took 2,003 ms. Keep the timeout short, retry in a loop, and check `pg_stat_activity` for old transactions first.

---

### Three things that break after the swap

**The sequence belongs to the old table.** `bigserial` ties the sequence to the original column, now in `parcel_scan_legacy`. Without the `OWNED BY` line, dropping the legacy partition fails with `cannot drop table parcel_scan_legacy because other objects depend on it`. `CASCADE` silences it by dropping the `scan_id` default everywhere, and the next insert failed with `null value in column "scan_id" ... violates not-null constraint`.

**Identity columns cannot be attached.** If the column is `GENERATED ALWAYS AS IDENTITY`, the attach fails with `The new partition may not contain an identity column`. Create the parent with `LIKE parcel_scan INCLUDING IDENTITY` and move the counter across in the swap, right after the first rename:

```sql
ALTER TABLE parcel_scan_legacy ALTER COLUMN scan_id DROP IDENTITY;
DO $$ BEGIN
  EXECUTE format('ALTER TABLE parcel_scan_new ALTER COLUMN scan_id RESTART WITH %s',
                 (SELECT max(scan_id) + 1 FROM parcel_scan_legacy));
END $$;
```

The rename already holds the lock, so no insert can slip in between reading the maximum and restarting the counter.

**A row without a partition is an error.** An insert with no matching partition fails with `no partition of relation "parcel_scan" found for row`, so partitions must exist ahead of time. Don't create them with `CREATE TABLE ... PARTITION OF`: it takes `ACCESS EXCLUSIVE` on the parent, and with a report open it timed out after one second. A standalone table plus `ATTACH` needs only `SHARE UPDATE EXCLUSIVE` and went through in 2.4 ms beside the same report:

```sql
CREATE OR REPLACE FUNCTION create_scan_partition(month_start date)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  part text        := 'parcel_scan_' || to_char(month_start, 'YYYY_MM');
  lo   timestamptz := month_start;
  hi   timestamptz := month_start + interval '1 month';
BEGIN
  IF to_regclass(part) IS NOT NULL THEN
    RETURN;
  END IF;

  EXECUTE format('CREATE TABLE %I (LIKE parcel_scan INCLUDING DEFAULTS)', part);
  EXECUTE format('ALTER TABLE parcel_scan ATTACH PARTITION %I FOR VALUES FROM (%L) TO (%L)',
                 part, lo, hi);
END $$;

SELECT create_scan_partition(m::date)
FROM generate_series(date_trunc('month', now()) + interval '1 month',
                     date_trunc('month', now()) + interval '6 months',
                     interval '1 month') AS m;
```

The function skips existing months. Each new table is empty, so the attach has nothing to scan and builds the parent's indexes on it instantly. The call that created the two missing months took 8.5 ms with the report still open. Schedule it daily with `pg_cron`, or hand the job to `pg_partman`.

---

### What pruning decides, and when it gives up

**Partition pruning** skips partitions whose bounds rule them out. Right after the swap there is little to prune, since everything before December is one partition, so I measured it on the 19-partition copy from the offline experiment.

A constant range prunes at plan time: the plan names a single partition. With `scanned_at >= now() - interval '7 days'` the planner can't fold `now()` into a constant, so pruning happens when execution starts:

```
 Aggregate (actual time=55.109..55.110 rows=1.00 loops=1)
   ->  Append (actual time=0.034..44.517 rows=257264.00 loops=1)
         Subplans Removed: 17
         ->  Index Only Scan using parcel_scan_monthly_2026_11_depot_id_scanned_at_idx on parcel_scan_monthly_2026_11 ...
         ->  Seq Scan on parcel_scan_monthly_2026_12 parcel_scan_monthly_2 (actual time=0.010..0.010 rows=0.00 loops=1)
```

A prepared statement on a generic plan, `WHERE scanned_at >= $1`, gets the same `Subplans Removed: 17`.

Pruning gives up when the key is wrapped in a function or cast. `WHERE scanned_at::date = date '2026-10-15'` scanned all 19 partitions in 2,709 ms, slower than the unpartitioned table's 2,486 ms. The same day as a half-open range touched one partition in 38 ms. Grep for the cast form before you migrate.

Queries without the key visit every partition. A lookup by `scan_id` alone went from 0.125 ms on the plain table to 0.372 ms partitioned. With prepared statements it was 0.117 against 0.140 ms, so most of the cost was planning 19 partitions, not probing them.

---

### Retention is the payoff

Dropping June 2025, 1,110,597 rows, on the monthly copy:

```sql
ALTER TABLE parcel_scan_monthly DETACH PARTITION parcel_scan_monthly_2025_06 CONCURRENTLY;
DROP TABLE parcel_scan_monthly_2025_06;
```

`DETACH ... CONCURRENTLY` takes only `SHARE UPDATE EXCLUSIVE` on the parent and can't run inside a transaction block. Detach and drop took 19 ms and 269 kB of WAL. Deleting the same month from the unpartitioned table took 953 ms and 146 MB of WAL, and the heap stayed at 1,563 MB.

The legacy partition can only be dropped whole, once its newest row expires; until then its retention is still a `DELETE`. Splitting it means another copy, since PostgreSQL 19.0 rejects `SPLIT PARTITION` as a syntax error.

---

### When not to partition

The costs stay after the migration. Uniqueness must include the partition key, so a foreign key to `scan_id` now needs `scanned_at` too. Queries without the key pay planning time for every partition. A job must create partitions forever, and the month it fails, inserts fail. If your queries don't filter on time, time partitions won't speed them up, and if the retention `DELETE` is fine, partitioning buys you nothing.

---

### Conclusion

A live table can be partitioned without copying it. Validate a `CHECK` matching the partition bounds and build the unique index with the key, both online, then rename, promote and attach in one transaction with a short `lock_timeout`. The locked part took 14 ms; the scan it replaced ran earlier under a lock that let writes through.

Before the swap, look for long transactions and foreign keys on the old key. During it, hand the sequence or identity to the parent. After it, attach future partitions instead of creating them with `PARTITION OF`, and make queries compare the key itself, not a cast of it. The legacy partition stays until its data expires.
