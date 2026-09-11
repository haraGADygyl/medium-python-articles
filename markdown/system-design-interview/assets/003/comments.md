# Reader comments — 003 Two Workers Hold the Same Lock

Not published. Read this before answering a follow-up so the reply stays
consistent with what was already said. Lab code and outputs: `lab/`.

---

## 1. "Just check the elapsed time before writing" — 2026-09-11

**Comment:**

> Can we set the key to Redis for 2.5 seconds, and in the application record the
> time from setting the key to Redis, and if more than 2 seconds have passed
> before writing to postgress, do not write anything to postgress? It seems more
> simple.

**What they mean:** a client-side deadline guard. TTL 2.5s, start a timer on
`SET`, and right before the Postgres write skip it if the timer is over 2s. The
0.5s is a safety margin so you never write after the lock could have expired.

**Why it does not close the hole:** the check and the write are two separate
steps, and a pause can land between them. The worker passes the check, freezes,
its lock expires, another worker takes over and writes, then the first worker
wakes and writes anyway. Same check-then-act gap as "raise the TTL" in the
article: it makes the window rarer, it does not remove it. Also: the write
itself can take time (row lock wait, pool, network retries), the local clock
must be monotonic, and the guard discards finished work even when nobody newer
exists.

**Lab:** `lab/lab_deadline.py`, same setup as the article (6 workers, 80 scenes
over 45s, 30% chance of a 2.2–3.4s `SIGSTOP`), TTL 2500ms, guard 2.0s, timer
started with `time.monotonic()` just before `SET`. Redis 7.4.11, Postgres 17.6.
Full output: `lab/output-deadline-guard.txt`.

| | stall during tiling | stall after the check passes | after the check + fencing |
|---|---|---|---|
| stalls | 31 | 31 | 30 |
| guard skipped the write | 31 | 0 | 0 |
| writes made without the lock | 0 | 31 | 30 |
| ... of those, accepted | 0 | 31 | 18 |
| rejected by the db | 0 | 0 | 12 |
| newer result overwritten | **0** | **11** | **0** |

- Stall during tiling (the case the reader pictured): the guard works.
- Stall after the check: the latest check passed at 1113 ms, 0.9s inside the margin, and still did not help.
- With fencing: 12 stale writes refused. The 18 accepted were correct, since those workers still held the newest token.
- The guard also threw away 3 finished jobs that nobody had replaced.
- Honest caveat: the stall was placed in that gap on purpose. In production a pause rarely lands exactly there.

**Reply posted:**

> Good instinct. I tested it on the same lab: TTL 2.5s, skip the write if more
> than 2s have passed. When the pause hits during tiling, it works: 31 stalls,
> 31 writes skipped, nothing corrupted. Then I moved the pause to just after the
> check passes and before the write. The guard skipped nothing, all 31 stale
> writes landed, and 11 of them overwrote a newer worker's result. The check had
> passed with 0.9s to spare, which doesn't help when the process then freezes
> for 3 seconds.
>
> The check and the write are two separate steps, and a pause can always land
> between them. A bigger margin makes that rarer but can't prevent it, the same
> way a bigger TTL can't. Fencing puts the check inside the write statement, so
> there's no gap. With the same stalls it rejected 12 stale writes and left 0
> corrupted scenes.

<!-- If the reply you actually posted differs, replace the block above with it. -->

**Likely follow-ups:**
- *"How often does a pause land in that gap in real life?"* Rarely, and I have not
  measured it in production. The point is that it is possible, and the corruption is
  silent when it happens.
- *"What if the database can't do a conditional write?"* See "What it costs" in
  the article: fencing needs the resource to compare the token in the same statement.
  Without that, there is no safe place for the check.
