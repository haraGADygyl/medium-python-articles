# PostgreSQL Table Bloat: 24 MB of Data in a 557 MB File

#### Autovacuum was running, dead tuples were zero, and the table was still 23x the size of its own data

**By Tihomir Manushev**

*Sep 9, 2026 · 9 min read*

---

The disk alert fires. One table is 557 MB. You count the rows, multiply by the row width, and get 24 MB. Nothing was deleted, the row count never changed, and `pg_stat_user_tables` reports zero dead tuples with autovacuum having run twice in the last minute.

Everything is working correctly. That is what makes bloat hard to reason about: it is the price of MVCC, not a malfunction, and the tools meant to clean it up did their job and left the file exactly where it was.

Everything below ran on PostgreSQL 17.6 in Docker on a Ryzen 5 3600, `shared_buffers = 512MB`, `maintenance_work_mem = 256MB`, `autovacuum_naptime = 10s`.

---

### The workload that does it

An EV charging network. Every active connector pings its session with a state update roughly every thirty seconds — kilowatt-hours delivered, battery percentage, a timestamp. Nothing is inserted, nothing is deleted. The same rows are updated, over and over, for the length of a charge.

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

CREATE TABLE charge_session (
    session_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connector_id   integer      NOT NULL,
    driver_tag     text         NOT NULL,
    started_at     timestamptz  NOT NULL,
    last_ping_at   timestamptz  NOT NULL,
    state          text         NOT NULL,
    soc_pct        smallint     NOT NULL,
    kwh_delivered  numeric(9,3) NOT NULL
);

CREATE INDEX charge_session_connector_idx
    ON charge_session (connector_id, started_at DESC);
```

Three hundred thousand sessions, then twenty rounds of telemetry across all of them — six million updates, no inserts, no deletes:

```sql
DO $$
BEGIN
  FOR round IN 1..20 LOOP
    UPDATE charge_session
       SET kwh_delivered = kwh_delivered + 0.42,
           soc_pct       = LEAST(100, soc_pct + 2),
           last_ping_at  = clock_timestamp()
     WHERE state = 'charging';
  END LOOP;
END $$;
```

An `UPDATE` in Postgres does not overwrite a row. It writes a **new version** of the row and marks the old one as no longer visible to transactions that start later. Six million updates therefore write six million row versions into the file, and the 300,000 you can still see are the last one of each.

---

### Measuring it, not guessing

`pg_relation_size` tells you how much disk the table occupies. It cannot tell you how much of that is live data. The `pgstattuple` extension opens the relation and counts:

```sql
SELECT pg_size_pretty(table_len)          AS file_size,
       tuple_count,
       pg_size_pretty(tuple_len)          AS live_data,
       round(tuple_percent::numeric, 2)   AS live_pct,
       dead_tuple_count,
       pg_size_pretty(free_space)         AS reusable_free,
       round(free_percent::numeric, 2)    AS free_pct
  FROM pgstattuple('charge_session');
```

```
 file_size | tuple_count | live_data | live_pct | dead_tuple_count | reusable_free | free_pct
-----------+-------------+-----------+----------+------------------+---------------+----------
 557 MB    |      300000 | 24 MB     |     4.26 |                0 | 528 MB        |    94.88
```

The table started at 24 MB and ended at 557 MB with the same 300,000 rows. **4.26% of the file is data.** Dead tuples are zero — autovacuum genuinely cleaned up — and 528 MB is free space inside the file.

The indexes went along for the ride. The primary key grew from a few megabytes to 58 MB and the connector index to 56 MB, because every non-HOT update writes a new index entry too:

```sql
SELECT round(avg_leaf_density::numeric, 1) AS leaf_density_pct, leaf_pages
  FROM pgstatindex('charge_session_connector_idx');
```

```
 leaf_density_pct | leaf_pages
------------------+------------
              5.0 |       7100
```

Five percent leaf density means an index scan reads twenty pages to get the useful content of one. Bloat is not only a disk-space problem — it is a cache-hit-ratio problem, because those mostly-empty pages occupy `shared_buffers` just as fully as dense ones.

---

### Vacuum reclaims space for reuse, not for you

Here is the mechanic that surprises people. `VACUUM` marks dead tuples' space as available **inside the file**, so future writes can use it. It does not hand the space back to the filesystem, except for entirely empty pages at the very end of the relation.

So the file grows to its high-water mark and stays there. If the workload is steady that is arguably correct — the space gets reused rather than re-requested from the OS. It becomes a problem when the high-water mark was set by an event that will not recur.

Autovacuum's default trigger explains how the mark got so high:

```sql
SELECT current_setting('autovacuum_vacuum_scale_factor') AS scale_factor,
       current_setting('autovacuum_vacuum_threshold')    AS threshold;
```

It waits for `threshold + scale_factor * live_rows` dead tuples — with the defaults, 50 + 20% of the table. On 300,000 rows that is 60,050 dead tuples before autovacuum even starts, and each pass takes time during which the burst keeps writing. On a 50-million-row table it is ten million dead tuples, which is why the busiest tables in a system are exactly the ones where autovacuum looks like it has stopped working. Lower it per table, on the tables that need it:

```sql
ALTER TABLE charge_session SET (
    autovacuum_vacuum_scale_factor = 0.02,   -- 2% instead of 20%
    autovacuum_vacuum_threshold    = 1000,
    autovacuum_vacuum_cost_delay   = 2       -- let it work harder when it runs
);
```

---

### The failure that makes vacuum useless

Everything above assumes vacuum can remove dead tuples. It often cannot, and this is the version of the problem that produces a genuine incident.

A tuple can only be removed once no running transaction could still need to see it. Postgres tracks that boundary as the **xmin horizon**. One session that ran `BEGIN`, took a snapshot, and then went to lunch pins the horizon in place for the entire database.

I opened a repeatable-read transaction, left it idle, then ran five rounds of updates and vacuumed:

```sql
VACUUM (VERBOSE) horizon_demo;
```

```
tuples: 0 removed, 1800000 remain, 1500000 are dead but not yet removable
removable cutoff: 805, which was 5 XIDs old when operation ended
```

**Zero removed.** One and a half million dead tuples, `VACUUM` reported success, the table went from 24 MB to 157 MB, and `n_dead_tup` stayed at 1,500,000. Terminating the idle session and running the identical command:

```
tuples: 1500000 removed, 300000 remain, 0 are dead but not yet removable
```

The phrase to grep for in `VERBOSE` output is **"dead but not yet removable"**. When it is non-zero, tuning autovacuum is wasted effort — something is holding the horizon. Find it:

```sql
SELECT pid, state, age(backend_xmin) AS xmin_age,
       now() - xact_start AS open_for, left(query, 60) AS query
  FROM pg_stat_activity
 WHERE backend_xmin IS NOT NULL
 ORDER BY age(backend_xmin) DESC
 LIMIT 5;
```

Three things pin the horizon: long-running or idle-in-transaction sessions, abandoned replication slots, and unresolved prepared transactions. Check `pg_replication_slots` for slots with no consumer and `pg_prepared_xacts` for the third. A slot left behind by a decommissioned replica will hold the horizon and the WAL forever, which is how a bloat incident turns into a disk-full incident.

---

### fillfactor and HOT, actually measured

The standard advice is to lower `fillfactor` so updates fit on the same page as **HOT updates** — heap-only tuples, which skip writing new index entries entirely. I ran the identical six-million-update workload on a copy with `fillfactor = 70`:

| | heap | indexes | HOT updates |
|---|---|---|---|
| default (fillfactor 100) | 557 MB | 114 MB | 0 of 6,000,000 |
| fillfactor 70 | 565 MB | 86 MB | 1,795,462 (29.9%) |

The index saving is real — 25% smaller, because 1.8 million updates skipped index maintenance. The heap saving is **negative**: reserving 30% of every page made the starting table 35 MB instead of 24 MB, and the final file came out slightly larger.

The reason is that this burst outruns vacuum. Free space only reappears on a page after a vacuum pass, so after two or three rounds there is nowhere left for a HOT update to go. I reran both tables with a `VACUUM` between each round, which is what a workload spread over hours actually looks like:

| | heap (from) | indexes | HOT updates |
|---|---|---|---|
| fillfactor 100 | 53 MB (24 MB) | 18 MB | 0.0% |
| fillfactor 70 | 70 MB (35 MB) | 18 MB | **94.3%** |

`fillfactor` moved HOT from zero to 94.3%, exactly as advertised. But look at what actually changed the outcome: **557 MB became 53 MB — a 10x reduction — purely from vacuuming often enough.** Against that, `fillfactor` cost 17 MB and saved nothing on this workload.

That is the ordering worth remembering. Fix vacuum cadence first and measure; reach for `fillfactor` second, when `n_tup_hot_upd` is near zero and index write volume is the thing hurting you. And it only works at all if the updated columns are unindexed — put an index on `soc_pct` and HOT drops back to zero no matter what `fillfactor` says.

---

### Getting the space back

Once the file is oversized, only a rewrite shrinks it. Two options, both measured on the bloated table:

| | before | after | duration | blocks reads |
|---|---|---|---|---|
| `VACUUM FULL` | 557 MB + 114 MB idx | 27 MB + 9 MB | 749 ms | yes |
| `pg_repack` | 565 MB + 86 MB idx | 38 MB + 9 MB | 1,147 ms | no |

`VACUUM FULL` was fast here for a reason worth internalizing: it rewrites only the **live** data, and this table was 96% air. On a table that is genuinely large it is slow, and the whole time it holds an `ACCESS EXCLUSIVE` lock. I confirmed that on a 444 MB table of pure live data — a `SELECT` arriving one second in was killed by a three-second `statement_timeout` while `pg_locks` showed the lock granted, and the rewrite ran 6,401 ms. The same table under `pg_repack` served that `SELECT` normally and took 7,917 ms.

```bash
# Debian/Ubuntu, matching your server version
apt-get install -y postgresql-17-repack
```

```sql
CREATE EXTENSION IF NOT EXISTS pg_repack;
```

```bash
pg_repack -d grid --table charge_session
```

`pg_repack` builds a copy, keeps it in sync with triggers, and swaps it in behind a brief exclusive lock at the very end. The costs are honest ones: it needs room for a full second copy of the table plus its indexes, it requires the extension installed server-side, and the table must have a primary key or a unique non-partial index. That last requirement disqualifies more tables than people expect.

---

### Conclusion

Bloat is not a bug and autovacuum reporting zero dead tuples is not the all-clear. The number that matters is the ratio, and `pgstattuple` is the only thing that will tell you honestly:

```sql
SELECT relname,
       pg_size_pretty(pg_relation_size(relid)) AS size,
       round((pgstattuple(relid)).tuple_percent::numeric, 1) AS live_pct
  FROM pg_stat_user_tables
 WHERE pg_relation_size(relid) > 100 * 1024 * 1024
 ORDER BY pg_relation_size(relid) DESC
 LIMIT 20;
```

Run it on anything over 100 MB. It takes a full scan, so do it off-peak. Anything under 50% live is worth a conversation; anything at 4% is the conversation.

When you find one, resist the urge to schedule a weekly `VACUUM FULL` — that treats the symptom and takes an outage to do it. Check the horizon first, because a pinned xmin makes every other fix pointless. Then lower `autovacuum_vacuum_scale_factor` on the specific tables that churn, which is where the 10x lives. Rewrite once to reset the high-water mark, and only then argue about `fillfactor`.

Postgres is not hiding any of this. `pgstattuple`, `VACUUM VERBOSE` and `pg_stat_activity` each report exactly what is happening — they just will not volunteer it, and no alert fires until the disk does.
