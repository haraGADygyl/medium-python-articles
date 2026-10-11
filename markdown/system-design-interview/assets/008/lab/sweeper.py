"""Resolves checkouts left pending longer than STALE_S.

lookup : ask the provider whether a charge with this key exists, decide
          from that
redrive: send the same charge again with the same key, decide from its answer
"""
import os
import sys
import time

import psycopg

from checkout import finish_checkout
from common import charge, lookup, shop

STALE_S = float(os.environ.get("STALE_S", "2"))


def resolve_by_lookup(conn: psycopg.Connection, key: str,
                      amount: int, card: str) -> None:
    """Ask the provider what happened to this key, decide from the answer."""
    found = lookup(key)
    finish_checkout(conn, key, found or {"status": "not found"}, "sweeper")


def resolve_by_redrive(conn: psycopg.Connection, key: str,
                       amount: int, card: str) -> None:
    """Send the same charge again. The key makes it the same charge."""
    finish_checkout(conn, key, charge(key, amount, card), "sweeper")


if __name__ == "__main__":
    resolve = {"lookup": resolve_by_lookup,
               "redrive": resolve_by_redrive}[sys.argv[1]]
    stop = sys.argv[2]
    conn = shop()
    while not os.path.exists(stop):
        stale = conn.execute(
            "SELECT key, amount, card FROM checkout WHERE state = 'pending' "
            "AND created_at < clock_timestamp() - %s * interval '1 second' "
            "ORDER BY created_at LIMIT 100", (STALE_S,)).fetchall()
        for key, amount, card in stale:
            resolve(conn, key, amount, card)
        time.sleep(0.25)
