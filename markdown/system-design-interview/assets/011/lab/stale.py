"""Trap 1: place an order on the primary, read it straight back from the replica.

    python3 stale.py idle 20     # 16 customers, nothing else running
    python3 stale.py busy 20     # same, while a bulk import writes to the primary

A read is stale when the replica says the order does not exist. For each stale
read we keep polling the replica every 0.5 ms to see how long it took to appear.
"""
import sys
import threading
import time

from common import PRIMARY, REPLICA, LagSampler, connect, med, pct

CUSTOMERS = 16


def place_order(conn, customer_id: int) -> int:
    """The write: one INSERT, committed on the primary."""
    row = conn.execute(
        "INSERT INTO orders (customer_id, total_cents) VALUES (%s, %s)"
        " RETURNING id", (customer_id, 4_250)).fetchone()

    return row[0]


def find_order(conn, order_id: int):
    """The read: the order page, served by the replica."""
    return conn.execute(
        "SELECT status, total_cents FROM orders WHERE id = %s",
        (order_id,)).fetchone()


def customer(cid: int, until: float, out: dict) -> None:
    prim, rep = connect(PRIMARY), connect(REPLICA)

    while time.monotonic() < until:
        order_id = place_order(prim, cid)
        committed = time.monotonic()
        out["reads"] += 1

        if find_order(rep, order_id) is None:
            out["stale"] += 1

            while find_order(rep, order_id) is None:
                time.sleep(0.0005)

            out["delays"].append((time.monotonic() - committed) * 1000)

        time.sleep(0.005)


def bulk_import(until: float) -> None:
    """A nightly-style import: 50,000-row batches into another table."""
    conn = connect(PRIMARY)
    batch = 0

    while time.monotonic() < until:
        conn.execute(
            "INSERT INTO import_rows SELECT g, 'SKU-' || g,"
            " repeat(md5(g::text), 8) FROM generate_series(1, 50000) g")
        batch += 1

    conn.execute("TRUNCATE import_rows")
    print(f"bulk import: {batch} batches of 50,000 rows")


def main() -> None:
    mode, seconds = sys.argv[1], float(sys.argv[2])
    t0 = time.monotonic()
    until = t0 + seconds
    sampler = LagSampler(t0)
    sampler.start()
    stats = [{"reads": 0, "stale": 0, "delays": []} for _ in range(CUSTOMERS)]
    threads = [threading.Thread(target=customer, args=(i + 1, until, stats[i]))
               for i in range(CUSTOMERS)]

    if mode == "busy":
        threads.append(threading.Thread(target=bulk_import, args=(until,)))

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    sampler.stop.set()
    reads = sum(s["reads"] for s in stats)
    stale = sum(s["stale"] for s in stats)
    delays = [d for s in stats for d in s["delays"]]
    lag_kb = [b / 1024 for _, b, _ in sampler.samples]
    print(f"{mode}: {CUSTOMERS} customers, {seconds:.0f} s, {reads:,} orders"
          f" placed and read back")
    print(f"  stale reads (order not found on replica): {stale:,}"
          f" ({stale / reads:.1%})")
    print(f"  time until it appeared: p50 {med(delays):.2f} ms,"
          f" p99 {pct(delays, 99):.2f} ms, max {max(delays, default=0):.2f} ms")
    print(f"  replica behind, sampled every 100 ms: p50 {med(lag_kb):.0f} KB,"
          f" max {max(lag_kb):.0f} KB")


if __name__ == "__main__":
    main()
