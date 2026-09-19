"""Scenario: which ALTERs are metadata-only and which rewrite the table."""
import json
import time

import psycopg

from lab import DSN, Traffic

STATEMENTS = [
    ("plain",
     "ALTER TABLE meter_reading ADD COLUMN firmware_tag text"),
    ("constant default",
     "ALTER TABLE meter_reading ADD COLUMN firmware_tag text "
     "DEFAULT 'fw-unknown'"),
    ("volatile default",
     "ALTER TABLE meter_reading ADD COLUMN firmware_tag text "
     "DEFAULT gen_random_uuid()::text"),
    ("type widened",
     "ALTER TABLE meter_reading ALTER COLUMN watt_hours TYPE numeric(12,2)"),
]


def table_bytes(conn: psycopg.Connection) -> int:
    return conn.execute(
        "SELECT pg_total_relation_size('meter_reading')").fetchone()[0]


def main() -> None:
    traffic = Traffic()
    traffic.start()
    time.sleep(3.0)
    rows = []
    for label, sql in STATEMENTS:
        with psycopg.connect(DSN, autocommit=True) as conn:
            conn.execute("ALTER TABLE meter_reading DROP COLUMN IF EXISTS "
                         "firmware_tag")
            conn.execute("ALTER TABLE meter_reading ALTER COLUMN watt_hours "
                         "TYPE numeric(9,2)")
            before = table_bytes(conn)
            started = time.monotonic()
            window_start = started - traffic.t0
            conn.execute(sql)
            seconds = time.monotonic() - started
            window_end = time.monotonic() - traffic.t0
            after = table_bytes(conn)
        blocked = traffic.report(label, (window_start, window_end))
        rows.append({"statement": label, "seconds": round(seconds, 2),
                     "size_before_mb": round(before / 1048576),
                     "size_after_mb": round(after / 1048576),
                     "traffic_p99_ms": blocked.get("p99_ms"),
                     "traffic_queries": blocked["queries"]})
        print(json.dumps(rows[-1]), flush=True)
        time.sleep(2.0)
    traffic.stop.set()
    with open("output-rewrite.json", "w") as fh:
        json.dump(rows, fh, indent=2)


if __name__ == "__main__":
    main()
