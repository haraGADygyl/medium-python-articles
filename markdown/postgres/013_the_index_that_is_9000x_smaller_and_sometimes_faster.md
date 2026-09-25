# The Index That Is 9,000x Smaller and Sometimes Faster

#### A 96 kB BRIN index beat an 857 MB B-tree on day-long range queries, until a purge touching 1.7% of the rows made it slower than a sequential scan

**By Tihomir Manushev**

*Sep 25, 2026 · 8 min read*

---

Every append-only table grows a timestamp index, and that index grows with the table. Forty million rows in, the B-tree on `passed_at` is 857 MB. It is rebuilt on every restore, carried in every backup and fought over in the buffer cache, and it exists to answer "what happened between Tuesday and Thursday".

A BRIN index answers the same question in 96 kB. On the table below it built five times faster and returned a one-day range twice as fast as the B-tree. Then I deleted 1.7% of the rows, inserted a day of new traffic, and the same BRIN index took 2.6 seconds for a query a sequential scan finished in 1.9. `pg_stats` still reported a correlation of 0.97.

Here is how BRIN works, where it wins, the failure mode behind that slowdown, and the two fixes.

Everything below ran on PostgreSQL 18.0 in Docker on a Ryzen 5 3600, `shared_buffers = 1GB`, `jit = off`, with parallel query disabled per session so each timing is one backend's work. Timings are the best of five runs with a warm cache.

---

### An append-only table and two indexes

A motorway toll network: every vehicle passing under a gantry becomes one row. Rows arrive in time order, give or take the thirty seconds it takes a gantry to batch its upload.

```sql
CREATE TABLE toll_transit (
    transit_id     bigint GENERATED ALWAYS AS IDENTITY,
    passed_at      timestamptz NOT NULL,
    gantry_id      integer     NOT NULL,
    lane           smallint    NOT NULL,
    vehicle_class  smallint    NOT NULL,
    plate_token    bigint      NOT NULL,
    fare_cents     integer     NOT NULL
);

INSERT INTO toll_transit (passed_at, gantry_id, lane, vehicle_class, plate_token, fare_cents)
SELECT timestamptz '2026-06-01 00:00:00+00'
         + (i * interval '198.72 milliseconds')
         + (random() * interval '30 seconds'),
       1 + (random() * 311)::int,
       1 + (random() * 5)::int,
       1 + (random() * 4)::int,
       (random() * 9e15)::bigint,
       (180 + random() * 1400)::int
FROM generate_series(1, 40000000) AS i;

VACUUM ANALYZE toll_transit;
```

Forty million transits over 92 days, 2,604 MB of heap. The `random() * interval '30 seconds'` term is the upload jitter: rows are nearly in order, never perfectly. Now two indexes on the same column:

```sql
CREATE INDEX toll_transit_passed_btree ON toll_transit USING btree (passed_at);
CREATE INDEX toll_transit_passed_brin  ON toll_transit USING brin  (passed_at);

SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE relname = 'toll_transit';
```

The B-tree took 11.5 seconds to build and is 857 MB. The BRIN index took 2.1 seconds and is 96 kB, 9,140 times smaller. Both answer `WHERE passed_at BETWEEN ...`, and the difference in size comes from what each one stores.

---

### How a 96 kB index answers a range query

A B-tree stores one entry per row: 40 million keys, each pointing at a tuple. **BRIN**, Block Range INdex, stores one entry per *range of heap pages*. The default `pages_per_range` is 128, so each entry summarises 1 MB of table, and for the default `minmax` operator class the summary is the smallest and largest value in that range. `pageinspect` shows the entries:

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;

SELECT blknum, value
FROM brin_page_items(get_raw_page('toll_transit_passed_brin', 3),
                     'toll_transit_passed_brin')
ORDER BY blknum
LIMIT 3;
```

```
 blknum |                              value
--------+------------------------------------------------------------------
  37248 | {2026-06-11 06:43:52.555627+00 .. 2026-06-11 07:35:11.147598+00}
  37376 | {2026-06-11 07:34:45.851244+00 .. 2026-06-11 08:25:58.226669+00}
  37504 | {2026-06-11 08:25:37.417191+00 .. 2026-06-11 09:16:54.798702+00}
```

Each 128-page range covers about 51 minutes of traffic, and neighbouring ranges overlap only by the jitter. Page 3 is where the summaries start in this index: the first pages of a BRIN index hold its metadata and its range map. To answer a range query, Postgres reads every summary. For the whole 2.6 GB table that took 14 buffer reads. It builds a bitmap of the ranges whose min–max interval overlaps the query, and reads only those pages in a **Bitmap Heap Scan**. The bitmap is **lossy**: it knows which pages might match, not which rows, so every row on those pages is rechecked against the condition.

This works only when a column's order on disk follows its values, which `pg_stats.correlation` measures. Here it is exactly 1.

---

### The benchmark

`SELECT count(*), sum(fare_cents)` over three windows, with only one index available at a time. The others were dropped inside a transaction that rolls back afterwards, a cheap way to ask the planner "what would you do without this index?" on a live table:

```
window  index                                ms  scan                buffers
1 hour  (no index)                       1652.9  Seq Scan            333,334
1 hour  toll_transit_passed_btree           4.5  Index Scan            7,567
1 hour  toll_transit_passed_brin            4.2  Bitmap Heap Scan        269
1 day   toll_transit_passed_btree         161.2  Index Scan          183,449
1 day   toll_transit_passed_brin           76.8  Bitmap Heap Scan      3,725
7 days  toll_transit_passed_btree         754.4  Index Scan        1,283,413
7 days  toll_transit_passed_brin          459.9  Bitmap Heap Scan     25,485
```

For one hour the two are tied at about 4 ms. For a day, BRIN is 2.1 times faster; for a week, 1.6 times. The buffer column explains it. A B-tree index scan fetches rows in key order, and with thirty seconds of jitter consecutive keys sit on different pages, so the scan touches a page once per row: 183,449 buffer accesses for a day. The bitmap heap scan reads each candidate page once, in physical order: 3,725 accesses. BRIN pays for its lossiness by rechecking about 10,000 extra rows at the edges of the window. That is cheap next to the page hopping.

`pages_per_range = 32` gives a finer summary (360 kB, four times the entries). It cut the rechecked rows from 12,609 to 4,929 on the one-hour query, and it was *slower* for the day, 115.8 ms against 76.8. On a well-ordered table the default is usually right.

---

### The failure nobody warns about

Tables like this do not stay append-only. A privacy request purges one driver's transits across the whole quarter. A fraud sweep deletes a gantry's bad readings. Here is a scattered purge of 1.7% of the rows, applied to an identical, perfectly ordered copy, followed by the next day's traffic:

```sql
CREATE TABLE toll_churned AS SELECT * FROM toll_transit ORDER BY passed_at;
VACUUM ANALYZE toll_churned;

DELETE FROM toll_churned WHERE plate_token % 50 = 7;   -- about 667,000 rows
VACUUM toll_churned;

INSERT INTO toll_churned (transit_id, passed_at, gantry_id, lane, vehicle_class, plate_token, fare_cents)
SELECT 40000000 + i,
       timestamptz '2026-09-01 00:00:00+00' + (i * interval '198.72 milliseconds'),
       1 + (random() * 311)::int, 1 + (random() * 5)::int, 1 + (random() * 4)::int,
       (random() * 9e15)::bigint, (180 + random() * 1400)::int
FROM generate_series(1, 800000) AS i;
ANALYZE toll_churned;
```

`VACUUM` marks the freed space in almost every page as reusable in the **free space map**. The next `INSERT` fills those gaps first, so September's rows land in pages from June, July and August. `pg_stats.correlation` for `passed_at` drops from 1 to 0.969, which still looks healthy. The BRIN summaries show what happened:

```
 blknum |                              value
--------+-----------------------------------------------------------------
  37248 | {2026-06-11 06:44:05.845985+00 .. 2026-09-01 04:07:31.53792+00}
  37376 | {2026-06-11 07:34:58.933198+00 .. 2026-09-01 04:08:13.66656+00}
  37504 | {2026-06-11 08:25:50.948977+00 .. 2026-09-01 04:09:03.94272+00}
```

Every one of the 2,613 ranges now reaches into September. A range's minimum and maximum can describe only one interval, so a single new row stretches the summary over three months. The benchmark, rebuilt on the churned table:

```
window  index                                ms  scan                buffers   recheck rows
1 hour  (no index)                       2151.2  Seq Scan            334,436              0
1 hour  toll_churned_passed_btree           3.1  Index Scan              205              0
1 hour  toll_churned_passed_brin         1515.7  Bitmap Heap Scan    161,421     19,351,148
Sep 1h  (no index)                       1934.8  Seq Scan            334,436              0
Sep 1h  toll_churned_passed_brin         2630.5  Bitmap Heap Scan    279,309     33,497,404
```

The one-hour query went from 4.2 ms to 1,515.7, and it rechecked 19 million rows to return 18,000. A query for September, the data people actually look at, read every page through the bitmap machinery and took 2,630 ms, 36% slower than simply scanning the table. Nothing errored and nothing logged. The planner still chose the index, because its cost model trusts a correlation of 0.97.

Correlation is the wrong health check. `Rows Removed by Index Recheck` in `EXPLAIN ANALYZE` is the right one: when it dwarfs the rows returned, the summaries have stopped discriminating.

---

### Two fixes: minmax_multi and summarisation

PostgreSQL 14 added `minmax_multi` operator classes, which keep up to 32 values per range, stored as several disjoint intervals instead of one:

```sql
CREATE INDEX toll_churned_passed_brin_multi ON toll_churned
    USING brin (passed_at timestamptz_minmax_multi_ops);
```

A range holding June rows plus a few September rows is now summarised as "these June intervals, and these September points", and a June query can skip it. On the churned table the one-hour query dropped back to 5.2 ms, and the day to 67.2 ms, faster than the B-tree's 77.7. It is not free. The index is 800 kB instead of 96 kB and took 9.1 seconds to build. The September query still took 81.8 ms against the B-tree's 5.7, because September rows really are scattered through every range and no summary can make them contiguous.

The second gotcha hits even a perfectly ordered table. New pages appended after the last summarisation are **unsummarised**, and BRIN must treat an unsummarised range as a possible match. I switched autovacuum off for the original table, as if the next run were still minutes away, appended one million rows and queried an hour of the new data:

```sql
ALTER TABLE toll_transit SET (autovacuum_enabled = false);

INSERT INTO toll_transit (passed_at, gantry_id, lane, vehicle_class, plate_token, fare_cents)
SELECT timestamptz '2026-09-01 00:00:30+00' + (i * interval '198.72 milliseconds'),
       1 + (random() * 311)::int, 1 + (random() * 5)::int, 1 + (random() * 4)::int,
       (random() * 9e15)::bigint, (180 + random() * 1400)::int
FROM generate_series(1, 1000000) AS i;

BEGIN;
DROP INDEX toll_transit_passed_btree;   -- leave BRIN as the only choice
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT count(*), sum(fare_cents) FROM toll_transit
WHERE passed_at >= '2026-09-01 06:00+00' AND passed_at < '2026-09-01 07:00+00';
ROLLBACK;

SELECT brin_summarize_new_values('toll_transit_passed_brin');
-- then run the BEGIN ... ROLLBACK block again

ALTER TABLE toll_transit RESET (autovacuum_enabled);
```

Before summarisation the plan showed `Heap Blocks: lossy=8227` and 969,084 rows removed by recheck, 108.3 ms. `brin_summarize_new_values` summarised 65 new ranges, and the same query then read 256 blocks in 3.45 ms. Normally `VACUUM` summarises new ranges, so the most recent data, the data most dashboards ask for, is the data BRIN helps least until the next vacuum. Creating the index `WITH (autosummarize = on)` asks autovacuum to summarise each range as it fills, which narrows that gap.

---

### What BRIN costs to write

The flip side of storing almost nothing is maintaining almost nothing. Appending five million rows to an empty table:

```
index       insert ms   WAL MB  index size
no index         7857      474        0 kB
B-tree          12439      790  108,152 kB
BRIN             8234      474       24 kB   then summarise 325 ranges: 804 ms
```

The B-tree added 58% to the insert time and 67% to the WAL. BRIN added 5% and no WAL during the insert, because rows landing in new, unsummarised ranges do not touch the index at all. The work moved to summarisation, 804 ms for all 325 ranges, done in the background by vacuum. On an ingest-heavy table that difference compounds into replication lag and backup size.

---

### When not to use BRIN

When the column's physical order does not follow its values: UUIDs, hashes, user ids, anything assigned at random. BRIN summaries of such a column cover the whole value space in every range.

When rows are updated or deleted and the space is reused. The churn experiment is the whole argument. If the table sees scattered deletes, use `minmax_multi`, keep a B-tree, or restore physical order with `CLUSTER` on a B-tree or `pg_repack --order-by=passed_at`. `VACUUM FULL` alone compacts the table but keeps the interleaved rows where they are.

For point lookups and selective filters. BRIN returns 128-page candidates, so fetching one row means reading 1 MB. It cannot enforce uniqueness, cannot provide sorted output for `ORDER BY ... LIMIT`, and cannot support an index-only scan. Primary keys stay B-trees.

---

### Conclusion

On an append-only table whose timestamp follows insertion order, BRIN is 9,140 times smaller than a B-tree, builds five times faster, costs almost nothing on insert, and returned day-long and week-long ranges faster than the B-tree here because it reads pages in order instead of hopping between them.

It depends on physical order that ordinary maintenance quietly destroys. A purge touching 1.7% of the rows, followed by normal inserts, made it slower than a sequential scan, while `pg_stats` reported a correlation of 0.97. Watch `Rows Removed by Index Recheck`, not correlation. Reach for `timestamptz_minmax_multi_ops` if the table sees scattered deletes, and summarise new ranges promptly, either with `autosummarize` or a scheduled `brin_summarize_new_values`, if the newest data matters most. With those two habits, BRIN stays at 96 kB and stays fast.
