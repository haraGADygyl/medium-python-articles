"""Scenario: two ways to make a backfilled column NOT NULL."""
import json
import time

import psycopg

from lab import DSN, Traffic


def timed(conn: psycopg.Connection, traffic: Traffic, sql: str) -> dict:
    """Run one statement and report what the traffic felt while it ran."""
    started = time.monotonic()
    window_start = started - traffic.t0
    conn.execute(sql)
    seconds = time.monotonic() - started
    window_end = time.monotonic() - traffic.t0
    felt = traffic.report(sql, (window_start, window_end))
    return {"sql": sql.split(" meter_reading ")[-1][:58],
            "seconds": round(seconds, 2),
            "queries_served": felt["queries"],
            "p99_ms": felt.get("p99_ms")}


def fresh(conn: psycopg.Connection) -> None:
    conn.execute("ALTER TABLE meter_reading DROP CONSTRAINT IF EXISTS "
                 "panel_serial_present")
    conn.execute("ALTER TABLE meter_reading DROP COLUMN IF EXISTS "
                 "panel_serial")
    conn.execute("ALTER TABLE meter_reading ADD COLUMN panel_serial text "
                 "DEFAULT 'sn-unknown'")


def main() -> None:
    traffic = Traffic()
    traffic.start()
    time.sleep(3.0)
    out = {}
    with psycopg.connect(DSN, autocommit=True) as conn:
        fresh(conn)
        out["direct"] = [timed(conn, traffic,
                               "ALTER TABLE meter_reading ALTER COLUMN "
                               "panel_serial SET NOT NULL")]
        time.sleep(2.0)
        fresh(conn)
        out["staged"] = [
            timed(conn, traffic,
                  "ALTER TABLE meter_reading ADD CONSTRAINT "
                  "panel_serial_present CHECK (panel_serial IS NOT NULL) "
                  "NOT VALID"),
            timed(conn, traffic,
                  "ALTER TABLE meter_reading VALIDATE CONSTRAINT "
                  "panel_serial_present"),
            timed(conn, traffic,
                  "ALTER TABLE meter_reading ALTER COLUMN panel_serial "
                  "SET NOT NULL"),
        ]
    traffic.stop.set()
    print(json.dumps(out, indent=2))
    with open("output-notnull.json", "w") as fh:
        json.dump(out, fh, indent=2)


if __name__ == "__main__":
    main()
