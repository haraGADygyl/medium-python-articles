# Rate Limiting in PostgreSQL: Token Bucket and Sliding Window in Pure SQL

#### An atomic upsert that can't be raced, two classic algorithms in a few lines each, and an honest look at the write cost you're signing up for

**By Tihomir Manushev**

*Jul 17, 2026 · 10 min read*

---

Rate limiting is the reflexive reason teams add Redis to a stack that didn't have it. The logic is trivial — count requests, reject past a threshold — but it has to be *fast* and it has to be *correct under concurrency*, and the folklore says a relational database is the wrong place for both. So a second datastore appears, with its own client library, its own failure modes, and its own thing to keep alive at 3 AM.

The correctness half of that problem has a clean answer in Postgres, and it hinges on one insight: a rate-limit check is a read-modify-write, and if you do it as a literal `SELECT` then `UPDATE`, two concurrent requests both read "one slot left" and both pass. The fix is not a lock you manage by hand — it's making the whole check a single atomic statement, which `INSERT ... ON CONFLICT` does natively.

This article builds two rate limiters in pure SQL for an API gateway — a token bucket and a sliding window — proves the token bucket admits exactly one request under a concurrent stampede, and then measures the real cost so you know precisely when to reach for Redis anyway. Everything runs on Postgres 16, and every number below is measured.

---

### The Race You Must Avoid

Picture the obvious implementation. A row holds a client's remaining allowance. On each request you read it, check it, and write back:

```sql
-- DO NOT DO THIS: two statements, one race.
SELECT tokens FROM rate_buckets WHERE client_key = 'api-key-77';  -- app sees 1
UPDATE rate_buckets SET tokens = tokens - 1 WHERE client_key = 'api-key-77';
```

Under any real load this is broken. Two requests arrive together, both run the `SELECT`, both see one token, both conclude "allowed," and both run the `UPDATE` — the counter goes to -1 and you admitted twice your limit. Wrapping it in a transaction at the default `READ COMMITTED` isolation does not save you, because both transactions read the same committed value before either writes. You could reach for `SELECT ... FOR UPDATE` to lock the row, or an advisory lock, but there's a simpler path: never split the read from the write. Compute the decision and the new state in one statement the database executes atomically.

---

### Token Bucket in One Atomic Statement

The **token bucket** is the algorithm worth reaching for first, because it allows controlled bursts. A bucket holds up to `burst` tokens and refills at `rate` tokens per second; each request consumes one. A client who's been quiet has a full bucket and can spike; a client hammering the API drains it and gets throttled to the steady refill rate. The elegant trick is **lazy refill**: you don't run a background job topping up buckets, you compute the refill on read from the elapsed time since the bucket was last touched.

```sql
CREATE TABLE rate_buckets (
    client_key text PRIMARY KEY,
    tokens     double precision NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE FUNCTION take_token(p_key text, p_rate double precision, p_burst double precision)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE affected int;
BEGIN
    INSERT INTO rate_buckets AS b (client_key, tokens, updated_at)
    VALUES (p_key, p_burst - 1, now())
    ON CONFLICT (client_key) DO UPDATE
        SET tokens = LEAST(p_burst,
                           b.tokens + extract(epoch FROM now() - b.updated_at) * p_rate) - 1,
            updated_at = now()
        WHERE LEAST(p_burst,
                    b.tokens + extract(epoch FROM now() - b.updated_at) * p_rate) >= 1;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END; $$;
```

Read the `ON CONFLICT` clause as the whole algorithm compressed into one expression. `extract(epoch FROM now() - b.updated_at) * p_rate` is how many tokens accrued since the last request; `LEAST(p_burst, ...)` caps the refill at the bucket's capacity; subtracting one consumes the request's token. The `WHERE` guard is the accept/reject decision — the update only happens if the refilled bucket actually has a token to give. If it doesn't, no row is touched, `ROW_COUNT` is zero, and the function returns `false`. A brand-new key skips straight to the `INSERT`, starting with `burst - 1` tokens and returning `true`.

Firing eight rapid requests at a bucket of five, refilling one per second, does exactly what the model promises:

```sql
SELECT n AS request, take_token('api-key-77', 1, 5) AS allowed
FROM generate_series(1, 8) n;
```

```
 request | allowed
---------+---------
       1 | t
       2 | t
       3 | t
       4 | t
       5 | t
       6 | f
       7 | f
       8 | f
```

Five allowed, three rejected, bucket empty. Wait three seconds and the lazy refill hands back three tokens — the next five requests split three allowed, two denied — without any background process having run. The refill happened arithmetically, the instant the sixth request read the row.

---

### Proving It's Atomic

The claim that this can't be raced deserves evidence, not assertion. `INSERT ... ON CONFLICT DO UPDATE` takes a row-level lock on the conflicting row, so concurrent calls for the *same* key serialize: the second waits for the first to commit, then sees the already-decremented token count. To test it, I gave a fresh key a burst of one and fired twelve simultaneous requests at it:

```
 results across 12 concurrent requests (t=allowed, f=denied):
    1 t
   11 f
```

Exactly one request won; the other eleven were correctly denied. There is no interleaving of a stale read and a late write, because there is no separate read — the decision and the mutation are the same statement, and the row lock makes the twelve of them take turns. This is the entire reason to prefer the atomic upsert over the tempting `SELECT`-then-`UPDATE`: correctness under concurrency is a property of the structure, not something you bolt on with careful locking.

---

### The Simpler Cousin: Fixed-Window Counter

Sometimes you don't need bursts — just "no more than N requests per minute." A **fixed-window counter** is the smallest correct implementation: bucket time into fixed windows, count hits per window, reject past the limit. `date_bin` snaps `now()` to the current window's start, and the same atomic-upsert pattern caps the counter:

```sql
CREATE TABLE window_counters (
    client_key   text,
    window_start timestamptz,
    hits         int NOT NULL,
    PRIMARY KEY (client_key, window_start)
);

CREATE FUNCTION allow_fixed(p_key text, p_limit int, p_window interval)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE affected int;
        w timestamptz := date_bin(p_window, now(), 'epoch');
BEGIN
    INSERT INTO window_counters AS c (client_key, window_start, hits)
    VALUES (p_key, w, 1)
    ON CONFLICT (client_key, window_start) DO UPDATE
        SET hits = c.hits + 1
        WHERE c.hits < p_limit;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END; $$;
```

With a limit of three per ten-second window, five requests give three allowed and two denied, and the same row-lock atomicity holds under concurrency. It's simpler than the token bucket and needs no floating-point refill math — but it has a well-known flaw. Because windows reset abruptly, a client can send the full limit in the last instant of one window and the full limit in the first instant of the next, landing *twice* the limit inside a span shorter than a single window. If that boundary burst matters to you, you need a sliding window.

---

### Sliding Window for Accuracy

A **sliding-window log** removes the boundary artifact by counting the actual requests in the trailing interval, not in a fixed bucket. It stores a row per request and counts those newer than `now() - window`. The catch: counting and then inserting are two operations, which reintroduces the very race we escaped — so here we *do* serialize per key, with a transaction-scoped advisory lock:

```sql
CREATE TABLE request_log (
    client_key text,
    hit_at     timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ON request_log (client_key, hit_at);

CREATE FUNCTION allow_sliding(p_key text, p_limit int, p_window interval)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE cnt int;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext('rl:' || p_key));
    SELECT count(*) INTO cnt FROM request_log
    WHERE client_key = p_key AND hit_at > now() - p_window;
    IF cnt >= p_limit THEN RETURN false; END IF;
    INSERT INTO request_log (client_key) VALUES (p_key);
    RETURN true;
END; $$;
```

The `pg_advisory_xact_lock` keyed on the client makes the count-then-insert indivisible for that client while leaving other clients unblocked. With a limit of four per sixty seconds, six requests give four allowed and two denied — exactly, with no boundary doubling. The cost is real, though: this table gains a row on every single allowed request, so it needs an aggressive retention policy — delete rows older than the window on a schedule, or partition by time and drop old partitions — or it grows without bound. Accuracy here is paid for in storage and cleanup.

---

### The Cost Nobody Mentions

Here is the part the "just use Postgres" posts skip. Every one of these checks is a **write**, and writes are not free. I ran 100,000 token-bucket checks spread across 100 keys:

```
 allowed
---------
  100000
Time: 16125.308 ms
```

That's roughly 161 microseconds per check, about 6,200 checks per second on a single connection — and this was server-side, with no network round-trip, no per-request commit. In a real deployment each check is its own transaction that commits (a WAL flush) across a network hop, so per-connection throughput is lower still. Worse, every check updated a row, and in Postgres every update writes a new tuple version:

```
 updates | dead_rows | hot_pct
---------+-----------+---------
   99914 |     99901 |    26.9
```

Nearly 100,000 dead tuples from 100,000 checks, and only 27% of updates qualified as HOT (heap-only, which avoid touching indexes). A hot rate-limit table bloats fast and leans hard on autovacuum. Three tunings make this workload survivable: set a lower `fillfactor` on the table so more updates can go HOT in-page, tune autovacuum to run aggressively on it, and — because rate-limit state is disposable — consider `synchronous_commit = off`, trading durability you don't need for throughput you do. None of this makes Postgres as fast as an in-memory counter; it makes the write cost *manageable*.

---

### When Redis Still Wins

Redis exists for exactly this shape of workload, and it is genuinely better at it. Its counters live in RAM, so a rate-limit check is an in-memory increment measured in single-digit microseconds and throughput in the millions per second — two to three orders of magnitude past what a row update on a durable, MVCC table will give you. It has no vacuum, no tuple bloat, and no WAL. It offers native key expiry, so windows clean themselves up instead of needing a retention job, and purpose-built atomic primitives (`INCR`, Lua scripts) for exactly this pattern. At high request volumes against hot keys, none of the Postgres tuning above closes that gap.

So the honest dividing line is about scale and coupling, not capability. Use Postgres when your request rates are in the thousands per second rather than the hundreds of thousands, when you'd rather not operate a second datastore for one feature, or — the real differentiator — when the rate-limit decision must be **transactionally consistent with other writes**. If admitting a request also debits a quota, records usage for billing, and inserts an audit row, doing all of it plus the limit check in one Postgres transaction gives you atomicity Redis simply cannot, because Redis isn't in that transaction. Reach for Redis when the limiter is a high-volume front door standing on its own, and its speed and built-in expiry are the whole game.

---

### Conclusion

A rate limiter is a read-modify-write under contention, and Postgres handles the contention natively the moment you stop splitting the read from the write. `INSERT ... ON CONFLICT` gives you a token bucket or a fixed-window counter that admits exactly the right number of requests under a concurrent stampede — proven, not hoped — and an advisory lock extends the same guarantee to an exact sliding window when boundary bursts matter.

What it does not give you for free is Redis's speed. Every check is a durable write that generates a dead tuple, so budget for autovacuum, tune `fillfactor`, and lean on `synchronous_commit = off` for state you can afford to lose. Do that, and you can rate-limit thousands of requests a second inside the database you already run — and, uniquely, in the same transaction as the work being limited. When your front door needs to survive hundreds of thousands of requests a second, that's when the second datastore finally earns its keep.
