# Replace Debezium with Postgres Logical Replication

#### Change data capture without a JVM, a Kafka Connect cluster, or the team it takes to operate them — plus the four failure modes that will fill your disk

**By Tihomir Manushev**

*Aug 24, 2026 · 12 min read*

---

The standard change-data-capture stack asks for a lot before it moves a single row. Kafka, a Connect cluster, a Debezium connector, usually a schema registry, and a JVM to keep warm underneath all of it. Then the on-call rotation that understands connector rebalancing, and the runbook for what to do when the connector's offsets and the database's replication slot disagree about where they are.

Half of that machinery exists to read the write-ahead log of a database that already streams its own changes. Postgres has shipped logical replication since version 10, and the decoding infrastructure Debezium uses is the *same* infrastructure — the Postgres connector is a client of the replication protocol, not a replacement for it.

This article builds working CDC on Postgres 17 twice: as table-to-table replication between two servers, and as a raw change stream your own application consumes. Then it spends the second half on the four ways this breaks in production, because the setup is three statements and the operations are where the interesting parts live.

Everything below runs on two Postgres 17.6 containers on one Docker network, on a Ryzen 5 3600.

---

### What Debezium is actually doing

Three pieces make logical decoding work, and they are worth naming because every failure later traces back to one of them.

The **write-ahead log** already records every change for crash recovery. At `wal_level = replica` those records describe physical block changes, which is enough to rebuild a byte-identical replica and useless for anything else. At `wal_level = logical`, Postgres adds enough information to reconstruct the change as *rows* — which table, which columns, which old values.

A **replication slot** is a bookmark with teeth. It remembers the last position a consumer confirmed, and it guarantees Postgres will not recycle WAL beyond that point. That guarantee is the whole value proposition — a consumer can disconnect for an hour and resume exactly where it stopped — and it is also the mechanism that fills your disk when the consumer never comes back.

An **output plugin** turns WAL records into something readable. `pgoutput` is built in and speaks the binary protocol Postgres subscribers use. `test_decoding` is also built in, emits plain text, and despite the name is the right tool for exploring what your workload actually produces.

Start the server with logical WAL and room for slots:

```bash
docker run -d --name pg-pub -e POSTGRES_PASSWORD=demo -e POSTGRES_DB=terminal \
  postgres:17 -c wal_level=logical -c max_replication_slots=10 -c max_wal_senders=10
```

On a real server those three go in `postgresql.conf`, and `wal_level` requires a restart — plan for it, because it is the only restart in this entire setup.

---

### Table to table in three statements

The domain is a container terminal: every crane move against a vessel produces a row, and berth occupancy changes as ships come and go.

```sql
CREATE TABLE container_move (
    move_id       bigserial PRIMARY KEY,
    container_no  text NOT NULL,
    berth_code    text NOT NULL,
    move_kind     text NOT NULL CHECK (move_kind IN ('discharge','load','shift')),
    crane_id      smallint NOT NULL,
    moved_at      timestamptz NOT NULL DEFAULT now(),
    gross_kg      integer NOT NULL,
    is_reefer     boolean NOT NULL DEFAULT false
);

CREATE TABLE berth_status (
    berth_code    text PRIMARY KEY,
    occupied_by   text,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
```

Fifty thousand moves seeded on the publisher, and a role allowed to replicate:

```sql
INSERT INTO container_move (container_no, berth_code, move_kind, crane_id, gross_kg, is_reefer)
SELECT 'MSKU' || to_char(n, 'FM0000000'),
       'B' || (1 + (n % 6)),
       (ARRAY['discharge','load','shift'])[1 + (n % 3)],
       1 + (n % 9),
       4200 + (n % 26000),
       (n % 11) = 0
FROM generate_series(1, 50000) AS n;

CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'demo';
GRANT USAGE ON SCHEMA public TO replicator;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO replicator;
```

The subscriber needs the same tables and no data. `pg_dump --schema-only` is the honest way to get them there — remember that part, it comes back to bite in a later section.

Now the publication on the source:

```sql
CREATE PUBLICATION terminal_moves FOR TABLE container_move, berth_status;
```

And the subscription on the destination:

```sql
CREATE SUBSCRIPTION terminal_feed
    CONNECTION 'host=pg-pub dbname=terminal user=replicator password=demo'
    PUBLICATION terminal_moves;
```

```
NOTICE:  created replication slot "terminal_feed" on publisher
CREATE SUBSCRIPTION
```

That single statement did four things: connected to the publisher, created a replication slot there, copied every existing row, and started streaming. Eight seconds later the subscriber holds all 50,000 rows without anyone running a `COPY`.

The **initial snapshot** is the part teams expect to build themselves. Postgres runs it per table in parallel workers, using an exported snapshot so the copy is consistent with the exact LSN where streaming begins — no gap and no overlap between "the rows that were there" and "the rows that arrived after."

Streaming is then continuous. An insert on the publisher:

```sql
INSERT INTO container_move (container_no, berth_code, move_kind, crane_id, gross_kg)
VALUES ('TGHU9911223','B4','discharge',7,18400);
```

showed up on the subscriber inside the first 100 ms poll. Updates and deletes travel the same path, and lag is visible from the publisher at any moment:

```sql
SELECT slot_name,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS retained
FROM pg_replication_slots;
```

```
   slot_name   | retained
---------------+----------
 terminal_feed | 0 bytes
```

`retained` is the single most important number in this article. It is how much WAL the publisher is holding because the consumer has not confirmed it yet. Zero means caught up. Growing means trouble, and there is a section on that below.

---

### When you want changes in your application, not another database

Table-to-table replication is the easy case. Debezium exists because people want changes in Kafka, in Elasticsearch, in a cache invalidator, in an audit pipeline — somewhere that is not another Postgres table.

For that, create the slot directly and read from it:

```sql
SELECT pg_create_logical_replication_slot('app_cdc', 'test_decoding');
```

```
 pg_create_logical_replication_slot
------------------------------------
 (app_cdc,0/21B5FE8)
```

From this moment the slot retains WAL for you. Every change to every table in the database is decodable, and nothing is discarded until you say so. Do some work:

```sql
INSERT INTO container_move (container_no, berth_code, move_kind, crane_id, gross_kg, is_reefer)
VALUES ('CAIU7788990','B2','load',3,22150,true);
UPDATE berth_status SET occupied_by='VESSEL-07' WHERE berth_code='B2';
```

And read it back:

```sql
SELECT lsn, xid, data FROM pg_logical_slot_peek_changes('app_cdc', NULL, NULL);
```

```
lsn  | 0/21B5FE8
xid  | 750
data | BEGIN 750

lsn  | 0/21B5FE8
xid  | 750
data | table public.container_move: INSERT: move_id[bigint]:50002
       container_no[text]:'CAIU7788990' berth_code[text]:'B2' move_kind[text]:'load'
       crane_id[smallint]:3 moved_at[timestamp with time zone]:'2026-08-30 13:51:31.082995+00'
       gross_kg[integer]:22150 is_reefer[boolean]:true

lsn  | 0/21B60A8
xid  | 750
data | table public.berth_status: UPDATE: berth_code[text]:'B2'
       occupied_by[text]:'VESSEL-07' updated_at[timestamp with time zone]:'2026-08-30 13:50:50.394815+00'

lsn  | 0/21B6138
xid  | 750
data | COMMIT 750
```

Every change, in commit order, wrapped in transaction boundaries, with column names and types. That is the raw material Debezium reshapes into its envelope format. If your consumer needs only "table, operation, new values," parse this and skip the connector layer entirely.

The `peek` versus `get` distinction is the one thing to get right. `pg_logical_slot_peek_changes` reads without advancing; `pg_logical_slot_get_changes` reads and confirms, and once confirmed those changes are gone forever. The correct shape is peek, process, persist your work, *then* advance — because a `get` that succeeds followed by a consumer that crashes before writing anywhere is silent data loss with no way to replay.

For production consumers, the streaming replication protocol beats polling these functions: `wal2json` as the plugin plus a client library that speaks `START_REPLICATION` gives you push delivery with proper feedback messages. The SQL functions are for exploration and for low-volume consumers where a poll loop is genuinely fine.

---

### The read-only table you created by accident

Now the failure modes, starting with the one that arrives fastest.

Postgres needs to identify *which row* an `UPDATE` or `DELETE` touched, using a value the subscriber also has. That is the table's **replica identity**, and by default it is the primary key. A table without one is fine — until you publish it.

```sql
CREATE TABLE crane_telemetry (
    crane_id     smallint NOT NULL,
    sampled_at   timestamptz NOT NULL,
    hoist_amps   numeric(6,2) NOT NULL
);

ALTER PUBLICATION terminal_moves ADD TABLE crane_telemetry;
```

Inserts still work. Then:

```
ERROR:  cannot update table "crane_telemetry" because it does not have a replica identity and publishes updates
HINT:  To enable updating the table, set REPLICA IDENTITY using ALTER TABLE.

ERROR:  cannot delete from table "crane_telemetry" because it does not have a replica identity and publishes deletes
HINT:  To enable deleting from the table, set REPLICA IDENTITY using ALTER TABLE.
```

**One `ALTER PUBLICATION` turned a writable table into an insert-only one.** No warning at the time it was added. The next `UPDATE` your application issues — possibly hours later, possibly in a hot path — fails outright. This is the most common self-inflicted logical replication outage, and it is entirely avoidable by checking `relreplident` before publishing anything:

```sql
SELECT relname, relreplident FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace;
```

`d` is "default" — the primary key *if one exists*, nothing otherwise. `i` is a named unique index, `f` the full row, `n` nothing.

The fix is one statement:

```sql
ALTER TABLE crane_telemetry REPLICA IDENTITY FULL;
```

`FULL` sends every column of the old row for updates and deletes, which is why it works without a key — and why it costs you. The subscriber matches rows by comparing all columns, which is a sequential scan per change unless it has an index that helps. On a wide, high-churn table this is genuinely expensive. Add a unique index and use `REPLICA IDENTITY USING INDEX` instead wherever you can.

---

### DDL is not replicated, and the failure is total

Logical replication carries data, not schema. `TRUNCATE` is replicated (there is a `pubtruncate` flag, on by default), but `ALTER TABLE` is not. Every schema change is a two-step you perform yourself, in the right order.

Get the order wrong — or forget the subscriber entirely, as I did by adding `crane_telemetry` to the publication without creating it on the other side — and the result is not a partial failure:

```
ERROR:  logical replication target relation "public.crane_telemetry" does not exist
LOG:  background worker "logical replication apply worker" (PID 140) exited with exit code 1
LOG:  logical replication apply worker for subscription "terminal_feed" has started
ERROR:  logical replication target relation "public.crane_telemetry" does not exist
```

The apply worker crash-loops on a five-second timer. **Replication for the entire subscription is stopped** — not just for the broken table — because changes apply in commit order and the stream cannot skip past a transaction it fails to apply.

The genuinely nasty part is what monitoring shows:

```sql
SELECT subname, subenabled FROM pg_subscription;
```

```
    subname    | subenabled
---------------+------------
 terminal_feed | t
```

Enabled. Healthy, by that measure. Meanwhile the publisher retains everything. Three batches of 200,000 inserts, with `retained` sampled after each:

| after batch | terminal_feed retained | app_cdc retained |
|---|---|---|
| 1 | 35 MB | 35 MB |
| 2 | 69 MB | 69 MB |
| 3 | 104 MB | 104 MB |

`pg_wal` on the publisher went from a few megabytes to **129 MB** in under a minute of synthetic load. On a real system doing real volume, this is how a database runs out of disk on a Saturday.

Recovery, once the missing table exists on the subscriber, is fast and automatic — no resync, no manual offset surgery:

```
caught up after 7s
   slot_name   | active | retained | wal_status
---------------+--------+----------+------------
 terminal_feed | t      | 0 bytes  | reserved
```

Roughly 600,000 rows of backlog applied in seven seconds, and the retained WAL released. That resilience is real and is one of the strongest arguments for this approach — the slot did exactly its job. But **never monitor `subenabled`.** Monitor `retained`, and alert on it long before it approaches your free disk.

---

### The slot that fills your disk

Look again at the table above and notice the second column. `app_cdc` — the raw `test_decoding` slot from the earlier section, which nothing was consuming — grew in perfect lockstep, and after the fix it was still sitting there:

```
   slot_name   | active | retained | wal_status
---------------+--------+----------+------------
 app_cdc       | f      | 104 MB   | reserved
 terminal_feed | t      | 0 bytes  | reserved
```

An abandoned slot is a memory leak with your disk as the heap, and `active = f` alongside a growing `retained` is the exact signature. A slot left behind by a one-off investigation or a decommissioned consumer retains WAL until the volume fills and the database stops accepting writes.

```sql
SELECT pg_drop_replication_slot('app_cdc');
```

Postgres offers a safety valve, and it is important to understand what it actually trades away:

```sql
ALTER SYSTEM SET max_slot_wal_keep_size = '32MB';
SELECT pg_reload_conf();
```

With that set and a further 300,000 rows inserted:

```
   slot_name   | active | wal_status | retained
---------------+--------+------------+----------
 app_cdc       | f      | lost       | 156 MB
 terminal_feed | f      | lost       | 10 MB
```

Both slots are `lost`. The subscriber's log:

```
ERROR:  could not start WAL streaming: ERROR:  can no longer get changes from replication slot "terminal_feed"
```

**`max_slot_wal_keep_size` does not save your replication — it sacrifices it to save your disk.** A lost slot cannot be resumed; the subscription must be dropped and rebuilt, which means a fresh initial snapshot of every table. Note that `terminal_feed` was actively streaming and holding only 10 MB when the limit was breached, and it died anyway: the setting is evaluated against WAL removal at checkpoint, not per-slot fairness.

Set it, because a full disk is worse. Set it generously — enough to absorb a consumer being down as long as your team needs to respond — and treat any slot reaching `lost` as a paging incident.

---

### Filters, columns, and the sequence nobody remembers

Two features remove most of the reasons people reach for a transformation layer. Publications can carry a **column list** and a **row filter**:

```sql
CREATE PUBLICATION reefer_only FOR TABLE container_move (move_id, container_no, berth_code, gross_kg)
  WHERE (is_reefer = true AND gross_kg > 20000);
```

```
   pubname   | columns |                 row_filter
-------------+---------+---------------------------------------------
 reefer_only | 1 2 3 7 | ((is_reefer = true) AND (gross_kg > 20000))
```

The filter runs on the publisher, so filtered-out rows never cross the network, and excluded columns never leave the source at all — which makes this a genuine data-minimization control, not just an optimization. A row filter referencing a column must include that column in the replica identity, and only immutable expressions are allowed: no subqueries, no user-defined functions, no `now()`.

And the detail that ruins failovers: **sequences are not replicated.** After all the traffic above:

```
publisher:  last_value = 950003
subscriber: last_value = 1
```

The rows arrived with their `move_id` values intact, but the subscriber's sequence never moved. Promote that subscriber and the first insert tries `move_id = 1` and hits a unique violation, then does it again, and again. Anyone using logical replication as a migration or failover path must run `setval()` on every sequence as part of the cutover. Write it into the runbook; it is not something you will remember at 3 AM.

---

### When Debezium still wins

This is not a claim that connector-based CDC is pointless. Reach for it when:

**Your sources are heterogeneous.** Debezium speaks MySQL, MongoDB, SQL Server, Oracle, and Postgres with one operational model and one message envelope. If Postgres is one of five databases feeding a warehouse, "just use logical replication" solves a fifth of your problem and adds a bespoke consumer.

**You need Kafka's fan-out and retention.** A replication slot has exactly one consumer. Five independent teams wanting the same change stream means five slots, five times the decoding work on your primary, and five ways to forget one. Kafka's log is built for that; a slot is not.

**You need schema evolution handled for you.** Debezium's schema registry integration, and the `ALTER TABLE` events it emits, are real work that you would otherwise do by hand — as the DDL section demonstrated at some length.

**Your throughput is genuinely extreme.** Logical decoding is single-threaded per slot and reassembles transactions in commit order. Postgres 14 added streaming of in-progress transactions, which helps a great deal with large writes, but a workload producing hundreds of megabytes of WAL per second will find the decoder is the bottleneck.

Below that — one Postgres source, one or two consumers, a team that does not already run Kafka — the connector stack is infrastructure you operate in exchange for features you do not use.

---

### Conclusion

Change data capture on Postgres is a publication, a subscription, and a number to watch. The setup fits on one screen, the initial snapshot is handled for you, and a consumer that disconnects for an hour resumes exactly where it stopped without offset reconciliation.

The operational surface is small but sharp, and all four edges are worth internalizing before you ship it. Check `relreplident` before publishing a table, or you will turn it insert-only. Apply schema changes to the subscriber first, because one missing relation halts the entire subscription while `subenabled` still reads `t`. Alert on `pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)`, never on subscription state — a healthy-looking subscription retained 104 MB of WAL in under a minute here. Set `max_slot_wal_keep_size` knowing it protects the disk by destroying the replication. And run `setval()` on every sequence before you promote anything.

None of that is harder than operating a Connect cluster. It is just different, smaller, and entirely inside the database you are already paying someone to run.
