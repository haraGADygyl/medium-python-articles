"""Check-then-insert booking race: naive table vs WITHOUT OVERLAPS, 24 workers."""
import random
import sys
import threading
from datetime import date, timedelta

import psycopg
from psycopg import errors

DSN = "postgresql://postgres:lab@localhost:55418/postgres"
WORKERS = 24
ATTEMPTS_PER_WORKER = 250
VAN_IDS = tuple(range(101, 121))
SEASON_START = date(2026, 6, 1)


def setup(table: str, constrained: bool) -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        key = ("PRIMARY KEY (van_id, rented_during WITHOUT OVERLAPS)" if constrained
               else "CHECK (true)")
        conn.execute(f"""
            CREATE TABLE {table} (
                rental_id bigint GENERATED ALWAYS AS IDENTITY,
                van_id integer NOT NULL,
                renter text NOT NULL,
                rented_during daterange NOT NULL,
                {key})""")
        if not constrained:
            conn.execute(f"CREATE INDEX ON {table} USING gist (van_id, rented_during)")


def worker(table: str, seed: int, isolation: str, tally: dict[str, int], lock: threading.Lock) -> None:
    rng = random.Random(seed)
    local = {"booked": 0, "refused_by_check": 0, "exclusion_violation": 0, "serialization_failure": 0}
    with psycopg.connect(DSN) as conn:
        conn.execute(f"SET default_transaction_isolation = '{isolation}'")
        conn.commit()
        for attempt in range(ATTEMPTS_PER_WORKER):
            start = SEASON_START + timedelta(days=rng.randrange(180))
            stay = (start, start + timedelta(days=rng.randrange(3, 11)))
            van_id = rng.choice(VAN_IDS)
            try:
                with conn.transaction():
                    taken = conn.execute(
                        f"SELECT EXISTS (SELECT 1 FROM {table} WHERE van_id = %s"
                        f" AND rented_during && daterange(%s, %s))", (van_id, *stay)).fetchone()[0]
                    if taken:
                        local["refused_by_check"] += 1
                        continue
                    conn.execute(
                        f"INSERT INTO {table} (van_id, renter, rented_during)"
                        f" VALUES (%s, %s, daterange(%s, %s))",
                        (van_id, f"renter-{seed}-{attempt}", *stay))
                local["booked"] += 1
            except errors.ExclusionViolation:
                local["exclusion_violation"] += 1
            except errors.SerializationFailure:
                local["serialization_failure"] += 1
    with lock:
        for key, value in local.items():
            tally[key] = tally.get(key, 0) + value


def overlapping_pairs(table: str) -> int:
    with psycopg.connect(DSN) as conn:
        return conn.execute(f"""
            SELECT count(*) FROM {table} a JOIN {table} b
              ON a.van_id = b.van_id AND a.rental_id < b.rental_id
             AND a.rented_during && b.rented_during""").fetchone()[0]


def run(table: str, constrained: bool, isolation: str) -> None:
    setup(table, constrained)
    tally: dict[str, int] = {}
    lock = threading.Lock()
    threads = [threading.Thread(target=worker, args=(table, seed, isolation, tally, lock))
               for seed in range(WORKERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print(f"{table:22} {isolation:16} {tally}  overlapping pairs: {overlapping_pairs(table)}")


if __name__ == "__main__":
    for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
        run("rental_naive", False, "read committed")
        run("rental_naive_ser", False, "serializable")
        run("rental_temporal", True, "read committed")
