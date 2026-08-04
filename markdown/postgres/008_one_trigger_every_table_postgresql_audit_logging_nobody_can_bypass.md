# One Trigger, Every Table: PostgreSQL Audit Logging Nobody Can Bypass

#### A single generic function records who changed what, when, and why across your entire schema — no per-table boilerplate, no application code.

**By Tihomir Manushev**

*Aug 4, 2026 · 9 min read*

---

The carrier's lawyer says you agreed to $3.10 per mile. Your `carrier_contracts` table says $3.42. Somebody changed it in March, and nobody can say who.

Your application has audit logging. It also has a nightly reconciliation job that connects with the same credentials and writes directly, a data-fix script somebody ran from a laptop last quarter, and an ops engineer with `psql` access. Application-level auditing records what the application did. It is blind to everything else that holds a connection string, which is precisely the set of changes you most need explained.

Postgres closes that gap, because a trigger fires on the write itself. It does not care whether the `UPDATE` arrived from your ORM, a migration tool, or somebody's terminal at 2 AM. What follows builds that system: one generic trigger function serving every table regardless of its columns, storing a JSONB diff attributed to a human with a reason attached. Then the parts nobody writes about — keeping the log append-only against your own database role, reconciling permanent history with the right to erasure, and what it all costs on the write path, measured rather than guessed.

Everything here runs on PostgreSQL 16 or later, with no extensions. Benchmarks come from 18.0.

---

### One Function, Any Table

The usual mistake is one audit trigger per table: mirror the columns into a history table, write a function naming each one, repeat for the next table. Every schema migration now touches two places, or the audit silently drifts out of sync with the reality it describes.

The fix is to stop naming columns at all. Postgres exposes `to_jsonb(NEW)` and `to_jsonb(OLD)`, which convert the row record into a JSONB object with no advance knowledge of its shape. A function built on that works for any table you attach it to.

Start with the target tables. A freight brokerage tracks carrier contracts and driver records — different shapes, different sensitivity:

```sql
CREATE TABLE carrier_contracts (
    contract_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    carrier_name     text NOT NULL,
    lane_origin      text NOT NULL,
    lane_destination text NOT NULL,
    rate_per_mile    numeric(8, 2) NOT NULL,
    status           text NOT NULL DEFAULT 'draft',
    effective_on     date NOT NULL
);

CREATE TABLE driver_profiles (
    driver_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name       text NOT NULL,
    mobile_number   text NOT NULL,
    license_state   char(2) NOT NULL,
    hazmat_endorsed boolean NOT NULL DEFAULT false
);
```

One log receives changes from both. It is partitioned by month from the start, because an audit log is the table most likely to outgrow its usefulness, and retroactively partitioning a billion-row table is a bad weekend:

```sql
CREATE TABLE change_log (
    entry_id    bigint GENERATED ALWAYS AS IDENTITY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    table_name  text NOT NULL,
    row_key     text NOT NULL,
    operation   char(1) NOT NULL,
    actor       text NOT NULL,
    reason      text,
    delta       jsonb NOT NULL,
    PRIMARY KEY (entry_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE change_log_2026_08 PARTITION OF change_log
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE change_log_2026_09 PARTITION OF change_log
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

CREATE INDEX change_log_row_idx ON change_log (table_name, row_key, occurred_at DESC);
```

Note `clock_timestamp()` rather than `now()`. Inside a transaction `now()` returns the transaction start time, so a thousand rows updated in one statement would share a single timestamp. `clock_timestamp()` advances on every call and preserves the true ordering of writes within a transaction.

The primary key includes `occurred_at` because Postgres requires the partition key to participate in any unique constraint on a partitioned table. `row_key` is `text` rather than `bigint` deliberately: it has to hold the primary key of any table you point this at, including composite or UUID keys.

---

### Recording the Diff, Not the Row

Here is the function that serves every table:

```sql
CREATE OR REPLACE FUNCTION record_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    key_column text   := TG_ARGV[0];
    redacted   text[] := string_to_array(coalesce(TG_ARGV[1], ''), ',');
    before_row jsonb  := CASE WHEN TG_OP = 'INSERT' THEN '{}'::jsonb ELSE to_jsonb(OLD) END;
    after_row  jsonb  := CASE WHEN TG_OP = 'DELETE' THEN '{}'::jsonb ELSE to_jsonb(NEW) END;
    delta      jsonb;
BEGIN
    SELECT coalesce(jsonb_object_agg(k, jsonb_build_object(
               'from', CASE WHEN k = ANY (redacted) AND before_row ? k
                            THEN to_jsonb('***'::text) ELSE before_row -> k END,
               'to',   CASE WHEN k = ANY (redacted) AND after_row ? k
                            THEN to_jsonb('***'::text) ELSE after_row -> k END
           )), '{}'::jsonb)
      INTO delta
      FROM (SELECT jsonb_object_keys(before_row || after_row) AS k) touched
     WHERE before_row -> k IS DISTINCT FROM after_row -> k;

    INSERT INTO change_log (table_name, row_key, operation, actor, reason, delta)
    VALUES (TG_TABLE_NAME,
            coalesce(after_row ->> key_column, before_row ->> key_column),
            left(TG_OP, 1),
            coalesce(nullif(current_setting('audit.actor', true), ''), session_user),
            nullif(current_setting('audit.reason', true), ''),
            delta);
    RETURN NULL;
END;
$$;
```

The function takes its configuration from `TG_ARGV`, the arguments supplied when the trigger is created. The first is the name of the primary key column, so the function knows which value identifies the row. The second is an optional comma-separated list of columns whose values must never reach the log.

The diff itself is the `SELECT`. `before_row || after_row` merges both versions, and `jsonb_object_keys` over that merge yields every column name appearing in either — which matters for `INSERT` and `DELETE`, where one side is an empty object. The `WHERE` clause then keeps only the keys whose values actually differ, using `IS DISTINCT FROM` so that a change to or from `NULL` counts as a change rather than evaluating to `NULL` and vanishing. What survives is aggregated into one object mapping each changed column to its `from` and `to` values.

`RETURN NULL` is correct here and does not discard anything, because this is an `AFTER` trigger — the row is already written and the return value is ignored. Attach it to both tables:

```sql
CREATE TRIGGER log_contract_changes AFTER INSERT OR UPDATE OR DELETE ON carrier_contracts
    FOR EACH ROW EXECUTE FUNCTION record_change('contract_id');

CREATE TRIGGER log_driver_changes AFTER INSERT OR UPDATE OR DELETE ON driver_profiles
    FOR EACH ROW EXECUTE FUNCTION record_change('driver_id', 'full_name,mobile_number');
```

Two tables with nothing in common, one function, and the second one masks personal data on the way in. Adding a third table is one `CREATE TRIGGER` statement. Adding a column to an audited table requires no audit change at all — the next write picks it up.

---

### The Missing Half: Who, and Why

A diff tells you a rate moved from 3.10 to 3.42. It does not tell you that a broker renegotiated a fuel surcharge under ticket FRT-4471. Without that, you have a change log that proves something happened and explains nothing.

The obstacle is that the database does not know who your users are. Connection pooling means `current_user` is whatever service role the pool authenticated as — the same value for every request from every human. The trigger runs deep inside a statement with no access to your request context.

Custom configuration parameters bridge the gap. Postgres accepts any dotted setting name it does not recognize and stores it as a session variable, which `current_setting()` reads back. Set it with `SET LOCAL` and the value lives exactly as long as the transaction:

```sql
BEGIN;
SET LOCAL audit.actor  = 'r.okonkwo@northbound-logistics';
SET LOCAL audit.reason = 'fuel surcharge renegotiation, ticket FRT-4471';
UPDATE carrier_contracts SET rate_per_mile = 3.42 WHERE contract_id = 2;
COMMIT;
```

The resulting entry carries the full story:

```
 row_key | operation |             actor              |                    reason                     |                       delta
---------+-----------+--------------------------------+-----------------------------------------------+---------------------------------------------------
 2       | U         | r.okonkwo@northbound-logistics | fuel surcharge renegotiation, ticket FRT-4471 | {"rate_per_mile": {"to": 3.42, "from": 3.10}}
```

Two details will bite you here.

The first is that `SET LOCAL` cannot take a bind parameter. `SET LOCAL audit.actor = $1` is a syntax error, because `SET` is not a planned statement, and every database driver you own sends parameterized queries. The function `set_config(name, value, is_local)` is the equivalent that accepts parameters — the third argument `true` means transaction-local:

```python
import psycopg


def reprice_contract(dsn: str, contract_id: int, new_rate: str,
                     actor: str, reason: str) -> None:
    """Update a contract rate with the audit context attached."""
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute(
                "SELECT set_config('audit.actor', %s, true),"
                "       set_config('audit.reason', %s, true)",
                (actor, reason),
            )
            conn.execute(
                "UPDATE carrier_contracts SET rate_per_mile = %s WHERE contract_id = %s",
                (new_rate, contract_id),
            )


reprice_contract(
    "dbname=freightlab",
    contract_id=2,
    new_rate="3.42",
    actor="r.okonkwo@northbound-logistics",
    reason="fuel surcharge renegotiation, ticket FRT-4471",
)
```

Because the setting is transaction-local, it rolls back with the transaction and cannot leak into the next request that borrows the same pooled connection. Set it inside the transaction, never on checkout.

The second detail is subtler and is why the function wraps `current_setting` in `nullif`. Before any `SET LOCAL` has run in a session, `current_setting('audit.actor', true)` returns `NULL`. After a transaction that used it commits, the same call in the same session returns an *empty string* — the placeholder now exists and simply has no value:

```sql
-- run this on a brand-new connection
SELECT current_setting('audit.actor', true) IS NULL;   -- t
BEGIN;
SET LOCAL audit.actor = 'someone@example';
COMMIT;
SELECT current_setting('audit.actor', true) IS NULL;   -- f  (it is now '')
```

A plain `coalesce(current_setting('audit.actor', true), session_user)` therefore works perfectly on the first unattributed transaction of each connection and silently writes an empty actor on every one after it. On a pooled connection that is most of them. `nullif(..., '')` collapses both cases so the fallback to `session_user` actually fires.

---

### Making the Log Append-Only

An audit log that the audited application can rewrite is decoration. Two mechanisms close that, and they defend against different attackers.

Privileges handle the application. Grant it nothing on the log — not even `INSERT`:

```sql
CREATE ROLE dispatch_app LOGIN PASSWORD 'replace-me';
GRANT USAGE ON SCHEMA public TO dispatch_app;

GRANT SELECT, INSERT, UPDATE, DELETE ON carrier_contracts, driver_profiles TO dispatch_app;
GRANT SELECT ON change_log TO dispatch_app;

ALTER FUNCTION record_change() SECURITY DEFINER;
```

`SECURITY DEFINER` makes the trigger execute with the privileges of the function's owner rather than the caller's, so the log still receives its entries while `dispatch_app` cannot write to it directly. The application can neither forge an entry nor erase one:

```
ERROR:  permission denied for table change_log
```

Privileges do nothing against the table owner, though, and that is the role your migrations run as. A statement-level trigger covers it:

```sql
CREATE OR REPLACE FUNCTION reject_log_tampering() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('audit.erasure_warrant', true) = 'granted' THEN
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'change_log is append-only (attempted %)', TG_OP
        USING ERRCODE = 'insufficient_privilege',
              HINT = 'erasure requests must go through redact_subject()';
END;
$$;

CREATE TRIGGER change_log_is_append_only BEFORE UPDATE OR DELETE ON change_log
    FOR EACH STATEMENT EXECUTE FUNCTION reject_log_tampering();
```

Now `DELETE FROM change_log` fails for everyone, owner included. Be honest about the boundary: a superuser can drop the trigger, and anyone with filesystem access can do as they please. This stops mistakes and casual tampering, not a determined administrator. Genuine tamper-evidence needs the log shipped off the box — streamed to append-only storage or a separate cluster nobody's application credentials reach.

Retention works by dropping partitions rather than deleting rows, which is the other reason to partition. Detaching is a metadata operation and does not scan the table:

```sql
ALTER TABLE change_log DETACH PARTITION change_log_2026_08 CONCURRENTLY;
```

`DELETE`-based retention on an audit log is a bloat generator: it writes as much WAL as the inserts did, leaves dead tuples for autovacuum, and competes with the write path that is already paying for the trigger.

---

### The Right to Erasure

Append-only history and a legal obligation to delete personal data are in direct conflict, and the conflict is why so many audit projects stall.

The best answer is to never create the problem. That is what the second trigger argument does — `full_name` and `mobile_number` are masked at write time, so the log records *that* a driver's phone number changed without recording either value:

```
{"driver_id": {"to": 1, "from": null},
 "full_name": {"to": "***", "from": null},
 "mobile_number": {"to": "***", "from": null},
 "hazmat_endorsed": {"to": true, "from": null},
 "license_state": {"to": "MN", "from": null}}
```

You keep the evidence that matters for compliance — who touched the record, when, and which fields moved — while the log holds no personal data to erase. Masked columns that did not change are absent entirely, since the diff drops them before masking is considered.

For the cases where personal data did reach the log, the escape hatch is the GUC check in the tampering trigger, gated behind a function that only privileged roles may execute:

```sql
CREATE OR REPLACE FUNCTION redact_subject(subject_table text, subject_key text, ticket text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE redacted_rows bigint;
BEGIN
    SET LOCAL audit.erasure_warrant = 'granted';
    UPDATE change_log
       SET delta = jsonb_build_object('_redacted', jsonb_build_object(
                       'keys', (SELECT jsonb_agg(k) FROM jsonb_object_keys(delta) AS k),
                       'ticket', ticket, 'at', to_jsonb(clock_timestamp())))
     WHERE table_name = subject_table AND row_key = subject_key;
    GET DIAGNOSTICS redacted_rows = ROW_COUNT;
    RETURN redacted_rows;
END;
$$;

REVOKE EXECUTE ON FUNCTION redact_subject(text, text, text) FROM public;
```

It replaces the values while leaving a tombstone recording which columns existed and under which ticket they were erased:

```
{"_redacted": {"at": "2026-08-04T19:54:25.972831+00:00",
               "keys": ["driver_id", "full_name", "license_state",
                        "mobile_number", "hazmat_endorsed"],
               "ticket": "GDPR-ERASE-2026-0231"}}
```

The auditor sees that history existed and was lawfully removed, which is a far better position than either an unexplained gap or an illegal refusal to delete. One residue remains: `row_key` is still an identifier for a real person. Treat it as pseudonymous data, and if your regulator disagrees, hash it.

---

### What Auditing Actually Costs

Row-level triggers are not free, and the honest number is larger than most people expect. The following measurements come from PostgreSQL 18.0 in Docker on an AMD Ryzen 5 3600 (12 threads, 31 GB RAM) with default `shared_buffers` of 128 MB and `synchronous_commit = on`. Each run is a single `UPDATE` touching all 200,000 rows of `carrier_contracts`, median of three runs with `VACUUM FULL` and `ANALYZE` between them:

| Configuration | Time | Multiplier |
|---|---|---|
| No auditing | 893 ms | 1.0× |
| Trigger fires, empty function body | 1,062 ms | 1.19× |
| Full-row JSONB snapshot | 4,505 ms | 5.0× |
| JSONB delta, 1 of 7 columns changed | 9,377 ms | 10.5× |
| JSONB delta, 5 of 7 columns changed | 11,193 ms | 12.5× |

PostgreSQL 16.14 landed within a few percent of every one of those figures. The work is plpgsql execution, not I/O, so 18's asynchronous I/O has nothing to bite on.

Read the table carefully, because it says something more useful than "triggers are slow." Trigger dispatch itself costs 19% — nearly nothing. Writing a full-row snapshot costs 5×. Computing the diff costs 10.5×, roughly double the snapshot, and that gap is entirely `jsonb_object_keys` and the aggregate running once per row.

So the diff buys storage with CPU. Across those same 200,000 entries:

| | Heap | With indexes |
|---|---|---|
| JSONB delta, narrow change | 32 MB | 56 MB |
| Full-row snapshot | 58 MB | 80 MB |

Nearly half the heap, as long as changes are narrow. When five of seven columns move, the delta stores both old and new values for each and swells to 86 MB — worse than the snapshot, at 349 bytes per entry. The delta approach wins on the OLTP pattern of small, frequent, single-column updates and loses on bulk rewrites.

Reads are the easy part. Reconstructing one row's history hits the composite index and returns in well under a millisecond:

```
Index Scan using change_log_2026_08_table_name_row_key_occurred_at_idx
  Index Cond: ((table_name = 'carrier_contracts') AND (row_key = '84213'))
  Buffers: shared hit=4
Execution Time: 0.034 ms
```

Searching the diffs themselves needs a GIN index on the JSONB column:

```sql
CREATE INDEX change_log_delta_idx ON change_log USING gin (delta);
```

Which turns "every contract suspension, with who and why" into a bitmap scan — 2,061 matches out of 180,632 entries in 1.4 ms:

```
Bitmap Heap Scan on change_log_2026_08 (actual rows=2061.00 loops=1)
  Recheck Cond: (delta @> '{"status": {"to": "suspended"}}'::jsonb)
  Heap Blocks: exact=53
  ->  Bitmap Index Scan on change_log_2026_08_delta_idx (actual rows=2061.00)
Execution Time: 1.422 ms
```

That GIN index is not free either — it roughly doubles the log's footprint and adds its own insert cost. Build it when you actually query diffs by content; the composite btree alone answers "what happened to this row," which is the majority of audit questions.

**When to reach for something else.** A 10× write penalty is irrelevant on a table taking a few hundred changes a minute and disqualifying on one ingesting sensor telemetry. Above roughly a few thousand writes per second, move to logical decoding — Debezium or `wal2json` read changes from the WAL, off the write path, at near-zero cost to the transaction. The catch is precisely what this article is about: the WAL contains the data change and knows nothing about your actor or reason, so you buy throughput by giving up the context that made the audit worth having. Teams that need both usually write a marker row inside each transaction for the decoder to pick up. And if your requirement is "who ran what statement" rather than "how did this row change," `pgaudit` answers that question directly and this design is the wrong tool entirely.

---

### Conclusion

The value of database-level auditing is not that it is convenient — it is 10× slower on writes than not auditing, and no amount of tuning changes that. The value is that it cannot be bypassed. Every path into the database goes through the trigger, including the ones you forgot existed, which are the ones that generate the disputes.

Build it generically. One function driven by `to_jsonb` and `TG_ARGV` covers every table you have and every column you add later, so the audit cannot drift from the schema it describes. Push the actor and reason in through transaction-local settings, remembering that `SET LOCAL` needs `set_config` from application code and that `current_setting` returns an empty string rather than `NULL` once a session has used it. Take the privileges away from the application and put a statement-level guard in front of the owner. Mask personal data at write time so the erasure question resolves before a regulator ever asks it.

Then measure the write penalty against your actual traffic. If it fits, you have an audit trail that answers who and why. If it does not, you have a precise number to justify the move to logical decoding — which is a better position than discovering the cost in production.
