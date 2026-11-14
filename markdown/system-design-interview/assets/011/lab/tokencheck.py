"""Which LSN goes in the token? Read back immediately and trust the check.

    python3 tokencheck.py early idle 20   # pg_current_wal_insert_lsn() inside the INSERT
    python3 tokencheck.py after idle 20   # pg_current_wal_lsn() after COMMIT
    python3 tokencheck.py early busy 20   # same, during the bulk import

"Trusted" reads are the ones where the replica said it had caught up; a trusted
read that cannot find the order is a bug in the token, not lag.
"""
import sys
import threading
import time

from common import PRIMARY, REPLICA, connect
from stale import bulk_import
from window import lsn_value

CUSTOMERS = 16


def customer(cid: int, kind: str, until: float, out: dict) -> None:
    prim, rep = connect(PRIMARY), connect(REPLICA)

    while time.monotonic() < until:
        if kind == "early":
            order_id, token = prim.execute(
                "INSERT INTO orders (customer_id, total_cents) VALUES (%s, %s)"
                " RETURNING id, pg_current_wal_insert_lsn()::text",
                (cid, 4_250)).fetchone()
        else:
            order_id = prim.execute(
                "INSERT INTO orders (customer_id, total_cents) VALUES (%s, %s)"
                " RETURNING id", (cid, 4_250)).fetchone()[0]
            token = prim.execute(
                "SELECT pg_current_wal_lsn()::text").fetchone()[0]

        while True:
            replayed = rep.execute(
                "SELECT pg_last_wal_replay_lsn()::text").fetchone()[0]

            if lsn_value(replayed) >= lsn_value(token):
                break

        row = rep.execute("SELECT 1 FROM orders WHERE id = %s",
                          (order_id,)).fetchone()
        out["trusted"] += 1
        out["missing"] += row is None


def main() -> None:
    kind, mode, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
    until = time.monotonic() + seconds
    stats = [{"trusted": 0, "missing": 0} for _ in range(CUSTOMERS)]
    threads = [threading.Thread(target=customer,
                                args=(i + 1, kind, until, stats[i]))
               for i in range(CUSTOMERS)]

    if mode == "busy":
        threads.append(threading.Thread(target=bulk_import, args=(until,)))

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    trusted = sum(s["trusted"] for s in stats)
    missing = sum(s["missing"] for s in stats)
    print(f"token {kind}, {mode}: {trusted:,} reads the replica said were"
          f" safe, {missing:,} could not find the order ({missing / trusted:.2%})")


if __name__ == "__main__":
    main()
