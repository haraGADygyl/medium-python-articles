"""Checkpointed balance under concurrent writers: max(id) boundary vs xid watermark."""

import os
import random
import sys
import threading
import time

import psycopg

DSN = "postgresql://postgres:demo@127.0.0.1:5471/postgres"
FEE_ACCOUNT = 7
MODE = sys.argv[1]                     # naive | watermark
WRITERS = int(os.environ.get("WRITERS", "32"))
DURATION = float(os.environ.get("DURATION", "30"))
EVERY_MS = float(os.environ.get("EVERY_MS", "50"))

NAIVE_CHECKPOINT = """
WITH prev AS (
    SELECT balance, upto_id, included FROM checkpoint
    WHERE account_id = %(acct)s ORDER BY seq DESC LIMIT 1
), fresh AS (
    SELECT max(e.id) AS upto, coalesce(sum(e.amount), 0) AS amount, count(*) AS n
    FROM entry e, prev
    WHERE e.account_id = %(acct)s AND e.id > prev.upto_id
)
INSERT INTO checkpoint (account_id, seq, balance, upto_id, included)
SELECT %(acct)s, %(seq)s, prev.balance + fresh.amount,
       coalesce(fresh.upto, prev.upto_id), prev.included + fresh.n
FROM prev, fresh
"""

WATERMARK_CHECKPOINT = """
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

NAIVE_READ = """
SELECT c.balance + coalesce(sum(e.amount), 0), c.included + count(e.id)
FROM (SELECT * FROM checkpoint WHERE account_id = %(acct)s
      ORDER BY seq DESC LIMIT 1) c
LEFT JOIN entry e ON e.account_id = c.account_id AND e.id > c.upto_id
GROUP BY c.balance, c.included
"""

WATERMARK_READ = """
SELECT c.balance + coalesce(sum(e.amount), 0), c.included + count(e.id)
FROM (SELECT * FROM checkpoint WHERE account_id = %(acct)s
      ORDER BY seq DESC LIMIT 1) c
LEFT JOIN entry e ON e.account_id = c.account_id AND e.xid >= c.below_xid
GROUP BY c.balance, c.included
"""

committed_amount = 0
committed_count = 0
tally = threading.Lock()
stop = threading.Event()


def writer(seed: int) -> None:
    """Credit the fee account inside a payment-shaped transaction."""
    global committed_amount, committed_count
    rng = random.Random(seed)
    with psycopg.connect(DSN) as conn:
        while not stop.is_set():
            amount = rng.randint(1, 100)
            wallet = rng.randint(1, 1_000_000)
            conn.execute(
                "INSERT INTO entry (account_id, amount) VALUES (%s, %s)",
                (FEE_ACCOUNT, amount),
            )
            conn.execute(
                "UPDATE account SET balance = balance - %s WHERE id = %s",
                (amount, wallet),
            )
            conn.commit()
            with tally:
                committed_amount += amount
                committed_count += 1


def checkpointer() -> int:
    """Roll the checkpoint forward every EVERY_MS until told to stop."""
    query = NAIVE_CHECKPOINT if MODE == "naive" else WATERMARK_CHECKPOINT
    seq = 1
    with psycopg.connect(DSN) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        while not stop.is_set():
            time.sleep(EVERY_MS / 1000)
            conn.execute(query, {"acct": FEE_ACCOUNT, "seq": seq})
            conn.commit()
            seq += 1
    return seq - 1


with psycopg.connect(DSN, autocommit=True) as admin:
    admin.execute("DELETE FROM entry WHERE account_id = %s", (FEE_ACCOUNT,))
    admin.execute("DELETE FROM checkpoint WHERE account_id = %s",
                  (FEE_ACCOUNT,))
    admin.execute(
        "INSERT INTO checkpoint VALUES (%s, 0, 0, 0, '0'::xid8, 0)",
        (FEE_ACCOUNT,),
    )

threads = [threading.Thread(target=writer, args=(n,)) for n in range(WRITERS)]
for thread in threads:
    thread.start()
result: list[int] = []
cp = threading.Thread(target=lambda: result.append(checkpointer()))
cp.start()
time.sleep(DURATION)
stop.set()
for thread in [*threads, cp]:
    thread.join()

with psycopg.connect(DSN, autocommit=True) as admin:
    read_sql = NAIVE_READ if MODE == "naive" else WATERMARK_READ
    balance, counted = admin.execute(read_sql, {"acct": FEE_ACCOUNT}).fetchone()
    truth, rows = admin.execute(
        "SELECT sum(amount), count(*) FROM entry WHERE account_id = %s",
        (FEE_ACCOUNT,),
    ).fetchone()

print(f"mode={MODE} writers={WRITERS} duration={DURATION:.0f}s "
      f"checkpoint every {EVERY_MS:.0f} ms, {result[0]} checkpoints")
print(f"committed by writers : {committed_count:>8} entries "
      f"{committed_amount:>10} cents")
print(f"SUM over the log     : {rows:>8} entries {truth:>10} cents")
print(f"checkpoint + tail    : {counted:>8} entries {balance:>10} cents")
print(f"lost                 : {rows - counted:>8} entries "
      f"{truth - balance:>10} cents")
