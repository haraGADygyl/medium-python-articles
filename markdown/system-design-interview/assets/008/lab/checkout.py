"""The two checkout handlers the article compares."""
import psycopg

from common import charge

RESERVE = ("UPDATE stock SET qty = qty - 1 "
           "WHERE sku = %s AND qty > 0 RETURNING qty")


class Declined(Exception):
    """The provider answered, and the answer was no."""


def checkout_in_transaction(conn: psycopg.Connection, key: str, sku: str,
                            amount: int, card: str) -> str:
    """The obvious answer: one transaction around stock, order and charge."""
    with conn.transaction():
        if conn.execute(RESERVE, (sku,)).fetchone() is None:
            return "sold out"
        conn.execute(
            "INSERT INTO orders (checkout_key, sku, amount) "
            "VALUES (%s, %s, %s)", (key, sku, amount))
        result = charge(key, amount, card)
        if result["status"] != "succeeded":
            raise Declined(key)               # rolls back stock and order
        conn.execute(
            "UPDATE orders SET charge_id = %s WHERE checkout_key = %s",
            (result["id"], key))
    return "completed"


def begin_checkout(conn: psycopg.Connection, key: str, sku: str,
                   amount: int, card: str) -> bool:
    """Step 1: commit the intent and the reservation before calling out."""
    with conn.transaction():
        if conn.execute(RESERVE, (sku,)).fetchone() is None:
            return False
        conn.execute(
            "INSERT INTO checkout (key, sku, amount, card, state) "
            "VALUES (%s, %s, %s, %s, 'pending')", (key, sku, amount, card))
    return True


def finish_checkout(conn: psycopg.Connection, key: str, result: dict,
                    by: str) -> bool:
    """Step 3: leave pending exactly once, for completed or failed."""
    with conn.transaction():
        if result["status"] == "succeeded":
            row = conn.execute(
                "UPDATE checkout SET state = 'completed', charge_id = %s, "
                "resolved_by = %s, resolved_at = clock_timestamp() "
                "WHERE key = %s AND state = 'pending' RETURNING sku, amount",
                (result["id"], by, key)).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO orders (checkout_key, sku, amount, "
                    "charge_id) VALUES (%s, %s, %s, %s)",
                    (key, row[0], row[1], result["id"]))
        else:
            row = conn.execute(
                "UPDATE checkout SET state = 'failed', resolved_by = %s, "
                "resolved_at = clock_timestamp() "
                "WHERE key = %s AND state = 'pending' RETURNING sku",
                (by, key)).fetchone()
            if row:                           # compensate: release the stock
                conn.execute(
                    "UPDATE stock SET qty = qty + 1 WHERE sku = %s",
                    (row[0],))
    return row is not None


def checkout_saga(conn: psycopg.Connection, key: str, sku: str,
                  amount: int, card: str) -> str:
    """Intent, then the charge under the checkout's key, then the outcome."""
    if not begin_checkout(conn, key, sku, amount, card):
        return "sold out"
    result = charge(key, amount, card)       # step 2
    if not finish_checkout(conn, key, result, "worker"):
        return "already resolved"
    return "completed" if result["status"] == "succeeded" else "declined"
