"""Time balance = SUM(entries) for accounts with growing history."""

import statistics
import time

import psycopg

DSN = "postgresql://postgres:demo@127.0.0.1:5471/postgres"
ACCOUNTS = {-1: "10,000", -2: "100,000", -3: "1,000,000", -4: "10,000,000"}
RUNS = 20

with psycopg.connect(DSN, autocommit=True) as conn:
    print(f"{'entries':>12} {'p50 ms':>9} {'p99 ms':>9}")
    for account_id, label in ACCOUNTS.items():
        timings = []
        for _ in range(RUNS + 2):
            started = time.perf_counter()
            conn.execute(
                "SELECT sum(amount) FROM entry WHERE account_id = %s",
                (account_id,),
            ).fetchone()
            timings.append((time.perf_counter() - started) * 1000)
        timings = sorted(timings[2:])
        p99 = timings[min(len(timings) - 1, int(len(timings) * 0.99))]
        print(f"{label:>12} {statistics.median(timings):9.2f} {p99:9.2f}")
    plan = conn.execute(
        "EXPLAIN (ANALYZE, BUFFERS, COSTS OFF) "
        "SELECT sum(amount) FROM entry WHERE account_id = -4"
    ).fetchall()
    print("\n".join(row[0] for row in plan))
