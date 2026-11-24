# Your Random UUID Primary Key Is Shredding Your Index

#### Loading 20 million rows with gen_random_uuid() keys took 280 seconds and 13.7 GB of WAL. With Postgres 18's uuidv7(), the same load took 91 seconds and 3.2 GB

**By Tihomir Manushev**

*Nov 24, 2026 · 8 min read*

---

The delivery log of a webhook service needs ids that leave the database. Customers see them in a `Webhook-Id` header, quote them in support tickets and use them to deduplicate retries, so a guessable `bigint` is out. `gen_random_uuid()` is built in and one `DEFAULT` away, which is how most tables like this get their key.

It works fine at first. As the table grows, every insert lands on a random page of the primary key index, and once the index no longer fits in memory, that randomness shows up as disk reads, half-empty pages and a write-ahead log several times larger than the data. PostgreSQL 18 added `uuidv7()`, a UUID that starts with a timestamp, and I measured what changes when that is the only difference.

The numbers come from PostgreSQL 18.6 in Docker on a Ryzen 5 3600 with NVMe storage, `shared_buffers = 256MB`, and the default `max_wal_size = 1GB` and `checkpoint_timeout = 5min`.

---

### Three tables that differ only in the key

```sql
CREATE TABLE delivery_v4 (
    delivery_id   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id   integer     NOT NULL,
    status_code   smallint    NOT NULL,
    payload_bytes integer     NOT NULL,
    attempted_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE delivery_v7 (LIKE delivery_v4 INCLUDING ALL);
ALTER TABLE delivery_v7 ALTER COLUMN delivery_id SET DEFAULT uuidv7();
```

`delivery_v7` copies the columns, the primary key and the defaults, then swaps the key's default. A third table, `delivery_serial`, uses `bigint GENERATED ALWAYS AS IDENTITY` as a baseline. There are no secondary indexes, so the primary key is the only index being maintained.

A version 4 UUID is 122 random bits. A version 7 UUID, as specified in RFC 9562, begins with a 48-bit Unix timestamp in milliseconds, and PostgreSQL fills the next 12 bits with a sub-millisecond fraction, so ids generated later sort higher. Both types take 16 bytes and both are globally unique. The only difference is where in the index a new key lands.

---

### Loading 20 million rows

Each table got 20 batches of a million rows, each batch measured on its own:

```sql
EXPLAIN (ANALYZE, BUFFERS, WAL)
INSERT INTO delivery_v4 (endpoint_id, status_code, payload_bytes)
SELECT 1 + (random() * 4999)::int,
       (ARRAY[200, 200, 200, 202, 204, 400, 410, 500, 503])[1 + (random() * 8)::int],
       200 + (random() * 9800)::int
FROM generate_series(1, 1000000);
```

`EXPLAIN ANALYZE` on an `INSERT` really inserts the rows, and the `WAL` option adds the log volume and the number of full-page images the statement produced. The `delivery_id` comes from the column default, so the same statement exercises each key type.

```text
20M-row load         bigint id      UUIDv4     UUIDv7
total time              47.8 s     280.3 s     90.5 s
20th million alone       2.3 s      46.0 s      5.8 s
WAL written           2,977 MB   13,687 MB   3,248 MB
full-page images            23   1,842,717         29
checkpoints                  8          28          9
primary key size        428 MB      772 MB     602 MB
leaf page density        90.0%       70.2%      90.0%
```

The v4 load did not slow down evenly. The first million took 4.7 s and the tenth 8.0 s. The batches got much slower when the index outgrew `shared_buffers`: the sixth batch read 2,775 blocks from outside the buffer cache, the seventh read 62,427, and the twentieth read 662,507. The v7 load stayed between 3.6 and 6.0 seconds per million and read almost nothing from outside the cache, because every insert goes to the same right-hand edge of the index, and that edge is always in memory.

---

### Where the extra 10 GB of WAL comes from

The first time a page changes after a checkpoint, PostgreSQL writes the whole 8 kB page into the WAL. This is a **full-page image**, and it lets crash recovery repair a page that was only half written to disk. Later changes to the same page before the next checkpoint log only the change.

A time-ordered key keeps modifying the same rightmost leaf until it fills, so it pays roughly one image per new page. A random key modifies a different leaf on almost every insert, and with 98,000 leaves, most inserts are that page's first change since the checkpoint. Each one adds 8 kB to the WAL for a row that takes about 65 bytes in the heap.

It also feeds itself. More WAL fills `max_wal_size` sooner and triggers an early checkpoint, which makes the next change to every page a "first change" again. The v4 load had 28 checkpoints against v7's 9, and wrote 1.84 million full-page images against 29.

The size difference comes from page splits. When the rightmost leaf of a B-tree fills, PostgreSQL leaves the old page at its fillfactor, 90% by default, and starts a new one. Any other leaf is split 50:50. Random keys split pages in the middle of the index, and those pages fill up again only slowly, so the index settled at 70% density and 772 MB. The v7 index holds the same 20 million keys in 602 MB.

---

### Single-row inserts, the way applications write

Bulk loads are the worst case. Applications usually insert one row per transaction, so I ran `pgbench` with 8 clients for 300 seconds, one full `checkpoint_timeout`, against each table at 20 million rows:

```sql
\set ep random(1, 5000)
\set bytes random(200, 10000)
INSERT INTO delivery_v4 (endpoint_id, status_code, payload_bytes) VALUES (:ep, 200, :bytes);
```

Each run started right after a `CHECKPOINT`, and `pg_stat_wal` was read before and after.

Throughput didn't separate them: v7 settled at about 1,900 transactions per second, and v4 at about 1,700, apart from an initial burst I couldn't explain. With one commit per row, every transaction waits for the WAL flush to disk, and a local NVMe drive absorbed the extra volume.

The log volume did separate them. v4 wrote 3,056 bytes of WAL per inserted row and v7 wrote 218, so five minutes produced 1,893 MB against 117 MB. v4 averaged 0.48 full-page images per row and set off three checkpoints, where v7 set off one. The v4 index read 446,403 blocks from outside the buffer cache in those five minutes, while the v7 index read 3.

That WAL doesn't stay on the primary. Every streaming replica receives it, the WAL archive stores it, and point-in-time recovery replays it. On a cloud volume with a throughput limit, 14 times the log volume can become the throughput limit as well.

---

### What else the timestamp buys

The creation time is part of the id, and ordering by the key is ordering by time:

```sql
SELECT uuid_extract_timestamp(uuidv7());   -- 2026-11-24 18:18:20.773+00
SELECT uuid_extract_timestamp(uuidv4());   -- NULL

SELECT delivery_id, endpoint_id, status_code
FROM delivery_v7
ORDER BY delivery_id DESC
LIMIT 50;
```

The latest 50 deliveries came back in 0.034 ms with a backward scan of the primary key, touching 51 buffers. The same question on the v4 table, `ORDER BY attempted_at DESC`, had no usable index: a parallel sequential scan over all 20 million rows took 1,564 ms. An index on `attempted_at` would fix that, but it is one more index for every insert to maintain, while v7 already has one.

Within one session, `uuidv7()` is strictly increasing. A million ids generated by one statement spanned 1,410 distinct milliseconds and every one sorted after the previous one, even within the same millisecond.

---

### Switching an existing table

A table already full of v4 keys doesn't need a rewrite:

```sql
ALTER TABLE delivery_v4 ALTER COLUMN delivery_id SET DEFAULT uuidv7();
```

It changes only the catalog and takes effect on the next insert. In the 60 seconds that followed, WAL per row dropped from 3,968 bytes to 227, and full-page images from 61,160 in the first minute after a checkpoint to 12. Ids generated in application code need the same change there.

The catch is in the index layout. The old random keys cover the entire UUID range, so the new keys, which all start with `01a2` today, land somewhere in the middle of the index rather than at its right edge. Every split there is a 50:50 split, because the B-tree code only fills to the fillfactor when the page is the rightmost one. It does have a heuristic for ascending runs inside an index, but PostgreSQL 18 skips it for single-column indexes. The new leaves held 145 rows each, against 261 in the pure v7 index, and that half-full growth continues for as long as old keys sort above the new ones.

An online rebuild packs everything back to the fillfactor:

```sql
REINDEX INDEX CONCURRENTLY delivery_v4_pkey;
```

It took 13.4 s without blocking writes and shrank the key from 815 MB to 627 MB, at 90% density. Run it once after the switch, and again whenever the new region has grown enough to matter.

---

### What uuidv7() gives away

**The timestamp is readable by anyone who has the id.** `uuid_extract_timestamp()` on the newest delivery id returned its creation time to the millisecond. For a webhook log that is harmless. For a user id in a public URL, it tells anyone when the account was created, and a sequence of ids reveals your signup rate. Keep v4, or a separate random public id, where that matters. `uuidv7(interval '-30 days')` shifts the embedded time, but a constant shift still shows the order and the rate, and one known creation date gives the offset away.

**Ordering is by clock, not by commit.** The monotonic guarantee covers one session. Across connections, a key generated earlier can commit later, so polling `WHERE delivery_id > :last_seen` will skip rows. Sequences have the same problem; a change feed needs logical replication.

**It is still 16 bytes.** The identity table's key took 428 MB against v7's 602 MB, its heap 1,149 MB against 1,302 MB, and every foreign key to a UUID doubles in width as well. If ids never leave the database and come from a single writer, a `bigint` is still smaller and faster.

---

### Conclusion

Random UUID keys cost more than the extra 8 bytes. Each insert dirties a random leaf, so the index stops fitting in memory, splits in the middle at 70% density and fills the WAL with full-page images: 280 seconds and 13.7 GB for a 20-million-row load, against 91 seconds and 3.2 GB with `uuidv7()`. With single-row commits, throughput stayed the same on fast local disks, but v4 still wrote 14 times the WAL.

On PostgreSQL 18, use `DEFAULT uuidv7()` for new tables that need UUIDs. For existing ones, change the default, run `REINDEX CONCURRENTLY` afterwards, and keep v4 only for ids whose creation time should stay private.
