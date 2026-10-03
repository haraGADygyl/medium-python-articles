"""One idle-in-transaction session pins the watermark; watch the tail grow."""

import random
import statistics
import threading
import time

import psycopg

DSN = "postgresql://postgres:demo@127.0.0.1:5471/postgres"
FEE_ACCOUNT = 7
WRITERS = 32
STALL_AT, STALL_FOR, TOTAL = 5.0, 30.0, 45.0

CHECKPOINT = """
WITH prev AS (
    SELECT balance, below_xid, included FROM checkpoint
    WHERE account_id = %(acct)s ORDER BY seq DESC LIMIT 1
), mark AS (
    SELECT pg_snapshot_xmin(pg_current_snapshot()) AS below
), fresh AS (
    SELECT coalesce(sum(e.amount), 0) AS amount, count(*) AS n
    FROM entry e, prev, mark
    WHERE e.account_id = %(acct)s
      AND e.xid >= prev.below_xid AND e.xid < mark.below
)
INSERT INTO checkpoint (account_id, seq, balance, below_xid, included)
SELECT %(acct)s, %(seq)s, prev.balance + fresh.amount, mark.below,
       prev.included + fresh.n
FROM prev, mark, fresh
"""

READ = """
SELECT c.balance + coalesce(sum(e.amount), 0), count(e.id)
FROM (SELECT * FROM checkpoint WHERE account_id = %(acct)s
      ORDER BY seq DESC LIMIT 1) c
LEFT JOIN entry e ON e.account_id = c.account_id AND e.xid >= c.below_xid
GROUP BY c.balance
"""

stop = threading.Event()


def writer(seed: int) -> None:
    """Same payment-shaped credit as race.py."""
    rng = random.Random(seed)
    with psycopg.connect(DSN) as conn:
        while not stop.is_set():
            conn.execute(
                "INSERT INTO entry (account_id, amount) VALUES (%s, %s)",
                (FEE_ACCOUNT, rng.randint(1, 100)),
            )
            conn.execute(
                "UPDATE account SET balance = balance - 1 WHERE id = %s",
                (rng.randint(1, 1_000_000),),
            )
            conn.commit()


def checkpointer() -> None:
    """Advance the watermark checkpoint every 50 ms."""
    seq = 1
    with psycopg.connect(DSN) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        while not stop.is_set():
            time.sleep(0.05)
            conn.execute(CHECKPOINT, {"acct": FEE_ACCOUNT, "seq": seq})
            conn.commit()
            seq += 1


def forgotten_transaction() -> None:
    """Write one row elsewhere, then sit idle inside the transaction."""
    time.sleep(STALL_AT)
    with psycopg.connect(DSN) as conn:
        conn.execute("UPDATE account SET balance = balance WHERE id = 42")
        time.sleep(STALL_FOR)
        conn.commit()


with psycopg.connect(DSN, autocommit=True) as admin:
    admin.execute("DELETE FROM entry WHERE account_id = %s", (FEE_ACCOUNT,))
    admin.execute("DELETE FROM checkpoint WHERE account_id = %s",
                  (FEE_ACCOUNT,))
    admin.execute("INSERT INTO checkpoint VALUES (%s, 0, 0, 0, '0'::xid8, 0)",
                  (FEE_ACCOUNT,))

workers = [threading.Thread(target=writer, args=(n,)) for n in range(WRITERS)]
workers += [threading.Thread(target=checkpointer),
            threading.Thread(target=forgotten_transaction)]
for worker in workers:
    worker.start()

print(f"{'t s':>5} {'tail entries':>13} {'read p50 ms':>12}")
started = time.perf_counter()
with psycopg.connect(DSN, autocommit=True) as reader:
    next_report = 0.0
    while (elapsed := time.perf_counter() - started) < TOTAL:
        timings, tail = [], 0
        for _ in range(9):
            t0 = time.perf_counter()
            _, tail = reader.execute(READ, {"acct": FEE_ACCOUNT}).fetchone()
            timings.append((time.perf_counter() - t0) * 1000)
        if elapsed >= next_report:
            print(f"{elapsed:5.0f} {tail:13d} {statistics.median(timings):12.2f}")
            next_report += 5
        time.sleep(0.2)
stop.set()
for worker in workers:
    worker.join()
