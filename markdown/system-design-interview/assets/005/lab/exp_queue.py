"""Scenario: traffic, a long reader, and one ALTER TABLE behind it."""
import json
import sys
import threading
import time

import psycopg

from lab import DSN, Traffic, hold_reader, run_alter, watch_locks

MODE = sys.argv[1] if len(sys.argv) > 1 else "naive"
HOLD_SECONDS = 12.0


def reset() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute("ALTER TABLE meter_reading DROP COLUMN IF EXISTS "
                     "firmware_tag")


def main() -> None:
    reset()
    traffic = Traffic()
    traffic.start()
    locks: list[dict] = []
    lock_stop = threading.Event()
    threading.Thread(target=watch_locks,
                     args=(lock_stop, locks, traffic.t0), daemon=True).start()
    time.sleep(4.0)                       # settle, collect a clean baseline

    ready = threading.Event()
    threading.Thread(target=hold_reader,
                     args=(HOLD_SECONDS, ready), daemon=True).start()
    ready.wait(5.0)
    reader_at = time.monotonic() - traffic.t0
    time.sleep(1.0)

    alter_at = time.monotonic() - traffic.t0
    sql = "ALTER TABLE meter_reading ADD COLUMN firmware_tag text"
    if MODE == "naive":
        result = run_alter(sql, None, 1)
    else:
        result = run_alter(sql, 250, 60)
    alter_done = time.monotonic() - traffic.t0

    time.sleep(HOLD_SECONDS + 3 - (time.monotonic() - traffic.t0 - reader_at))
    traffic.stop.set()
    lock_stop.set()
    time.sleep(0.5)

    peak = max(locks, key=lambda r: r["waiting"])
    stalled = [r for r in locks if r["waiting"] > 0]
    report = {
        "mode": MODE,
        "reader_started_at_s": round(reader_at, 2),
        "alter_started_at_s": round(alter_at, 2),
        "alter_finished_at_s": round(alter_done, 2),
        "alter_wall_s": round(alter_done - alter_at, 2),
        "alter_attempts": len(result["tries"]),
        "alter_succeeded_on": result["succeeded_on"],
        "peak_waiting_backends": peak["waiting"],
        "peak_waiting_at_s": peak["t"],
        "seconds_with_waiters": round(len(stalled) * 0.1, 1),
        "traffic_before": traffic.report("before", (1.0, alter_at)),
        "traffic_during": traffic.report("during", (alter_at, alter_done)),
        "traffic_after": traffic.report("after", (alter_done + 0.5, 99.0)),
        "traffic_errors": len(traffic.errors),
    }
    print(json.dumps(report, indent=2))
    with open(f"output-queue-{MODE}.json", "w") as fh:
        json.dump({"report": report, "locks": locks,
                   "alter_tries": result["tries"]}, fh, indent=2)


if __name__ == "__main__":
    main()
