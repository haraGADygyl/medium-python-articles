"""Eight concurrent 60-cent debits against a 100-cent wallet, two designs."""

import threading

import psycopg

DSN = "postgresql://postgres:demo@127.0.0.1:5471/postgres"
WALLET, START, DEBIT, BUYERS = 900, 100, 60, 8


def reset() -> None:
    """Give the wallet 100 cents in both representations."""
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("DELETE FROM entry WHERE account_id = %s", (WALLET,))
        conn.execute("UPDATE account SET balance = %s WHERE id = %s",
                     (START, WALLET))
        conn.execute("INSERT INTO entry (account_id, amount) VALUES (%s, %s)",
                     (WALLET, START))


def debit_from_log(gate: threading.Barrier, wins: list[int]) -> None:
    """Check SUM(entries), then append the debit."""
    with psycopg.connect(DSN) as conn:
        gate.wait()
        (balance,) = conn.execute(
            "SELECT sum(amount) FROM entry WHERE account_id = %s", (WALLET,)
        ).fetchone()
        if balance >= DEBIT:
            conn.execute(
                "INSERT INTO entry (account_id, amount) VALUES (%s, %s)",
                (WALLET, -DEBIT),
            )
            wins.append(1)
        conn.commit()


def debit_column(gate: threading.Barrier, wins: list[int]) -> None:
    """One conditional UPDATE on the wallet row."""
    with psycopg.connect(DSN) as conn:
        gate.wait()
        cur = conn.execute(
            "UPDATE account SET balance = balance - %s "
            "WHERE id = %s AND balance >= %s",
            (DEBIT, WALLET, DEBIT),
        )
        if cur.rowcount == 1:
            conn.execute(
                "INSERT INTO entry (account_id, amount) VALUES (%s, %s)",
                (WALLET, -DEBIT),
            )
            wins.append(1)
        conn.commit()


for name, debit in (("SUM check, then append", debit_from_log),
                    ("conditional UPDATE   ", debit_column)):
    reset()
    gate, wins = threading.Barrier(BUYERS), []
    threads = [threading.Thread(target=debit, args=(gate, wins))
               for _ in range(BUYERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with psycopg.connect(DSN) as conn:
        (final,) = conn.execute(
            "SELECT sum(amount) FROM entry WHERE account_id = %s", (WALLET,)
        ).fetchone()
    print(f"{name}  debits accepted {len(wins)}/{BUYERS}  "
          f"balance {START} -> {final} cents")
