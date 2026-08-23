# Your Multi-Tenant WHERE Clause Is One Typo From a Data Breach

#### Row-Level Security moves tenant isolation into the database, where forgetting it stops being possible — with the four bypasses and the 77x performance trap nobody warns you about

**By Tihomir Manushev**

*Aug 23, 2026 · 11 min read*

---

Run this against your multi-tenant codebase right now:

```bash
grep -rn "FROM charge_session" --include="*.py" --include="*.go" src/ | grep -v "operator_id"
```

Every line it prints is a query that returns another customer's data. Not "could" — does. The only thing standing between your tenants and each other is that a developer remembered to type six words, in every query, forever, including the one written at 6 PM on a Friday to debug a support ticket.

That is not a security model. It is a habit. Habits have a failure rate.

PostgreSQL has had Row-Level Security since 9.5, and it moves the guarantee from the application into the table definition: the tenant predicate becomes part of the table, and there is no SQL a connected application can write that escapes it. This article builds a working multi-tenant setup on Postgres 17, then spends most of its length on the parts that go wrong — the four roles that still see everything, the policy shape that turns a 1 ms query into a 93 ms sequential scan, and what happens when you put PgBouncer in front of it.

All numbers below come from a Postgres 17.6 container on a Ryzen 5 3600 (12 threads, 31 GB RAM), against a 2-million-row table spread across 200 tenants.

---

### The schema

An EV charging network platform: each tenant is a **network operator** running stations, and every plug-in produces a session row.

```sql
CREATE TABLE operator (
    operator_id   bigint PRIMARY KEY,
    display_name  text NOT NULL,
    country_code  char(2) NOT NULL
);

CREATE TABLE charge_session (
    session_id      bigserial PRIMARY KEY,
    operator_id     bigint NOT NULL REFERENCES operator,
    station_code    text NOT NULL,
    connector_no    smallint NOT NULL,
    began_at        timestamptz NOT NULL,
    ended_at        timestamptz,
    kwh_delivered   numeric(8,3) NOT NULL,
    settled_cents   integer NOT NULL,
    driver_token    text NOT NULL
);
```

Two million sessions across 200 operators, ten thousand each, spanning three months:

```sql
INSERT INTO operator
SELECT g,
       'Operator ' || to_char(g, 'FM000'),
       (ARRAY['BG','DE','NL','PL','SE'])[1 + (g % 5)]
FROM generate_series(1, 200) AS g;

INSERT INTO charge_session
    (operator_id, station_code, connector_no, began_at, ended_at,
     kwh_delivered, settled_cents, driver_token)
SELECT 1 + (n % 200),
       'ST-' || to_char(1 + (n % 4000), 'FM0000'),
       1 + (n % 4),
       timestamptz '2026-01-01 00:00:00+00' + (n % 200000) * interval '3 minutes',
       timestamptz '2026-01-01 00:00:00+00' + (n % 200000) * interval '3 minutes'
           + interval '41 minutes',
       round((7 + (n % 620) / 10.0)::numeric, 3),
       120 + (n % 8800),
       md5(n::text)
FROM generate_series(1, 2000000) AS n;

CREATE INDEX charge_session_operator_began_idx
    ON charge_session (operator_id, began_at DESC);

VACUUM ANALYZE charge_session;
```

That index leads with `operator_id`, which matters more than it looks like it does. Hold that thought until the performance section.

---

### One policy replaces every WHERE clause

The application connects as a dedicated role that owns nothing:

```sql
CREATE ROLE portal_app LOGIN PASSWORD 'demo';
GRANT SELECT, INSERT, UPDATE, DELETE ON charge_session TO portal_app;
GRANT USAGE, SELECT ON SEQUENCE charge_session_session_id_seq TO portal_app;
```

Now switch the table on and attach the rule:

```sql
ALTER TABLE charge_session ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON charge_session
    USING       (operator_id = current_setting('app.operator_id')::bigint)
    WITH CHECK  (operator_id = current_setting('app.operator_id')::bigint);
```

`USING` filters rows the statement can *see* — it applies to `SELECT`, `UPDATE`, and `DELETE`. `WITH CHECK` validates rows the statement wants to *write* — `INSERT` and the post-image of `UPDATE`. You need both. A `USING`-only policy lets a tenant read only their own rows and then hand one to a competitor with an `UPDATE`.

`current_setting('app.operator_id')` reads a session variable. Any name with a dot works; Postgres treats the prefix as a namespace and does not validate it. Your connection setup writes it once per request:

```sql
SET app.operator_id = '42';
```

That is the whole mechanism. Here is what the application role can now do, connecting fresh with nothing set:

```
lab=> SELECT count(*) FROM charge_session;
ERROR:  unrecognized configuration parameter "app.operator_id"
```

**This error is a feature.** The tempting alternative is `current_setting('app.operator_id', true)`, whose second argument suppresses the error and returns NULL when unset. The policy then evaluates to NULL, which is not true, so the query returns zero rows — and zero rows looks exactly like "this tenant has no sessions yet." A support engineer chases that for an hour. A hard error names the bug in one line. Use the strict form and let unset context be a crash.

With the setting in place, tenant 42 sees its ten thousand rows and no others:

```
lab=> SET app.operator_id = '42';
lab=> SELECT count(*) FROM charge_session;
 count
-------
 10000
```

Writes are sealed in both directions. Inserting on behalf of operator 77 while identified as 42:

```
ERROR:  new row violates row-level security policy for table "charge_session"
```

Moving an existing row to another tenant hits the same wall:

```
lab=> UPDATE charge_session SET operator_id = 77
lab->  WHERE session_id = (SELECT min(session_id) FROM charge_session);
ERROR:  new row violates row-level security policy for table "charge_session"
```

And a delete aimed at someone else's data quietly matches nothing, because those rows do not exist as far as this session is concerned:

```
lab=> DELETE FROM charge_session WHERE operator_id = 77;
DELETE 0
```

Note what did *not* happen: no application code changed. No query in the codebase gained a `WHERE` clause. The grep at the top of this article now returns lines that are safe.

---

### Four roles that still see all two million rows

This is where teams ship the breach they were trying to prevent, because "RLS is enabled" and "RLS applies" are different statements.

**The table owner is exempt by default.** Not by accident — Postgres assumes the owner is doing maintenance. With the table owned by a non-superuser `schema_owner` and RLS enabled:

```
lab=> SELECT count(*) FROM charge_session;
  count
---------
 2000000
```

The policy is attached, active, and completely ignored. Fixing it takes one statement:

```sql
ALTER TABLE charge_session FORCE ROW LEVEL SECURITY;
```

```
lab=> SET app.operator_id = '42';
lab=> SELECT count(*) FROM charge_session;
 count
-------
 10000
```

This matters far beyond a psql session. Your migration tool connects as the owner. Your nightly export script probably does too. Anything running as the owner without `FORCE` operates on the whole table while the code around it looks tenant-scoped.

**A superuser bypasses everything, including FORCE.** With `FORCE ROW LEVEL SECURITY` still on, the `postgres` role:

```
lab=> SELECT count(*) FROM charge_session;
  count
---------
 2000000
```

No setting will change this. Superusers are not subject to RLS, full stop. If your ORM's connection string ends in `postgres:postgres@`, you have written a policy and gained nothing.

**`BYPASSRLS` does what it says.** A reporting role created with that attribute:

```sql
CREATE ROLE reporting LOGIN BYPASSRLS;
GRANT SELECT ON charge_session TO reporting;
```

```
lab=> SELECT count(*) FROM charge_session;
  count
---------
 2000000
```

This is legitimately useful — cross-tenant analytics, billing reconciliation, the dashboard your finance team needs. Grant it deliberately to a role that cannot log in from the application network, and audit the list with `SELECT rolname FROM pg_roles WHERE rolbypassrls;` on a schedule.

**A table with RLS on and no policy denies everything.** That is the safe default, and it will page you. Enable RLS in the same migration that creates the policy, never one deploy earlier.

The rule that follows from all four: **the role your application connects as must not own the tables it queries.** Owner, superuser, and `BYPASSRLS` are three separate escape hatches, and the application role should hold none of them.

---

### The planner treats the policy as a real predicate

The common assumption is that RLS is a post-filter — Postgres fetches rows, then throws away the ones you cannot see. If that were true it would be unusable at scale. It is not what happens.

A dashboard query for one tenant's recent sessions, run by `portal_app` with no `operator_id` written anywhere in the SQL:

```sql
SET app.operator_id = '42';
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)
SELECT station_code, kwh_delivered, began_at
FROM charge_session
WHERE began_at >= '2026-03-01' AND began_at < '2026-03-08'
ORDER BY began_at DESC
LIMIT 20;
```

```
 Limit (actual time=0.037..0.147 rows=20 loops=1)
   Buffers: shared hit=10 read=13
   ->  Index Scan using charge_session_operator_began_idx on charge_session
         Index Cond: ((operator_id = (current_setting('app.operator_id'::text))::bigint)
                  AND (began_at >= '2026-03-01 00:00:00+00'::timestamptz)
                  AND (began_at < '2026-03-08 00:00:00+00'::timestamptz))
 Planning Time: 0.357 ms
 Execution Time: 0.175 ms
```

The policy predicate is an **Index Cond**, sitting alongside the application's own date range in the same index scan. Postgres rewrote the query to include the policy and then planned the whole thing together. That is why the leading `operator_id` column in the index earns its place: the policy is the query's most selective predicate on every single request, so the index that serves it should start there.

For comparison, the same query written by hand with `WHERE operator_id = 42` and no RLS produces an identical plan shape — 26 buffers against 23, 0.106 ms against 0.175 ms. Same access path, same work.

There is a second, subtler protection in play. Postgres evaluates policy predicates *before* other qualifiers unless it can prove the other qualifiers are leakproof. A function that reports what it sees, priced absurdly cheaply so the planner would love to run it first:

```sql
CREATE FUNCTION peek(t text) RETURNS boolean AS $$
BEGIN RAISE NOTICE 'saw token %', t; RETURN false; END $$
LANGUAGE plpgsql COST 0.0000001;
```

Running `SELECT count(*) FROM charge_session WHERE peek(driver_token);` as the tenant emits exactly **10,000 notices** — its own rows, not 2,000,000. The plan shows why:

```
 Bitmap Heap Scan on charge_session
   Recheck Cond: (operator_id = (current_setting('app.operator_id'::text))::bigint)
   Filter: peek(driver_token)
```

The policy became the index condition; the non-leakproof function was pinned above it as a `Filter` and never saw a row it should not have. Postgres will not reorder a possibly-leaky qualifier past a security barrier, no matter how cheap you claim it is.

---

### The policy shape that seq-scans your entire table

Now the failure that actually costs you. Real systems rarely have one tenant per session — a user belongs to several operators, so the obvious policy queries a membership table:

```sql
CREATE TABLE operator_member (
    member_id    bigint NOT NULL,
    operator_id  bigint NOT NULL REFERENCES operator,
    PRIMARY KEY (member_id, operator_id)
);

CREATE POLICY tenant_isolation ON charge_session
    USING (operator_id IN (SELECT om.operator_id FROM operator_member om
                            WHERE om.member_id = current_setting('app.member_id')::bigint));
```

Correct, readable, and it destroys the query. A monthly kWh aggregate for one tenant:

```
 Finalize Aggregate (actual time=86.545..92.489 rows=1 loops=1)
   Buffers: shared hit=13044 read=17737
   ->  Gather (Workers Launched: 2)
         ->  Parallel Seq Scan on charge_session (actual time=1.295..84.118 rows=247 loops=3)
               Filter: ((ANY (operator_id = (hashed SubPlan 1).col1))
                    AND (began_at >= '2026-03-01'::timestamptz)
                    AND (began_at < '2026-04-01'::timestamptz))
               Rows Removed by Filter: 666420
 Execution Time: 92.589 ms
```

**Two million rows scanned to return 740.** The subplan itself is cheap — it runs three times and hits eleven buffers — but the planner cannot convert `operator_id = ANY (hashed subplan)` into an index condition. So the predicate lands as a post-scan filter, the index goes unused, and Postgres burns two parallel workers reading 30,781 buffers off a 303 MB table.

The scalar policy from earlier, same query, same data:

```
 Bitmap Heap Scan on charge_session
   Recheck Cond: ((operator_id = (current_setting('app.operator_id'::text))::bigint) AND ...)
   Buffers: shared hit=744
 Execution Time: 1.202 ms
```

1.20 ms against 92.59 ms — **77x**, and 744 buffers against 30,781. The policy did not change what was returned. It changed whether the index was reachable.

The fix keeps multi-tenant membership and gets the index back: return the tenant list as an **array** from a `STABLE` function, so the planner sees a constant-per-query value it can push into a scalar array operation.

```sql
CREATE FUNCTION visible_operators() RETURNS bigint[]
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT coalesce(array_agg(om.operator_id), '{}')
    FROM operator_member om
    WHERE om.member_id = current_setting('app.member_id')::bigint
$$;

CREATE POLICY tenant_isolation ON charge_session
    USING      (operator_id = ANY (visible_operators()))
    WITH CHECK (operator_id = ANY (visible_operators()));
```

```
 Bitmap Heap Scan on charge_session
   Recheck Cond: ((operator_id = ANY (visible_operators())) AND ...)
   ->  Bitmap Index Scan on charge_session_operator_began_idx
         Index Cond: ((operator_id = ANY (visible_operators())) AND ...)
 Execution Time: 1.491 ms
```

Back to 1.49 ms and an index condition. `STABLE` is the load-bearing keyword — it promises the result will not change within a statement, which is what lets Postgres evaluate the function once and treat the array as a constant. Mark it `VOLATILE` and you are back to a per-row call. `SECURITY DEFINER` lets the function read the membership table without granting tenants direct access to it.

The general shape to aim for: **a policy predicate should be an equality or an array containment against something the planner can resolve to a value before the scan starts.** Anything that reaches into another table mid-predicate will cost you the index.

---

### Connection poolers will hand tenant 42's context to tenant 7

RLS depends on session state, and a transaction-pooling PgBouncer exists specifically to give your session state to somebody else. Two behaviours decide whether this works.

Plain `SET` survives the transaction that issued it:

```
lab=> SET app.operator_id = '42';
lab=> BEGIN; SET app.operator_id = '13'; COMMIT;
lab=> SELECT DISTINCT operator_id FROM charge_session;
 operator_id
-------------
          13
```

Under transaction pooling, that connection returns to the pool still identified as operator 13, and the next request to grab it — a different customer — starts authenticated as somebody else until it overwrites the value. If it forgets, or if it fails between checkout and `SET`, it reads another tenant's data with a valid policy in place.

`SET LOCAL` reverts at commit:

```
lab=> SET app.operator_id = '42';
lab=> BEGIN;
lab->   SET LOCAL app.operator_id = '99';
lab->   SELECT DISTINCT operator_id FROM charge_session;   -- 99
lab-> COMMIT;
lab=> SELECT DISTINCT operator_id FROM charge_session;     -- 42
```

**Use `SET LOCAL`, always, and set it as the first statement inside the same transaction as the query.** Not on connection checkout — inside the transaction. That is the only scope a transaction pooler cannot shuffle.

One thing you do *not* have to worry about: prepared statements. After six executions Postgres switches to a generic plan, and there is a real question of whether the tenant gets baked in. It does not:

```
lab=> SET app.operator_id = '42';
lab=> PREPARE visible_tenant AS SELECT DISTINCT operator_id FROM charge_session;
lab=> EXECUTE visible_tenant;   -- 42  (x6, including after the generic plan kicks in)
lab=> SET app.operator_id = '7';
lab=> EXECUTE visible_tenant;
 operator_id
-------------
           7
```

`current_setting()` stays a runtime call in the cached plan, so the seventh execution reads the new value. Your ORM's statement cache is not a leak.

---

### What it actually costs

The honest question is what you pay for moving the predicate into the database. Two pgbench runs, 8 clients, 4 threads, 30 seconds each, on the hardware named at the top. Both compute a monthly aggregate for a randomly chosen tenant. Run A goes through the policy and includes the `SET LOCAL` round trip. Run B is a `BYPASSRLS` role writing the `WHERE` clause by hand.

| | transactions | latency avg | tps |
|---|---|---|---|
| A — RLS policy + `SET LOCAL` | 257,579 | 0.932 ms | **8,587** |
| B — explicit `WHERE`, no RLS | 274,174 | 0.875 ms | **9,140** |

About **6% throughput**, 57 microseconds of latency — and that includes the extra statement per transaction, which is most of the gap. There is no per-row cost, because there is no per-row work: the policy became part of the index condition.

Six percent to make an entire class of bug unreachable is not a difficult trade. What *is* expensive is the wrong policy shape, and that costs 7,600% rather than 6%.

---

### When to leave it alone

RLS is a poor fit for a few real cases. **Schema-per-tenant or database-per-tenant** setups already have isolation at a coarser, stronger boundary; adding RLS inside them buys nothing. **Bulk ETL** runs faster and simpler through a `BYPASSRLS` role than through a policy evaluated on every one of a hundred million rows. **Column-level secrets** are not RLS's job — it filters rows, so hiding `driver_token` from a support role means a view or `GRANT`/`REVOKE` on the column. And if your isolation rule genuinely cannot be expressed as an indexable predicate — arbitrary hierarchy walks, permissions computed from three tables — you will fight the planner constantly, and enforcing it in a well-reviewed data-access layer may be the more honest engineering.

The one deployment mistake worth naming: turning RLS on across an existing production schema in a single migration. Do it table by table, `FORCE` included, verifying the plan for your top queries at each step. A policy that silently drops an index is a performance incident that arrives hours later, under load, and looks nothing like the change that caused it.

---

### Conclusion

Row-Level Security converts tenant isolation from something every developer must remember into something the table enforces. The mechanism is small — one `CREATE POLICY`, one session variable, `SET LOCAL` inside each transaction — and the runtime cost measured about 6%.

The work is in the surrounding details. Give the application a role that owns nothing and holds no `BYPASSRLS`, because owner and superuser both walk straight past your policy. Add `FORCE ROW LEVEL SECURITY` so your migration tool does not quietly operate on every tenant at once. Use the strict `current_setting()` so missing context throws instead of returning an empty result that looks like real data. And check `EXPLAIN` after writing a policy the same way you would after writing a query — the difference between a scalar predicate and a subquery predicate was 1.2 ms against 92.6 ms on the same rows, and nothing in the SQL you wrote will tell you which one you got.
