"""One reader, one writer, one sailing: the interleaving, with timestamps.

    python3 scene.py plain                  stall 300 ms, delete after COMMIT
    python3 scene.py double 500 700         second delete at 500 ms, stall 700 ms
    python3 scene.py versioned              set-if-newer, but the writer deletes
    python3 scene.py tombstone              set-if-newer against a tombstone
"""
import sys
import threading
import time

import psycopg
import redis

from race import PG, RHOST, RPORT, SET_IF_NEWER

KEY, SAILING, TTL = "fare:42", 42, 3600


def main() -> None:
    mode = sys.argv[1]
    delay = int(sys.argv[2]) / 1000 if len(sys.argv) > 2 else 0.5
    stall = int(sys.argv[3]) / 1000 if len(sys.argv) > 3 else 0.3
    r = redis.Redis(host=RHOST, port=RPORT, decode_responses=True)
    fill = r.register_script(SET_IF_NEWER)
    setup = psycopg.connect(PG, autocommit=True)
    setup.execute("UPDATE fares SET fare_cents = 8900, version = 7"
                  " WHERE sailing_id = %s", (SAILING,))
    r.delete(KEY)
    t0 = time.monotonic()
    log: list[tuple[float, str, str]] = []

    def note(who: str, what: str) -> None:
        log.append((time.monotonic() - t0, who, what))

    def reader() -> None:
        db = psycopg.connect(PG, autocommit=True)
        note("reader", f"GET {KEY} -> {r.get(KEY)} (miss)")
        fare, version = db.execute(
            "SELECT fare_cents, version FROM fares WHERE sailing_id = %s",
            (SAILING,)).fetchone()
        note("reader", f"SELECT -> {fare / 100:.2f} EUR, version {version}")
        note("reader", f"stalls for {stall * 1000:.0f} ms")
        time.sleep(stall)

        if mode in ("versioned", "tombstone"):
            took = fill(keys=[KEY], args=[version, fare, TTL])
            note("reader", f"set-if-newer v{version} -> "
                 + ("written" if took == 1 else "refused"))
        else:
            r.set(KEY, f"{version}|{fare}", ex=TTL)
            note("reader", f"SET {KEY} = v{version}|{fare}")

    def writer() -> None:
        db = psycopg.connect(PG, autocommit=True)
        time.sleep(0.05)
        version = db.execute(
            "UPDATE fares SET fare_cents = 11900, version = version + 1"
            " WHERE sailing_id = %s RETURNING version", (SAILING,)).fetchone()[0]
        note("writer", f"UPDATE -> 119.00 EUR, version {version}, COMMIT")

        if mode == "tombstone":
            fill(keys=[KEY], args=[version, "-", TTL])
            note("writer", f"tombstone v{version}|-")
        else:
            r.delete(KEY)
            note("writer", f"DEL {KEY}")

        if mode == "double":
            time.sleep(delay)
            r.delete(KEY)
            note("writer", f"DEL {KEY} again, {delay * 1000:.0f} ms later")

    threads = [threading.Thread(target=reader), threading.Thread(target=writer)]

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    time.sleep(1.0)
    db_fare, db_version = setup.execute(
        "SELECT fare_cents, version FROM fares WHERE sailing_id = %s",
        (SAILING,)).fetchone()
    cached = r.get(KEY)
    note("check", f"database v{db_version}|{db_fare}, cache {cached}, "
         f"TTL {r.ttl(KEY)} s")

    print(f"scene {mode}" + (f" ({delay * 1000:.0f} ms delay, "
                             f"{stall * 1000:.0f} ms stall)"
                             if mode == "double" else ""))

    for at, who, what in sorted(log):
        print(f"  {at * 1000:7.1f} ms  {who:<6}  {what}")


if __name__ == "__main__":
    main()
