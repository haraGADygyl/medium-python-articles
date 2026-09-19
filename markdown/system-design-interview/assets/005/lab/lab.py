"""DDL lock-queue experiments against a 20M-row table."""
import argparse
import random
import statistics
import threading
import time

import psycopg

DSN = "host=127.0.0.1 port=5461 dbname=postgres user=postgres password=demo"
TRAFFIC_WORKERS = 8
INVERTERS = 40000


class Traffic:
    """Steady indexed point lookups, the kind an API serves."""

    def __init__(self) -> None:
        self.samples: list[tuple[float, float]] = []
        self.errors: list[tuple[float, str]] = []
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.t0 = time.monotonic()

    def worker(self) -> None:
        with psycopg.connect(DSN, autocommit=True) as conn:
            while not self.stop.is_set():
                inverter = random.randint(1, INVERTERS)
                started = time.monotonic()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT watt_hours FROM meter_reading "
                            "WHERE inverter_id = %s "
                            "ORDER BY read_at DESC LIMIT 1", (inverter,))
                        cur.fetchall()
                    elapsed = (time.monotonic() - started) * 1000
                    with self.lock:
                        self.samples.append((started - self.t0, elapsed))
                except psycopg.Error as exc:
                    with self.lock:
                        self.errors.append((started - self.t0,
                                            type(exc).__name__))
                    conn.close()
                    conn = psycopg.connect(DSN, autocommit=True)
                time.sleep(0.01)

    def start(self) -> list[threading.Thread]:
        threads = [threading.Thread(target=self.worker, daemon=True)
                   for _ in range(TRAFFIC_WORKERS)]
        for t in threads:
            t.start()
        return threads

    def report(self, label: str, window: tuple[float, float] | None = None
               ) -> dict:
        with self.lock:
            rows = list(self.samples)
        if window:
            rows = [r for r in rows if window[0] <= r[0] < window[1]]
        lat = sorted(v for _, v in rows)
        out = {"label": label, "queries": len(lat)}
        if lat:
            out["p50_ms"] = round(statistics.median(lat), 2)
            out["p99_ms"] = round(lat[int(len(lat) * 0.99)], 2)
            out["max_ms"] = round(lat[-1], 2)
        return out


def watch_locks(stop: threading.Event, seen: list[dict], t0: float) -> None:
    """Poll pg_locks for backends waiting on the table."""
    with psycopg.connect(DSN, autocommit=True) as conn:
        while not stop.wait(0.1):
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*) FILTER (WHERE NOT granted),
                           count(*) FILTER (WHERE NOT granted
                                            AND mode = 'AccessShareLock')
                    FROM pg_locks
                    WHERE relation = 'meter_reading'::regclass
                """)
                waiting, readers = cur.fetchone()
            seen.append({"t": round(time.monotonic() - t0, 2),
                         "waiting": waiting, "readers": readers})


def hold_reader(seconds: float, ready: threading.Event) -> None:
    """A long analytics transaction holding ACCESS SHARE on the table."""
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT reading_id FROM meter_reading LIMIT 1")
            cur.fetchall()
            ready.set()
            cur.execute("SELECT pg_sleep(%s)", (seconds,))
        conn.rollback()


def run_alter(sql: str, lock_timeout_ms: int | None,
              attempts: int) -> dict:
    """Run one DDL statement, optionally with lock_timeout and retries."""
    tries = []
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            with psycopg.connect(DSN, autocommit=True) as conn:
                with conn.cursor() as cur:
                    if lock_timeout_ms is not None:
                        cur.execute(f"SET lock_timeout = {lock_timeout_ms}")
                    cur.execute(sql)
            tries.append({"attempt": attempt, "ok": True,
                          "ms": round((time.monotonic() - started) * 1000, 1)})
            return {"tries": tries, "succeeded_on": attempt}
        except psycopg.errors.LockNotAvailable:
            tries.append({"attempt": attempt, "ok": False,
                          "ms": round((time.monotonic() - started) * 1000, 1)})
            time.sleep(0.5)
    return {"tries": tries, "succeeded_on": None}
