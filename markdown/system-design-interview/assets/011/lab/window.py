"""Trap 2 and the fixes: the same 60 s scene under different read routing.

    python3 window.py sticky         # primary for 2 s after your own write
    python3 window.py sticky 5       # primary for 5 s after your own write
    python3 window.py token          # LSN token taken after COMMIT
    python3 window.py token-early    # LSN token taken inside the INSERT (wrong)
    python3 window.py remote_apply   # commit waits for the replica to apply it
    python3 window.py sticky-feedback  # sticky, with hot_standby_feedback = on

The scene: 24 customers each place an order, then view it every 250 ms for 8 s,
then place the next one. 24 more customers browse old orders (no recent write).
At t=10 s a finance report opens a REPEATABLE READ transaction on the replica
and holds it (the slow part faked with pg_sleep). At t=12 s the cart cleanup job
deletes 100,000 abandoned carts on the primary and VACUUMs the table.
"""
import random
import sys
import threading
import time

import psycopg

from common import PRIMARY, REPLICA, LagSampler, connect, med, pct

WRITERS, BROWSERS = 24, 24
SECONDS, VIEW_FOR, VIEW_EVERY, STICKY = 60.0, 8.0, 0.25, 2.0
REPORT_AT, CLEANUP_AT = 10.0, 12.0
log: list[tuple[float, str, str, float]] = []  # (t, who, route, ms)
stale: list[tuple[float, float]] = []          # (t, seconds since the write)
commits: list[tuple[float, float]] = []        # (t, commit ms)
orders: list[tuple[float, bool, bool]] = []    # (t placed, seen, then gone)
events: list[str] = []
lock = threading.Lock()


def lsn_value(lsn: str) -> int:
    hi, lo = lsn.split("/")

    return (int(hi, 16) << 32) + int(lo, 16)


def place_order(conn, mode: str, customer_id: int) -> tuple[int, str | None]:
    """INSERT on the primary; return the id and, for token modes, the token."""
    if mode == "token-early":
        order_id, token = conn.execute(
            "INSERT INTO orders (customer_id, total_cents) VALUES (%s, %s)"
            " RETURNING id, pg_current_wal_insert_lsn()::text",
            (customer_id, 4_250)).fetchone()

        return order_id, token

    order_id = conn.execute(
        "INSERT INTO orders (customer_id, total_cents) VALUES (%s, %s)"
        " RETURNING id", (customer_id, 4_250)).fetchone()[0]

    if mode == "token":
        token = conn.execute("SELECT pg_current_wal_lsn()::text").fetchone()[0]

        return order_id, token

    return order_id, None


def replica_caught_up(rep, token: str) -> bool:
    """Has the replica replayed past this customer's last commit?"""
    replayed = rep.execute(
        "SELECT pg_last_wal_replay_lsn()::text").fetchone()[0]

    return lsn_value(replayed) >= lsn_value(token)


def choose(mode: str, rep, wrote_at: float | None, token: str | None) -> str:
    if mode.startswith("sticky"):
        recent = wrote_at is not None and time.monotonic() - wrote_at < STICKY

        return "primary" if recent else "replica"

    if mode.startswith("token") and token is not None:
        return "replica" if replica_caught_up(rep, token) else "primary"

    return "replica"


def read_order(conn, order_id: int):
    return conn.execute("SELECT status FROM orders WHERE id = %s",
                        (order_id,)).fetchone()


def writer(cid: int, mode: str, t0: float) -> None:
    prim, rep = connect(PRIMARY), connect(REPLICA)

    if mode == "remote_apply":
        prim.execute("SET synchronous_commit = remote_apply")

    time.sleep(random.uniform(0, VIEW_FOR))

    while time.monotonic() - t0 < SECONDS:
        started = time.monotonic()
        order_id, token = place_order(prim, mode, cid)
        wrote_at = time.monotonic()

        with lock:
            commits.append((wrote_at - t0, (wrote_at - started) * 1000))

        seen = vanished = False

        while time.monotonic() - wrote_at < VIEW_FOR:
            if time.monotonic() - t0 >= SECONDS:
                return

            begin = time.monotonic()
            route = choose(mode, rep, wrote_at, token)
            row = read_order(prim if route == "primary" else rep, order_id)
            now = time.monotonic()

            with lock:
                log.append((now - t0, "writer", route, (now - begin) * 1000))

                if row is None:
                    stale.append((now - t0, now - wrote_at))

            vanished = vanished or (seen and row is None)
            seen = seen or row is not None
            time.sleep(VIEW_EVERY)

        with lock:
            orders.append((wrote_at - t0, seen, vanished))


def browser(mode: str, t0: float) -> None:
    rep = connect(REPLICA)

    while time.monotonic() - t0 < SECONDS:
        begin = time.monotonic()
        read_order(rep, random.randint(1, 1_000_000))
        now = time.monotonic()

        with lock:
            log.append((now - t0, "browser", "replica", (now - begin) * 1000))

        time.sleep(VIEW_EVERY)


def report(t0: float) -> None:
    """A finance report on the replica that keeps its snapshot open."""
    time.sleep(REPORT_AT)
    conn = psycopg.connect(REPLICA)
    conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ

    try:
        rows = conn.execute(
            "SELECT date_trunc('month', created_at), sum(total_cents)"
            " FROM orders GROUP BY 1").fetchall()
        events.append(f"t={time.monotonic() - t0:5.1f} s  report: {len(rows)}"
                      " months summed, transaction held open")
        conn.execute("SELECT pg_sleep(90)")
        events.append(f"t={time.monotonic() - t0:5.1f} s  report finished")
    except psycopg.errors.Error as exc:
        first = str(exc).splitlines()[0]
        events.append(f"t={time.monotonic() - t0:5.1f} s  report cancelled:"
                      f" {first}")
    finally:
        conn.close()


def cleanup(t0: float) -> None:
    """Delete abandoned carts and VACUUM, as a cron job would."""
    time.sleep(CLEANUP_AT)
    conn = connect(PRIMARY)
    notes: list[str] = []
    conn.add_notice_handler(lambda d: notes.append(d.message_primary))
    gone = conn.execute("DELETE FROM carts WHERE updated_at < now()"
                        " - interval '1 hour'").rowcount
    conn.execute("VACUUM (VERBOSE) carts")
    events.append(f"t={time.monotonic() - t0:5.1f} s  cleanup: deleted"
                  f" {gone:,} abandoned carts, VACUUM done")

    for note in notes:
        if 'public.carts"' not in note:
            continue  # the TOAST table's report

        for line in note.split("\n"):
            if "tuples:" in line:
                events.append(f"t={time.monotonic() - t0:5.1f} s  vacuum"
                              f" {line.strip()}")


def prepare(mode: str) -> None:
    prim, rep = connect(PRIMARY), connect(REPLICA)
    feedback = "on" if mode == "sticky-feedback" else "off"
    rep.execute(f"ALTER SYSTEM SET hot_standby_feedback = {feedback}")
    rep.execute("SELECT pg_reload_conf()")
    names = "*" if mode == "remote_apply" else ""
    prim.execute(f"ALTER SYSTEM SET synchronous_standby_names = '{names}'")
    prim.execute("SELECT pg_reload_conf()")
    prim.execute("TRUNCATE carts")
    prim.execute(
        "INSERT INTO carts (customer_id, items, updated_at)"
        " SELECT g % 200000 + 1, jsonb_build_object('sku', g, 'qty', 1),"
        " now() - CASE WHEN g % 2 = 0 THEN interval '2 hours'"
        " ELSE interval '5 minutes' END FROM generate_series(1, 200000) g")
    prim.execute("VACUUM ANALYZE carts")
    head = prim.execute("SELECT pg_current_wal_lsn()::text").fetchone()[0]

    while not replica_caught_up(rep, head):
        time.sleep(0.05)

    time.sleep(1.0)


def timeline(samples: list[tuple[float, int, float]]) -> None:
    print("\n   t (s)  replica behind   writer reads  primary  stale"
          "  commit max ms  browser reads")

    for start in range(0, int(SECONDS), 4):
        end = start + 4
        in_bucket = [s for s in samples if start <= s[0] < end]
        behind = max((s[2] for s in in_bucket), default=0.0)
        wr = [x for x in log if start <= x[0] < end and x[1] == "writer"]
        to_primary = sum(1 for x in wr if x[2] == "primary")
        st = sum(1 for t, _ in stale if start <= t < end)
        cm = max((ms for t, ms in commits if start <= t < end), default=0.0)
        br = sum(1 for x in log if start <= x[0] < end and x[1] == "browser")
        print(f"  {start:2d}-{end:<2d}  {behind:10.2f} s   {len(wr):10d}"
              f"  {to_primary:7d}  {st:5d}  {cm:13.1f}  {br:13d}")


def main() -> None:
    global STICKY
    mode = sys.argv[1]

    if len(sys.argv) > 2:
        STICKY = float(sys.argv[2])
    prepare(mode)
    t0 = time.monotonic()
    sampler = LagSampler(t0)
    sampler.start()
    threads = [threading.Thread(target=writer, args=(i + 1, mode, t0))
               for i in range(WRITERS)]
    threads += [threading.Thread(target=browser, args=(mode, t0))
                for _ in range(BROWSERS)]
    threads += [threading.Thread(target=report, args=(t0,)),
                threading.Thread(target=cleanup, args=(t0,))]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    sampler.stop.set()
    reads = [x for x in log if x[1] == "writer"]
    prim_reads = [x for x in reads if x[2] == "primary"]
    ages = [age for _, age in stale]
    lat = [x[3] for x in reads]
    commit_ms = [ms for _, ms in commits]
    worst_lag = max(s[2] for s in sampler.samples)
    label = f"{mode} {STICKY:g} s" if mode.startswith("sticky") else mode
    print(f"mode {label}: {WRITERS} customers placing orders,"
          f" {BROWSERS} browsing, {SECONDS:.0f} s")

    for e in sorted(events):
        print(f"  {e}")

    print(f"  replica behind: worst {worst_lag:.2f} s")
    print(f"  own-order reads: {len(reads):,}, sent to primary"
          f" {len(prim_reads):,} ({len(prim_reads) / len(reads):.1%}),"
          f" stale {len(stale):,} ({len(stale) / len(reads):.1%})")

    never = [t for t, seen, _ in orders if not seen]
    gone = [t for t, _, vanished in orders if vanished]
    print(f"  orders viewed for the full 8 s: {len(orders)}; shown then gone:"
          f" {len(gone)}; never shown: {len(never)}")

    if ages:
        print(f"  stale reads came {med(ages):.1f} s (median) to"
              f" {max(ages):.1f} s (max) after the customer's own order")

    print(f"  own-order read latency: p50 {med(lat):.2f} ms,"
          f" p99 {pct(lat, 99):.2f} ms")
    print(f"  orders placed: {len(commit_ms):,}, commit p50"
          f" {med(commit_ms):.2f} ms, p99 {pct(commit_ms, 99):.2f} ms,"
          f" max {max(commit_ms):.1f} ms")
    timeline(sampler.samples)


if __name__ == "__main__":
    main()
